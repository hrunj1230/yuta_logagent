from langchain_core.tools import tool
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from ..storage.database import SessionLocal
from ..storage.models import Source, SourceType, EmbeddingStatus
from ..llm_router import local_embedding
from . import chatlog
from .ingest_rules import git_file_dates, normalize_date, resolve_date, should_collect
import os
import hashlib
import shutil
import subprocess
import json
import threading
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
import time

# 설정
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 400
DATA_DIR = Path("./data/sources")
CHROMA_DIR = Path("./chroma_db")

# 하루치를 한 덩어리로 담는 문서 타입. 청크 분할에서 제외한다.
DAILY_SUMMARY_TYPES = {"git_log", "agent_chatlog"}

# 한 번에 임베딩할 청크 수. 작을수록 진행률이 촘촘해지고, 클수록 처리량이 높다.
EMBED_BATCH_SIZE = 16

# IN_PROGRESS 상태가 이 시간을 넘기면 중단된 작업으로 보고 재시도를 허용한다.
# 서버가 임베딩 도중 죽으면 상태가 영원히 IN_PROGRESS로 남기 때문이다.
STALE_AFTER = timedelta(minutes=30)


def _get_chroma_collection(user_id: str):
    """사용자별 ChromaDB Collection 가져오기"""
    collection_name = f"user_{user_id}"

    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=local_embedding,
        persist_directory=str(CHROMA_DIR)
    )

    return vectorstore._collection


def _save_to_chromadb(chunks: list[Document], user_id: str, progress=None):
    """
    청크를 ChromaDB에 저장한다.

    진행률을 보고할 수 있도록 배치로 나누어 저장한다. 한 번에 전부 넣으면
    가장 오래 걸리는 구간에서 아무 신호도 나오지 않는다.
    """
    if not chunks:
        return

    store = Chroma(
        collection_name=f"user_{user_id}",
        embedding_function=local_embedding,
        persist_directory=str(CHROMA_DIR),
    )

    total = len(chunks)
    for start in range(0, total, EMBED_BATCH_SIZE):
        batch = chunks[start:start + EMBED_BATCH_SIZE]
        store.add_documents(batch)
        if progress:
            progress("embedding", min(start + len(batch), total), total)


def _delete_source_embeddings(user_id: str, source_id: int) -> int:
    """특정 소스의 모든 임베딩 삭제"""
    try:
        collection = _get_chroma_collection(user_id)

        results = collection.get(
            where={"source_id": source_id},
            include=["metadatas"]
        )

        ids_to_delete = results.get("ids", [])

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)

        return len(ids_to_delete)
    except Exception as e:
        print(f"ChromaDB 삭제 중 오류: {e}")
        return 0


def _split_documents(documents: list[Document]) -> list[Document]:
    """문서를 청크로 분할"""
    if not documents:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    chunks = []
    for doc in documents:
        if doc.metadata.get("source_type") in DAILY_SUMMARY_TYPES:
            # 하루 요약은 그 자체로 완결된 한 덩어리다. 쪼개면 제목 줄과 맺음 줄이
            # 본문에서 떨어져 고아 청크가 된다. 이 문서는 유사도가 아니라 날짜
            # 메타데이터로 조회하므로 길이가 길어도 검색에 불리하지 않다.
            doc.metadata["chunk_index"] = 0
            chunks.append(doc)
            continue

        doc_chunks = splitter.split_documents([doc])

        # 청크 인덱스 추가
        for idx, chunk in enumerate(doc_chunks):
            chunk.metadata["chunk_index"] = idx
            chunks.append(chunk)

    return chunks


