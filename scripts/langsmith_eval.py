"""
LangSmith 일지 품질 평가

구조:
    Dataset    = 기준 일지 (logs/<user>-reference/) — 사람이 쓴 정답
    Experiment = 모델이 생성한 일지 — Dataset에 target 함수를 돌린 결과
    Evaluator  = 기준·원자료와 대조해 점수를 매기는 함수

지표:
    coverage      기준 일지의 용어 중 생성 일지가 담아낸 비율 (누락 탐지)
    grounded      생성 일지의 용어 중 원자료에 근거가 있는 비율 (환각 탐지)
    length_ratio  기준 대비 분량. 1보다 크게 벗어나면 늘려 쓴 것

세 지표 모두 코드로 계산한다 — LLM judge를 쓰지 않으므로 몇 번을 돌려도
토큰 비용이 없고 결과가 항상 같다.

사용법:
    uv run python -m scripts.langsmith_eval upload alex          # Dataset 생성/갱신
    uv run python -m scripts.langsmith_eval run alex             # 현재 모델로 Experiment
    uv run python -m scripts.langsmith_eval run alex --model claude-sonnet-5
    uv run python -m scripts.langsmith_eval local alex           # LangSmith 없이 콘솔 출력
"""
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LOGS = Path("logs")
DATASET_SUFFIX = "-journal-eval"

# 기술 용어로 볼 만한 토큰만 뽑는다.
# 영문/숫자 토큰(vLLM, FAISS, Next.js, HNSW …)과 한글 2글자 이상 덩어리.
_TERM = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{1,}|[가-힣]{2,}")

# 조사·접속사처럼 어디에나 나오는 말은 지표를 흐린다
STOPWORDS = {
    "그리고", "하지만", "때문", "위해", "통해", "대한", "관련", "정리", "학습", "확인",
    "오늘", "내용", "부분", "경우", "다음", "이번", "사용", "진행", "생각", "이해",
    "것이", "있다", "없다", "한다", "된다", "같은", "라는", "에서", "으로", "이라고",
    "the", "and", "for", "with", "that", "this", "from", "was", "are",
}

# 한국어는 교착어라 같은 말이 조사·어미를 달고 여러 형태로 나온다.
# "개념"/"개념을"/"개념이" 를 다른 용어로 세면 지표가 노이즈에 묻힌다.
_SUFFIXES = (
    "으로는", "에서는", "이라고", "으로써", "으로서", "에게서", "까지", "부터", "에서",
    "에게", "으로", "이라", "라고", "처럼", "보다", "만큼", "하고", "이며", "이고",
    "하는", "했다", "한다", "된다", "되는", "했고", "하여", "하고", "이다", "입니다",
    "들이", "들을", "들의", "들은", "를", "을", "이", "가", "은", "는", "의", "에",
    "와", "과", "도", "만", "로", "라", "고", "들", "적", "함",
)


def _stem(token: str) -> str:
    """한글 토큰에서 흔한 조사·어미를 떼어 낸다 (형태소 분석기 없이 쓰는 근사)."""
    if not token or not ("가" <= token[0] <= "힣"):
        return token
    for suffix in _SUFFIXES:
        if len(token) > len(suffix) + 1 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def terms(text: str) -> set[str]:
    """비교에 쓸 용어 집합을 뽑는다."""
    found = {_stem(t.lower().strip(".-+_")) for t in _TERM.findall(text or "")}
    return {t for t in found if len(t) >= 2 and t not in STOPWORDS}


# 원자료에서 "막힌 지점"을 나타내는 표시.
# 일지 기준의 2번 항목(막힌 것)이 실제로 잡혔는지 확인하는 데 쓴다.
_BLOCKER = re.compile(r"\?{2,}|헛점|허점|매끄럽지|모르겠|불명확|헷갈")

# 커밋 메시지에서 conventional commit 접두어를 떼고 내용만 남긴다
_COMMIT_LINE = re.compile(r"^\[\d{4}-\d{2}-\d{2}\]\s*(?:\w+:\s*)?(.+)$", re.MULTILINE)


