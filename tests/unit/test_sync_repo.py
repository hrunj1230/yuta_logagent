"""
저장소 동기화 단위 테스트

로컬에 만든 임시 저장소를 origin 으로 삼으므로 네트워크가 필요 없다.
ChromaDB·임베딩 모델도 타지 않는다 (수집 함수까지만 호출).

여기서 잠그는 것은 "클론한 뒤 origin 에 쌓인 커밋이 재수집에 들어오는가"다.
갱신을 빠뜨리면 수집은 성공으로 끝나고 통계도 정상으로 보이므로,
테스트가 없으면 유실이 어디에도 드러나지 않는다.
"""
import subprocess
import types
from pathlib import Path

import pytest

from src.storage.models import SourceType
from src.tools import embedding


def git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"git {' '.join(args)} 실패:\n{result.stderr}"
    return result.stdout


def commit(repo: Path, name: str, message: str, date: str | None = None) -> None:
    (repo / name).write_text(f"# {name}\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    args = ["commit", "-q", "-m", message]
    if date:
        # 날짜별 묶기를 확인하려면 커밋을 서로 다른 날에 놓아야 한다
        args = ["-c", f"user.date={date}", *args, "--date", date]
    git(*args, cwd=repo)


def commit_count(docs) -> int:
    """하루 문서들이 담고 있는 커밋 총합."""
    return sum(d.metadata["commit_count"] for d in docs)


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """커밋 2개를 가진 원격 저장소 역할의 로컬 저장소."""
    repo = tmp_path / "origin"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("config", "user.email", "test@example.com", cwd=repo)
    git("config", "user.name", "tester", cwd=repo)
    commit(repo, "first.md", "feat: 첫 커밋")
    commit(repo, "second.md", "feat: 둘째 커밋")
    return repo


@pytest.fixture
def source(origin: Path):
    """DB 없이 수집 함수가 요구하는 속성만 가진 Source 대역."""
    return types.SimpleNamespace(
        id=1, name="testrepo", location=str(origin), type=SourceType.GIT_LOG
    )


@pytest.fixture(autouse=True)
def data_dir(tmp_path: Path, monkeypatch):
    """클론 위치를 임시 디렉토리로 돌려 실제 data/sources 를 건드리지 않는다."""
    target = tmp_path / "data"
    monkeypatch.setattr(embedding, "DATA_DIR", target)
    return target


def repo_path(data_dir: Path) -> Path:
    return data_dir / "tester" / "testrepo"


class TestGitLogSync:
    """git_log 타입 — 파일 본문 없이 받고(blob:none) fetch 로 갱신한다."""

    def test_clone_수집(self, source):
        """커밋 2건이 같은 날이므로 하루 문서 하나로 묶인다."""
        docs, _ = embedding._collect_git_log(source, "tester")

        assert len(docs) == 1
        assert docs[0].metadata["commit_count"] == 2
        assert "feat: 첫 커밋" in docs[0].page_content
        assert "feat: 둘째 커밋" in docs[0].page_content

    def test_체크아웃_없이_받는다(self, source, data_dir):
        """--no-checkout — 커밋 메타데이터만 읽으므로 작업 트리가 필요 없다."""
        embedding._collect_git_log(source, "tester")
        repo = repo_path(data_dir)

        assert not (repo / "first.md").exists()

    def test_blob_을_받지_않는다(self, source, data_dir):
        """--filter=blob:none — 파일 본문은 임베딩에 쓰이지 않는다.

        로컬 origin 은 필터를 무시하고 객체를 전부 넘기지만(git 의 제약),
        설정은 남으므로 어떤 형태로 요청했는지는 여기서 잠글 수 있다.
        """
        embedding._collect_git_log(source, "tester")
        repo = repo_path(data_dir)

        assert embedding._is_partial_clone(repo)
        assert git(
            "-C", str(repo), "config", "--get", "remote.origin.partialclonefilter"
        ).strip() == "blob:none"

    def test_클론_이후의_커밋이_재수집에_들어온다(self, source, origin):
        """C2 회귀 방지 — 갱신을 빠뜨리면 커밋 수가 2 그대로 남는다.

        fetch 는 refs/remotes/origin/* 만 앞당기므로, 조회가 --all 이 아니면
        새 커밋이 로컬 브랜치 뒤에 가려 보이지 않는다.
        """
        before, _ = embedding._collect_git_log(source, "tester")
        commit(origin, "third.md", "feat: 클론 이후 커밋")

        after, _ = embedding._collect_git_log(source, "tester")

        assert commit_count(after) == commit_count(before) + 1
        assert "feat: 클론 이후 커밋" in "".join(d.page_content for d in after)

    def test_다른_브랜치의_커밋도_들어온다(self, source, origin):
        """--all — main 에 병합되지 않은 브랜치의 작업도 그날 한 일이다."""
        git("checkout", "-q", "-b", "side", cwd=origin)
        commit(origin, "side.md", "feat: 곁가지 작업")
        git("checkout", "-q", "main", cwd=origin)

        docs, _ = embedding._collect_git_log(source, "tester")

        assert "feat: 곁가지 작업" in "".join(d.page_content for d in docs)

    def test_옛_mirror_클론은_자동_전환된다(self, source, origin, data_dir):
        """--mirror 로 받아둔 저장소가 남아 있어도 지금 형태로 다시 받는다."""
        repo = repo_path(data_dir)
        repo.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "-q", "--mirror", str(origin), str(repo))
        assert git("-C", str(repo), "rev-parse", "--is-bare-repository").strip() == "true"

        docs, _ = embedding._collect_git_log(source, "tester")

        assert git("-C", str(repo), "rev-parse", "--is-bare-repository").strip() == "false"
        assert embedding._is_partial_clone(repo)
        assert commit_count(docs) == 2