def _filter_new_documents(documents: list[Document], user_id: str, source_id: int) -> tuple[list[Document], int]:
    """기존 임베딩과 비교하여 새 문서만 반환"""
    try:
        collection = _get_chroma_collection(user_id)

        # 기존 해시 목록 가져오기
        results = collection.get(
            where={"source_id": source_id},
            include=["metadatas"]
        )
        existing_hashes = set()
        for metadata in results.get("metadatas", []):
            if "file_hash" in metadata:
                existing_hashes.add(metadata["file_hash"])
            elif "commit_sha" in metadata:
                existing_hashes.add(metadata["commit_sha"])
    except Exception as e:
        print(f"기존 임베딩 조회 중 오류 (새 Collection 생성): {e}")
        existing_hashes = set()

    # 새 문서 필터링
    new_docs = []
    skipped = 0

    for doc in documents:
        doc_hash = doc.metadata.get("file_hash") or doc.metadata.get("commit_sha")
        if doc_hash not in existing_hashes:
            new_docs.append(doc)
        else:
            skipped += 1

    return new_docs, skipped


def _collect_documents(
    root: Path,
    source: Source,
    user_id: str,
    source_type: str,
    git_dates: dict[str, str] | None = None,
    allow_mtime: bool = False,
) -> tuple[list[Document], dict[str, int]]:
    """
    디렉토리를 순회하며 수집 대상 문서를 Document 로 변환한다.

    수집 규칙(확장자/제외 디렉토리/크기)과 날짜 추출은 ingest_rules 에 위임한다.
    날짜를 확정할 수 없는 문서는 일지 시스템의 대상이 아니므로 제외한다.

    Returns:
        (문서 목록, {제외 사유: 건수})
    """
    documents: list[Document] = []
    skipped: dict[str, int] = {}

    def note(reason: str):
        skipped[reason] = skipped.get(reason, 0) + 1

    for file_path in root.rglob("*"):
        ok, reason = should_collect(file_path, root)
        if not ok:
            if reason != "not_a_file":
                note(reason)
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"파일 읽기 실패 {file_path}: {e}")
            note("read_failed")
            continue

        rel_path = file_path.relative_to(root)
        doc_date, date_origin = resolve_date(
            rel_path=rel_path,
            content=content,
            git_dates=git_dates,
            abs_path=file_path if allow_mtime else None,
        )

        if not doc_date:
            note("no_date")
            continue

        documents.append(Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "source_id": source.id,
                "source_type": source_type,
                "source_name": source.name,
                "file_path": str(rel_path),
                "file_hash": hashlib.sha256(content.encode()).hexdigest(),
                "date": doc_date,
                "date_origin": date_origin,
                "embedded_at": datetime.now().isoformat(),
            }
        ))

    return documents, skipped


def _git(*args: str) -> subprocess.CompletedProcess:
    """git 명령을 실행한다."""
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _clone_mode(repo_dir: Path) -> bool | None:
    """
    이미 받아둔 저장소가 bare 인지 판단한다.

    Returns:
        True=bare, False=작업 트리 있음, None=git 저장소가 아님
    """
    result = _git("-C", str(repo_dir), "rev-parse", "--is-bare-repository")
    if result.returncode != 0:
        return None
    return result.stdout.strip() == "true"


def _is_partial_clone(repo_dir: Path) -> bool:
    """
    blob 을 받지 않은 partial clone 인지 판단한다.

    서버가 필터를 지원하지 않아 객체를 전부 받아왔더라도 이 설정은 남으므로,
    '어떤 의도로 받은 저장소인가'를 가리는 표시로 쓸 수 있다.
    """
    result = _git("-C", str(repo_dir), "config", "--get", "remote.origin.partialclonefilter")
    return bool(result.stdout.strip())