def find_blockers(source: str, date: str | None = None, user_id: str | None = None,
                  min_support: int = 1) -> list[str]:
    """
    그날의 막힌 지점 목록(= 채점의 분모)을 돌려준다.

    우선 build_blocker_pool.py 가 만들어 둔 풀 파일을 읽는다. 풀은 여러 모델의
    결과를 합쳐 한 번 만들고 고정한 것이라, 몇 번을 채점해도 분모가 같다.
    채점할 때마다 LLM에게 물으면 같은 자료인데도 6~10개 사이로 흔들려
    일지를 고치지 않아도 점수가 30%p씩 움직인다.

    풀 파일이 없으면 정규식으로 후퇴한다. 정규식은 `???`나 "헛점" 같은 표시가
    붙은 것만 세므로 대부분의 날에서 0개가 나온다 — 어디까지나 임시방편이다.

    min_support: 몇 개 모델이 찾은 항목까지 분모에 넣을지. 1이면 전부,
                 2면 한 모델만 찾은 항목(오탐 의심)을 제외한다.
    """
    if date and user_id:
        pool = LOGS / user_id / f"{date}.blockers.json"
        if pool.exists():
            data = json.loads(pool.read_text(encoding="utf-8"))
            return [b["text"] for b in data["blockers"] if b["support"] >= min_support]

    return [line.strip() for line in (source or "").splitlines() if _BLOCKER.search(line)]


def find_commits(chunks: list[dict]) -> list[str]:
    """커밋 청크에서 커밋 메시지 본문만 뽑는다."""
    messages = []
    for c in chunks:
        if c.get("type") == "git_log":
            messages += _COMMIT_LINE.findall(c["text"])
    return messages


def _hit(needle_terms: set[str], haystack: str, threshold: float = 0.4) -> bool:
    """needle의 용어 중 threshold 이상이 haystack에 등장하면 반영된 것으로 본다."""
    if not needle_terms:
        return True
    found = sum(1 for t in needle_terms if t in haystack)
    return found / len(needle_terms) >= threshold


def score(candidate: str, source: str, chunks: list[dict],
          date: str | None = None, user_id: str | None = None,
          min_support: int = 1) -> dict:
    """
    생성 일지를 **원자료**와 대조해 점수를 낸다.

    기준 일지와 비교하지 않는 이유: 일지는 요약이므로 정답이 하나가 아니다.
    사람이 쓴 문장과 용어가 겹치는지를 재면 문체 차이가 점수로 둔갑한다.
    대신 기준 문서가 "반드시 담으라"고 정한 것만 원자료에서 찾아 확인한다.
    """
    low = candidate.lower()

    # ① 커밋 반영 — 그날 커밋한 내용이 일지에 나타나는가
    commits = find_commits(chunks)
    commit_hits = [m for m in commits if _hit(terms(m), low)]
    commit_score = len(commit_hits) / len(commits) if commits else 1.0

    # ② 막힌 것 반영 — 그날의 막힌 지점이 일지에 나타나는가 (분모는 고정된 풀)
    blockers = find_blockers(source, date, user_id, min_support)
    blocker_hits = [b for b in blockers if _hit(terms(b), low, threshold=0.3)]
    blocker_score = len(blocker_hits) / len(blockers) if blockers else 1.0

    # ③ 환각 — 일지의 영문/기술 용어 중 원자료에 없는 것
    source_flat = (source or "").lower()
    cand_en = {t for t in terms(candidate) if t[0].isascii()}
    invented_en = sorted(t for t in cand_en if t not in source_flat)
    hallucination = len(invented_en) / len(cand_en) if cand_en else 0.0

    return {
        "commit_captured": round(commit_score, 3),
        "blocker_captured": round(blocker_score, 3),
        "hallucination": round(hallucination, 3),
        "length": len(candidate),
        "commits_total": len(commits),
        "blockers_total": len(blockers),
        "blockers_missed": [b[:60] for b in blockers if b not in blocker_hits],
        "invented_en": invented_en,
    }