class TestDailyGrouping:
    """커밋을 날짜별로 묶는다. 조회가 커밋 메타데이터만 읽으므로 파일 기반
    판별(merge·빈 커밋 제외, 집중 영역 집계)은 하지 않는다."""

    def test_날짜별로_문서가_하나씩_생긴다(self, source, origin):
        commit(origin, "a.md", "feat: 어제 일", date="2026-01-01T10:00:00")
        commit(origin, "b.md", "feat: 오늘 일 1", date="2026-01-02T10:00:00")
        commit(origin, "c.md", "feat: 오늘 일 2", date="2026-01-02T11:00:00")

        docs, _ = embedding._collect_git_log(source, "tester")
        by_date = {d.metadata["date"]: d for d in docs}

        assert by_date["2026-01-01"].metadata["commit_count"] == 1
        assert by_date["2026-01-02"].metadata["commit_count"] == 2
        assert "feat: 오늘 일 1" in by_date["2026-01-02"].page_content
        assert "feat: 오늘 일 2" in by_date["2026-01-02"].page_content

    def test_하루_안에서는_시간순으로_적는다(self, source, origin):
        commit(origin, "a.md", "feat: 먼저", date="2026-01-02T10:00:00")
        commit(origin, "b.md", "feat: 나중", date="2026-01-02T11:00:00")

        docs, _ = embedding._collect_git_log(source, "tester")
        body = next(d for d in docs if d.metadata["date"] == "2026-01-02").page_content

        assert body.index("feat: 먼저") < body.index("feat: 나중")

    def test_merge_커밋도_그대로_들어온다(self, source, origin):
        """조회가 파일 목록을 읽지 않으므로 merge 를 가려낼 근거가 없다.

        merge 메시지("Merge branch ...")가 하루 요약의 '한 일'에 섞인다.
        되살리려면 --pretty 에 %P 를 넣어 부모가 둘인 커밋을 걸러야 한다.
        """
        git("checkout", "-q", "-b", "side", cwd=origin)
        commit(origin, "side.md", "feat: 곁가지")
        git("checkout", "-q", "main", cwd=origin)
        git("merge", "-q", "--no-ff", "-m", "Merge side into main", "side", cwd=origin)

        docs, skipped = embedding._collect_git_log(source, "tester")
        body = "".join(d.page_content for d in docs)

        assert "Merge side into main" in body
        assert "feat: 곁가지" in body
        assert "merge" not in skipped

    def test_빈_커밋도_그대로_들어온다(self, source, origin):
        """변경 없는 커밋(--allow-empty)을 가려내려면 파일 목록이 필요하다."""
        git("commit", "-q", "--allow-empty", "-m", "chore: 빈 커밋", cwd=origin)

        docs, skipped = embedding._collect_git_log(source, "tester")

        assert "chore: 빈 커밋" in "".join(d.page_content for d in docs)
        assert "empty" not in skipped
        assert commit_count(docs) == 3  # 원래 2건 + 빈 커밋 1건

    def test_제외_사유는_날짜_없음만_남는다(self, source, origin):
        """C5 — 버릴 때는 사유와 함께 센다. 지금 버리는 것은 날짜 없는 커밋뿐이다."""
        git("commit", "-q", "--allow-empty", "-m", "chore: 빈 커밋 1", cwd=origin)
        git("commit", "-q", "--allow-empty", "-m", "chore: 빈 커밋 2", cwd=origin)

        docs, skipped = embedding._collect_git_log(source, "tester")

        assert skipped == {}
        assert commit_count(docs) == 4

    def test_원본_커밋과_대조할_수_있다(self, source, origin):
        """metadata 의 sha 목록으로 유실 여부를 검산할 수 있어야 한다."""
        docs, _ = embedding._collect_git_log(source, "tester")

        stored = {s for d in docs for s in d.metadata["commit_shas"].split(",")}
        truth = {line[:8] for line in git("log", "--pretty=format:%H", cwd=origin).split()}

        assert stored == truth

    def test_본문은_커밋_메시지뿐이다(self, source, origin):
        """파일 경로는 조회 자체가 읽지 않으므로 문서에 남지 않는다."""
        (origin / "src").mkdir()
        (origin / "src" / "a.md").write_text("a", encoding="utf-8")
        git("add", "-A", cwd=origin)
        git("commit", "-q", "-m", "feat: src 작업", cwd=origin)

        docs, _ = embedding._collect_git_log(source, "tester")
        body = "".join(d.page_content for d in docs)

        assert "feat: src 작업" in body
        assert "집중 영역:" not in body
        assert "src/a.md" not in body

    def test_작성자_메일은_본문과_메타데이터에_남지_않는다(self, source, origin):
        """%ae 를 읽되 싣지는 않는다 — 같은 사람이 주소마다 갈라지기 때문."""
        docs, _ = embedding._collect_git_log(source, "tester")

        assert docs[0].metadata["author"] == "tester"
        assert "test@example.com" not in docs[0].page_content
        assert "test@example.com" not in str(docs[0].metadata)

    def test_하루_요약은_청크로_쪼개지_않는다(self, source, origin):
        """제목 줄과 '집중 영역'이 본문에서 떨어지면 고아 청크가 된다."""
        for i in range(60):
            commit(origin, f"f{i}.md", f"feat: 커밋 {i} " + "긴 메시지 " * 8)

        docs, _ = embedding._collect_git_log(source, "tester")
        chunks = embedding._split_documents(docs)

        assert len(docs[0].page_content) > 2000  # 분할 기준을 넘겼는데도
        assert len(chunks) == len(docs)          # 쪼개지지 않는다