def _sync_repo(source: Source, user_id: str, with_files: bool) -> Path:
    """
    소스의 git 저장소를 로컬에 준비한다 (없으면 clone, 있으면 갱신).

    받는 형태는 그 저장소로 무엇을 읽을지에 따라 갈린다:
        with_files=True  (git)     — 파일 본문을 읽어야 하므로 통째로 받아 체크아웃한다.
        with_files=False (git_log) — 커밋 메타데이터만 읽으므로
                                     --filter=blob:none --no-checkout 으로 받는다.
                                     파일 본문(blob)을 아예 내려받지 않아
                                     같은 저장소 기준 752KB → 148KB 로 줄었다.

    갱신 명령도 함께 갈린다. 체크아웃이 없는 저장소에 pull 을 걸면 작업 트리를
    건드리려다 실패하므로 fetch 를 쓴다. fetch 는 refs/remotes/origin/* 만
    앞당기는데, 조회를 --all 로 하므로 새 커밋이 그대로 들어온다.

    Returns:
        준비된 저장소 경로
    """
    repo_dir = DATA_DIR / user_id / source.name

    if repo_dir.exists():
        # 받아둔 형태가 지금 필요한 형태와 다르면 그대로 쓸 수 없다.
        # bare 는 옛 --mirror 방식의 잔재이므로 두 타입 모두 다시 받는다.
        stale = _clone_mode(repo_dir) is not False
        if not stale and with_files:
            # blob 이 빠진 저장소로는 파일 본문을 읽을 수 없다
            stale = _is_partial_clone(repo_dir)

        if stale:
            shutil.rmtree(repo_dir, ignore_errors=True)
        else:
            # 갱신하지 않으면 clone 시점 이후의 커밋·문서가 영원히 들어오지 않는다
            result = (
                _git("-C", str(repo_dir), "pull") if with_files
                else _git("-C", str(repo_dir), "fetch", "--prune", "origin")
            )
            if result.returncode != 0:
                verb = "pull" if with_files else "fetch"
                raise RuntimeError(f"Git {verb} 실패: {result.stderr}")
            return repo_dir

    repo_dir.parent.mkdir(parents=True, exist_ok=True)
    options = [] if with_files else ["--filter=blob:none", "--no-checkout"]
    result = _git("clone", *options, source.location, str(repo_dir))
    if result.returncode != 0:
        raise RuntimeError(f"Git clone 실패: {result.stderr}")

    return repo_dir


def _collect_git_files(source: Source, user_id: str) -> tuple[list[Document], dict[str, int]]:
    """Git 저장소를 동기화하고 텍스트 파일 수집"""
    repo_dir = _sync_repo(source, user_id, with_files=True)

    # 파일별 최종 커밋 날짜를 한 번에 조회 (문서 날짜의 3순위 근거)
    git_dates = git_file_dates(repo_dir)

    documents, skipped = _collect_documents(
        root=repo_dir,
        source=source,
        user_id=user_id,
        source_type=source.type.value,
        git_dates=git_dates,
        allow_mtime=False,  # git 소스는 커밋 날짜가 있으므로 mtime까지 내려가지 않는다
    )
    return documents, skipped