def load_pairs(user_id: str) -> list[dict]:
    """
    원자료가 있는 모든 날짜를 모은다.

    채점은 원자료만으로 하므로 기준 일지는 필수가 아니다. 있으면 사람이
    비교해 볼 참고용으로 함께 싣는다.
    """
    ref_dir = LOGS / f"{user_id}-reference"
    gen_dir = LOGS / user_id

    pairs = []
    for sources in sorted(gen_dir.glob("*.sources.json")):
        date = sources.name.removesuffix(".sources.json")
        chunks = json.loads(sources.read_text(encoding="utf-8"))["chunks"]
        reference = ref_dir / f"{date}.md"
        pairs.append({
            "date": date,
            "source_text": "\n\n".join(c["text"] for c in chunks),
            "chunks": chunks,
            "reference": reference.read_text(encoding="utf-8") if reference.exists() else "",
        })
    return pairs


# ---------- LangSmith ----------

def upload(user_id: str) -> int:
    """기준 일지를 Dataset으로 올린다 (이미 있으면 예시만 채운다)."""
    from langsmith import Client

    pairs = load_pairs(user_id)
    if not pairs:
        print("❌ 기준 일지가 없습니다. logs/<user>-reference/ 에 먼저 작성하세요.")
        return 1

    client = Client()
    name = f"{user_id}{DATASET_SUFFIX}"

    if client.has_dataset(dataset_name=name):
        dataset = client.read_dataset(dataset_name=name)
        existing = {e.inputs.get("date") for e in client.list_examples(dataset_id=dataset.id)}
        print(f"📁 기존 Dataset 사용: {name} (예시 {len(existing)}개)")
    else:
        dataset = client.create_dataset(
            dataset_name=name,
            description=f"{user_id}의 일지 생성 품질 평가 — 기준 일지는 사람이 작성",
        )
        existing = set()
        print(f"📁 Dataset 생성: {name}")

    new = [p for p in pairs if p["date"] not in existing]
    if new:
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    # user_id를 함께 실어야 evaluator가 그날의 분모 풀 파일을 찾을 수 있다
                    "inputs": {"date": p["date"], "chunks": p["chunks"], "user_id": user_id},
                    "outputs": {"journal": p["reference"], "source_text": p["source_text"]},
                }
                for p in new
            ],
        )
        print(f"➕ 예시 {len(new)}개 추가: {', '.join(p['date'] for p in new)}")
    else:
        print("변경 없음 (모든 날짜가 이미 등록됨)")

    print(f"\n✅ https://smith.langchain.com → Datasets → {name}")
    return 0


def _evaluators():
    """LangSmith evaluator 4종. 모두 코드 기반이라 호출 비용이 없고 결과가 항상 같다."""
    def _score(outputs, inputs, reference_outputs):
        return score(
            outputs.get("journal", ""),
            reference_outputs.get("source_text", ""),
            inputs.get("chunks", []),
            date=inputs.get("date"),
            user_id=inputs.get("user_id"),
        )

    def commit_captured(outputs, inputs, reference_outputs):
        s = _score(outputs, inputs, reference_outputs)
        return {"key": "commit_captured", "score": s["commit_captured"],
                "comment": f"커밋 {s['commits_total']}건 중 반영"}

    def blocker_captured(outputs, inputs, reference_outputs):
        s = _score(outputs, inputs, reference_outputs)
        missed = "; ".join(s["blockers_missed"][:3])
        return {"key": "blocker_captured", "score": s["blocker_captured"],
                "comment": f"막힌 지점 {s['blockers_total']}건. 놓침: {missed or '없음'}"}

    def not_hallucinated(outputs, inputs, reference_outputs):
        s = _score(outputs, inputs, reference_outputs)
        return {"key": "not_hallucinated", "score": round(1 - s["hallucination"], 3),
                "comment": f"원자료에 없는 용어: {', '.join(s['invented_en'][:8]) or '없음'}"}

    # 길이는 점수로 매기지 않는다.
    # 길이만 정확히 측정돼 감점되고 추가로 잡아낸 항목은 분모에 없으면 반영되지 않아,
    # "측정 가능한 것만 벌하는" 비대칭이 생겼다. 참고값으로만 남긴다.
    def length(outputs, inputs, reference_outputs):
        return {"key": "length", "score": None,
                "comment": f"{len(outputs.get('journal', ''))}자"}

    return [commit_captured, blocker_captured, not_hallucinated, length]