class TestGitFilesSync:
    """git 타입 — 파일을 읽어야 하므로 작업 트리를 유지한다."""

    @pytest.fixture
    def source(self, origin: Path):
        return types.SimpleNamespace(
            id=2, name="testrepo", location=str(origin), type=SourceType.GIT
        )

    def test_작업_트리를_유지한다(self, source, data_dir):
        embedding._collect_git_files(source, "tester")
        repo = repo_path(data_dir)

        assert git("-C", str(repo), "rev-parse", "--is-bare-repository").strip() == "false"
        assert (repo / "first.md").exists()

    def test_클론_이후의_문서가_재수집에_들어온다(self, source, origin):
        before, _ = embedding._collect_git_files(source, "tester")
        commit(origin, "third.md", "docs: 새 문서")

        after, _ = embedding._collect_git_files(source, "tester")

        assert len(after) == len(before) + 1
        assert "third.md" in {d.metadata["file_path"] for d in after}

    def test_bare_로_받아둔_저장소는_작업_트리를_되찾는다(self, source, origin, data_dir):
        repo = repo_path(data_dir)
        repo.parent.mkdir(parents=True, exist_ok=True)
        git("clone", "-q", "--mirror", str(origin), str(repo))

        embedding._collect_git_files(source, "tester")

        assert (repo / "first.md").exists()