def _read_commits(repo_dir: Path) -> tuple[list[dict], dict[str, int]]:
    """
    저장소의 커밋을 읽어 구조화한다.

    수집 대상이 아닌 커밋은 사유와 함께 세어 돌려준다. 조용히 버리면 나중에
    "커밋이 몇 개 들어왔는지"를 검산할 수 없고, 유실이 생겨도 드러나지 않는다.

    Returns:
        (커밋 목록, {제외 사유: 건수})
    """
    result = subprocess.run(
        [
            # core.quotepath=false: 한글 경로가 8진수로 이스케이프되는 것을 방지
            "git", "-C", str(repo_dir), "-c", "core.quotepath=false", "log",
            # --all: 모든 ref 를 훑는다. 갱신을 fetch 로 하면 로컬 브랜치는
            # 제자리에 있고 refs/remotes/origin/* 만 앞당겨지므로, --all 이 아니면
            # clone 이후의 커밋이 조회에 들어오지 않는다.
            "--all",
            "--date=iso",
            "--pretty=format:Commit: %H%nAuthor: %an <%ae>%nDate: %ad%nSubject: %s%n",
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Git log 실패: {result.stderr}")

    # 'Commit: ' 로 시작하는 줄이 새 커밋의 시작이다. %s(제목)는 한 줄이므로
    # 본문 줄이 끼어들어 라벨을 흉내 낼 여지가 없다.
    parsed: list[dict] = []
    for line in result.stdout.splitlines():
        if line.startswith("Commit: "):
            parsed.append({"sha": line[8:].strip(), "author": "", "message": ""})
        elif not parsed:
            continue
        elif line.startswith("Author: "):
            parsed[-1]["author"], parsed[-1]["email"] = _split_author(line[8:].strip())
        elif line.startswith("Date: "):
            parsed[-1]["date"] = normalize_date(line[6:].strip())
        elif line.startswith("Subject: "):
            parsed[-1]["message"] = line[9:].strip()

    commits: list[dict] = []
    skipped: dict[str, int] = {}

    for commit in parsed:
        if not commit.get("date"):
            # 날짜가 없으면 일지의 어느 날에도 배치할 수 없다.
            # 조용히 버리면 유실이 통계에 잡히지 않으므로 사유와 함께 센다.
            skipped["no_date"] = skipped.get("no_date", 0) + 1
        else:
            commits.append(commit)

    return commits, skipped


def _split_author(raw: str) -> tuple[str, str]:
    """'이름 <메일>' 을 이름과 메일로 나눈다. 메일이 없으면 빈 문자열."""
    name, sep, email = raw.partition(" <")
    return name.strip(), email.rstrip(">").strip() if sep else ""


def _daily_commit_documents(
    commits: list[dict], source: Source, user_id: str
) -> list[Document]:
    """
    커밋을 날짜별로 묶어 하루당 문서 하나로 만든다.

    커밋 단위로 저장하면 하루에 문서가 수십 개 생기는데, 사용자가 묻는 단위는
    커밋이 아니라 하루다. 저장 단위를 질문 단위에 맞추면 그날 자료가 한 덩어리로
    잡히고, 커밋마다 반복되던 작성자·날짜 줄도 한 번만 남는다.

    일지가 답해야 할 것은 '무엇을 했는가'이므로 커밋 메시지를 본문으로 삼는다.
    파일 경로는 수집하지 않는다 — 조회 명령이 커밋 메타데이터만 읽기 때문이다.
    """
    by_date: dict[str, list[dict]] = defaultdict(list)
    for commit in commits:
        by_date[commit["date"]].append(commit)

    documents = []
    for date, day in sorted(by_date.items()):
        # git log 는 최신순이므로 하루 안에서는 시간순으로 되돌린다
        day = list(reversed(day))

        # 메일 주소는 수집만 하고 본문·메타데이터에는 싣지 않는다.
        # 같은 사람이 기기마다 다른 주소를 쓰면 한 사람이 여럿으로 갈라진다.
        authors = sorted({commit["author"] for commit in day if commit["author"]})

        lines = [
            f"[{date}] {source.name} — 커밋 {len(day)}건",
            "",
            "한 일:",
        ]
        lines += [f"- {commit['message']}" for commit in day]

        content = "\n".join(lines)
        documents.append(Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "source_id": source.id,
                "source_type": "git_log",
                "source_name": source.name,
                # 하루치를 한 덩어리로 교체하기 위한 키.
                # file_path 는 증분 판정(_delete_stale_chunks)이 쓰는 이름이다.
                "file_path": f"commits/{date}",
                "file_hash": hashlib.sha256(content.encode()).hexdigest(),
                # 원본 git log 와 대조해 유실을 검산할 수 있도록 남긴다
                "commit_shas": ",".join(commit["sha"][:8] for commit in day),
                "commit_count": len(day),
                "author": ", ".join(authors),
                "date": date,
                "date_origin": "git",
                "embedded_at": datetime.now().isoformat(),
            }
        ))

    return documents