def run(user_id: str, model: str | None = None) -> int:
    """Dataset에 대해 일지를 새로 생성하고 평가한다 (= Experiment 한 번)."""
    import anthropic
    from langsmith import Client

    from src.llm_router import ANTHROPIC_MODEL
    from scripts.generate_journals import SYSTEM, build_prompt

    model = model or ANTHROPIC_MODEL
    client = Client()
    llm = anthropic.Anthropic()

    def target(inputs: dict) -> dict:
        # Sonnet 5 / Opus 5는 thinking이 기본으로 켜져 있고 max_tokens가
        # thinking + 응답을 합쳐 제한하므로 여유를 크게 준다.
        response = llm.messages.create(
            model=model,
            max_tokens=12000,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(inputs["date"], inputs["chunks"])}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(str(response.stop_details))
        text = next(b.text for b in response.content if b.type == "text")
        return {"journal": text}

    print(f"🧪 Experiment 실행: {model}")
    results = client.evaluate(
        target,
        data=f"{user_id}{DATASET_SUFFIX}",
        evaluators=_evaluators(),
        experiment_prefix=model,
        metadata={"model": model},
    )
    print(f"\n✅ 완료 — LangSmith에서 실험끼리 나란히 비교하세요")
    print(f"   https://smith.langchain.com → Datasets → {user_id}{DATASET_SUFFIX} → Experiments")
    return 0


# ---------- LangSmith 없이 ----------

def local(user_id: str, variant: str | None = None) -> int:
    """
    생성된 일지를 원자료와 대조해 콘솔에 출력한다.

    variant를 주면 logs/<variant>/ 를 대신 읽는다 (예: alex-v1, alex-reference).
    """
    read_dir = LOGS / (variant or user_id)
    dates = sorted(p.stem for p in (LOGS / user_id).glob("*.md"))
    if not dates:
        print("❌ 평가할 일지가 없습니다.")
        return 1

    print(f"📂 대상: {read_dir}/\n")
    print(f"{'날짜':<12} {'커밋반영':>8} {'막힌것':>8} {'환각없음':>8} {'길이':>6}")
    print("-" * 100)

    totals = {"commit": 0.0, "blocker": 0.0, "clean": 0.0, "length": 0}
    n = 0

    for date in dates:
        journal = read_dir / f"{date}.md"
        sources = LOGS / user_id / f"{date}.sources.json"
        if not journal.exists() or not sources.exists():
            continue

        chunks = json.loads(sources.read_text(encoding="utf-8"))["chunks"]
        source_text = "\n\n".join(c["text"] for c in chunks)
        s = score(journal.read_text(encoding="utf-8"), source_text, chunks,
                  date=date, user_id=user_id)

        n += 1
        totals["commit"] += s["commit_captured"]
        totals["blocker"] += s["blocker_captured"]
        totals["clean"] += 1 - s["hallucination"]
        totals["length"] += s["length"]

        flag = "  ⚠️" if s["blocker_captured"] < 1.0 and s["blockers_total"] else ""
        print(f"{date:<12} {s['commit_captured']:>8.0%} {s['blocker_captured']:>8.0%}"
              f" {1 - s['hallucination']:>8.0%} {s['length']:>6}{flag}")
        if s["blockers_missed"]:
            print(f"{'':>13}↳ 놓친 막힌 지점: {' / '.join(s['blockers_missed'][:2])}")
        if s["invented_en"]:
            print(f"{'':>13}↳ 원자료에 없는 용어: {', '.join(s['invented_en'][:8])}")

    print("-" * 100)
    print(f"{'평균':<12} {totals['commit']/n:>8.0%} {totals['blocker']/n:>8.0%}"
          f" {totals['clean']/n:>8.0%} {totals['length']//n:>6}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    command, user = sys.argv[1], sys.argv[2]
    model_arg = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else None

    if command == "upload":
        sys.exit(upload(user))
    if command == "run":
        sys.exit(run(user, model_arg))
    if command == "local":
        variant = sys.argv[sys.argv.index("--dir") + 1] if "--dir" in sys.argv else None
        sys.exit(local(user, variant))

    print(f"알 수 없는 명령: {command}")
    sys.exit(1)