def _collect_git_log(source: Source, user_id: str) -> tuple[list[Document], dict[str, int]]:
    """Git 커밋 히스토리를 날짜별로 묶어 수집"""
    # 커밋 메타데이터만 읽으므로 파일 본문(blob)도 체크아웃도 받지 않는다.
    repo_dir = _sync_repo(source, user_id, with_files=False)

    commits, skipped = _read_commits(repo_dir)
    return _daily_commit_documents(commits, source, user_id), skipped


def _collect_local_files(source: Source, user_id: str) -> tuple[list[Document], dict[str, int]]:
    """로컬 디렉토리의 문서 파일 수집"""
    local_path = Path(source.location)

    if not local_path.exists():
        raise FileNotFoundError(f"로컬 경로가 존재하지 않습니다: {source.location}")

    # 로컬 경로가 git 저장소라면 커밋 날짜도 날짜 근거로 활용한다
    git_dates = git_file_dates(local_path) if (local_path / ".git").exists() else {}

    return _collect_documents(
        root=local_path,
        source=source,
        user_id=user_id,
        source_type="local",
        git_dates=git_dates,
        allow_mtime=True,  # 로컬 소스는 커밋 이력이 없을 수 있어 mtime을 최후 수단으로 허용
    )


def _collect_chatlog(source: Source, user_id: str) -> tuple[list[Document], dict[str, int]]:
    """
    에이전트 대화 로그 수집.

    location 은 Claude Code 트랜스크립트가 모인 디렉토리를 가리킨다
    (예: ~/.claude/projects/-Users-me-work-myproject).
    """
    root = Path(source.location).expanduser()

    if not root.exists():
        raise FileNotFoundError(f"대화 로그 경로가 존재하지 않습니다: {source.location}")

    if not any(root.glob("*.jsonl")):
        # 경로는 있는데 트랜스크립트가 없으면 잘못 지정한 것이다.
        # 0건 수집으로 조용히 성공 처리하면 사용자가 알 방법이 없다.
        raise FileNotFoundError(f"트랜스크립트(.jsonl)가 없습니다: {source.location}")

    turns, skipped = chatlog.read_turns(root)
    return chatlog.daily_documents(turns, source, user_id), skipped


def _collect_memsearch(source: Source, user_id: str) -> tuple[list[Document], dict[str, int]]:
    """Memsearch 데이터 수집 (추후 구현)"""
    return [], {}


def _delete_stale_chunks(user_id: str, source_id: int, documents: list[Document]) -> int:
    """
    갱신 대상 문서의 기존 청크를 미리 삭제한다 (delete-then-insert).

    파일이 수정되면 해시가 달라져 새 문서로 저장되는데, 이전 해시의 청크를
    지우지 않으면 같은 파일의 옛 내용이 벡터DB에 계속 남아 검색에 섞인다.

    Returns:
        삭제된 청크 수
    """
    keys = {
        doc.metadata.get("file_path") or doc.metadata.get("commit_sha")
        for doc in documents
    }
    keys.discard(None)
    if not keys:
        return 0

    try:
        collection = _get_chroma_collection(user_id)
    except Exception as e:
        print(f"기존 청크 삭제 준비 실패: {e}")
        return 0

    deleted = 0
    for key in keys:
        for field in ("file_path", "commit_sha"):
            try:
                found = collection.get(where={"$and": [
                    {"source_id": source_id},
                    {field: key},
                ]})
            except Exception:
                continue

            ids = found.get("ids", [])
            if ids:
                collection.delete(ids=ids)
                deleted += len(ids)

    return deleted


def _process_source_by_type(source: Source, user_id: str, progress=None) -> dict:
    """
    소스 타입에 따라 적절한 처리 함수 호출.

    Args:
        progress: progress(phase, done, total) 형태의 콜백. 화면 진행률 표시용.
    """
    start_time = time.time()

    def report(phase: str, done: int = 0, total: int = 0):
        if progress:
            progress(phase, done, total)

    # 원격 저장소를 clone/pull 하는 구간이 길 수 있어 먼저 알린다
    report("collecting")

    # 소스 타입별 파일 수집
    if source.type == SourceType.GIT:
        documents, skip_reasons = _collect_git_files(source, user_id)
    elif source.type == SourceType.GIT_LOG:
        documents, skip_reasons = _collect_git_log(source, user_id)
    elif source.type == SourceType.LOCAL:
        documents, skip_reasons = _collect_local_files(source, user_id)
    elif source.type == SourceType.AGENT_CHATLOG:
        documents, skip_reasons = _collect_chatlog(source, user_id)
    elif source.type == SourceType.MEMSEARCH:
        documents, skip_reasons = _collect_memsearch(source, user_id)
    else:
        raise ValueError(f"지원하지 않는 소스 타입: {source.type}")

    # 증분 업데이트 (내용이 바뀌지 않은 문서는 건너뜀)
    new_docs, unchanged_count = _filter_new_documents(documents, user_id, source.id)

    # 갱신되는 문서의 옛 청크를 먼저 제거한다
    stale_deleted = _delete_stale_chunks(user_id, source.id, new_docs)

    # 청크 분할
    chunks = _split_documents(new_docs)

    # ChromaDB에 저장 (가장 오래 걸리는 구간 — 배치마다 진행률 보고)
    if chunks:
        report("embedding", 0, len(chunks))
        _save_to_chromadb(chunks, user_id, progress=progress)

    duration = time.time() - start_time

    return {
        "stats": {
            "files_collected": len(documents),
            "files_skipped": sum(skip_reasons.values()),
            "skip_reasons": skip_reasons,
            "files_unchanged": unchanged_count,
            "chunks_created": len(chunks),
            "stale_chunks_deleted": stale_deleted,
            "duration_seconds": round(duration, 2)
        }
    }


def is_stale(source: Source) -> bool:
    """IN_PROGRESS 상태가 중단된 작업의 잔재인지 판단한다."""
    if source.embedding_status != EmbeddingStatus.IN_PROGRESS:
        return False
    started = source.embedding_started_at
    if started is None:
        # 시작 시각이 없다는 건 이 기능 도입 전에 남은 값이므로 재시도를 허용한다
        return True
    return datetime.now() - started > STALE_AFTER


def _run_embedding_job(user_id: str, source_id: int):
    """
    백그라운드 스레드에서 실제 임베딩을 수행한다.

    스레드마다 별도의 DB 세션을 쓴다 (SQLAlchemy 세션은 스레드 간 공유 불가).
    진행률은 sources.embedding_stats 에 기록되어 화면 폴링으로 노출된다.
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()
        if not source:
            return

        def progress(phase: str, done: int = 0, total: int = 0):
            source.embedding_stats = json.dumps({
                "phase": phase,
                "done": done,
                "total": total,
            })
            db.commit()

        try:
            result = _process_source_by_type(source, user_id, progress=progress)

            source.embedding_status = EmbeddingStatus.COMPLETED
            source.last_synced_at = datetime.now()
            source.embedding_stats = json.dumps({**result["stats"], "phase": "done"})
            source.embedding_error = None
            db.commit()

        except Exception as e:
            db.rollback()
            source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()
            if source:
                source.embedding_status = EmbeddingStatus.FAILED
                source.embedding_error = str(e)
                db.commit()
            print(f"[embed] 임베딩 실패 (source_id={source_id}): {e}")

    finally:
        db.close()


@tool
def embed_source(user_id: str, source_id: int) -> str:
    """
    소스의 모든 파일을 임베딩합니다 (증분 업데이트).

    Args:
        user_id: 사용자 ID
        source_id: 소스 ID

    Returns:
        임베딩 시작 안내 (완료 결과가 아님)
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()

        if not source:
            return f"❌ 오류: 소스를 찾을 수 없습니다. (ID: {source_id})"

        if source.embedding_status == EmbeddingStatus.IN_PROGRESS and not is_stale(source):
            return f"⏳ 소스 '{source.name}'는 이미 임베딩 진행 중입니다."

        was_stale = is_stale(source)

        # 작업을 넘기기 전에 상태를 선점한다
        source.embedding_status = EmbeddingStatus.IN_PROGRESS
        source.embedding_started_at = datetime.now()
        source.embedding_error = None
        source.embedding_stats = json.dumps({"phase": "starting", "done": 0, "total": 0})
        db.commit()

        source_name = source.name
    finally:
        db.close()

    # 실제 작업은 백그라운드에서. 채팅은 기다리지 않고 바로 응답한다.
    threading.Thread(
        target=_run_embedding_job,
        args=(user_id, source_id),
        daemon=True,
        name=f"embed-{user_id}-{source_id}",
    ).start()

    notice = f"""🚀 임베딩을 시작했습니다: {source_name}

저장소를 가져와 문서를 임베딩하는 중이며, 진행 상황은 화면에 표시됩니다.
완료 여부가 궁금하면 "임베딩 상태 알려줘"라고 물어보세요."""

    if was_stale:
        notice += "\n\n⚠️ 이전에 중단된 작업이 남아 있어 정리하고 다시 시작했습니다."

    return notice


@tool
def get_embedding_status(user_id: str, source_id: int) -> str:
    """
    소스의 임베딩 상태를 조회합니다.

    Args:
        user_id: 사용자 ID
        source_id: 소스 ID

    Returns:
        임베딩 상태 정보
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter_by(id=source_id, user_id=user_id).first()

        if not source:
            return f"❌ 오류: 소스를 찾을 수 없습니다. (ID: {source_id})"

        status_emoji = {
            EmbeddingStatus.PENDING: "⏳",
            EmbeddingStatus.IN_PROGRESS: "🔄",
            EmbeddingStatus.COMPLETED: "✅",
            EmbeddingStatus.FAILED: "❌"
        }.get(source.embedding_status, "❓")

        result = f"{status_emoji} 소스: {source.name}\n"
        result += f"상태: {source.embedding_status.value}\n"

        if source.last_synced_at:
            result += f"마지막 동기화: {source.last_synced_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

        stats = json.loads(source.embedding_stats) if source.embedding_stats else {}

        if source.embedding_status == EmbeddingStatus.IN_PROGRESS:
            if is_stale(source):
                result += (
                    "\n⚠️ 작업이 중단된 것으로 보입니다 "
                    f"(시작 후 {STALE_AFTER.total_seconds() / 60:.0f}분 경과).\n"
                    "다시 임베딩해 달라고 요청하시면 새로 시작합니다."
                )
            else:
                result += f"\n진행: {describe_progress(stats)}"

        elif stats:
            result += f"\n통계:\n"
            result += f"- 수집된 문서: {stats.get('files_collected', 0)}개\n"
            result += f"- 생성된 청크: {stats.get('chunks_created', 0)}개\n"
            result += f"- 제외된 파일: {stats.get('files_skipped', 0)}개\n"

        if source.embedding_status == EmbeddingStatus.FAILED and source.embedding_error:
            result += f"\n⚠️ 오류: {source.embedding_error}"

        return result

    finally:
        db.close()


# 진행 단계를 사용자에게 보여줄 문구로 변환한다
PHASE_LABELS = {
    "starting": "준비 중",
    "collecting": "저장소 가져오는 중",
    "embedding": "임베딩 중",
    "done": "완료",
}


def describe_progress(stats: dict) -> str:
    """진행 상태 dict 를 사람이 읽을 문장으로 만든다."""
    phase = stats.get("phase", "starting")
    label = PHASE_LABELS.get(phase, phase)
    total = stats.get("total") or 0
    done = stats.get("done") or 0

    if phase == "embedding" and total:
        return f"{label} ({done}/{total} 청크, {done * 100 // total}%)"
    return label
