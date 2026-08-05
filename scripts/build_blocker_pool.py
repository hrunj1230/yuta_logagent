"""
「막힌 것」 분모 풀 생성

일지 평가의 분모 — 그날 원자료에 실제로 있던 막힌 지점의 개수 — 를 한 번 계산해
파일로 고정한다. 채점할 때마다 LLM에게 다시 물으면 같은 자료인데도 6~10개 사이로
답이 흔들려, 일지를 고치지 않아도 점수가 30%p씩 움직인다.

여러 모델의 결과를 합집합으로 모으는 이유는 TREC 풀링과 같다. 한 모델이 만든
목록으로 채점하면 그 모델의 관점이 곧 정답이 되어 자기 자신에게 유리해진다.
여러 시스템의 결과를 모아 풀을 만들면 특정 시스템에 치우치지 않는다.

중복 병합에는 로컬 임베딩 모델을 쓴다("코랩이 느림"과 "코랩 실행 속도 느림"은
같은 항목). 로컬이라 호출 비용이 없다.

생성된 파일은 사람이 열어 고칠 수 있다. LLM은 예정된 과제나 소감을 막힌 것으로
세는 경향이 있으므로, 분모가 큰 날 위주로 검토하는 편이 좋다.

사용법:
    uv run python -m scripts.build_blocker_pool alex
    uv run python -m scripts.build_blocker_pool alex --dates 2026-06-22
    uv run python -m scripts.build_blocker_pool alex --models claude-haiku-4-5
"""
import json
import sys
from pathlib import Path

import anthropic
import numpy as np
from dotenv import load_dotenv

from src import llm_router

load_dotenv()

LOGS = Path("logs")

# 풀에 기여할 모델들. 비교 대상 세 모델을 모두 넣어 어느 하나에 치우치지 않게 한다.
POOL_MODELS = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"]

# 코사인 유사도가 이보다 높으면 같은 항목으로 본다.
# 실측으로 정했다 — 합쳐야 할 쌍은 0.64~0.80, 합치면 안 될 쌍은 0.12~0.28에
# 분포해 그 사이가 넓게 비어 있다. 0.60은 그 빈 구간의 아래쪽이다.
MERGE_THRESHOLD = 0.60

SCHEMA = {
    "type": "object",
    "properties": {
        "blockers": {
            "type": "array",
            "items": {"type": "string", "description": "짧은 한 구절"},
        }
    },
    "required": ["blockers"],
    "additionalProperties": False,
}

SYSTEM = """자료에서 **막힌 지점**만 뽑아라.

막힌 지점이란:
- 스스로 표시한 의문이나 오류 (`???`, "헛점", "매끄럽지 않다", "모르겠다")
- 답을 얻지 못한 채 남긴 질문
- 잘 안 되거나 불편해서 언급한 것
- 미해결로 남긴 판단

막힌 지점이 아닌 것 — 뽑지 마라:
- 앞으로 할 일, 예정된 과제, 커리큘럼 ("~할 예정", "다음 주 ~")
- 배운 내용의 요약
- 소감이나 다짐 ("열심히 하자", "개념이 쏟아진다")
- 단순 일정

각 항목은 자료의 표현을 살려 짧은 한 구절로 쓴다. 없으면 빈 배열을 반환한다."""


def extract(client, model: str, source: str) -> list[str]:
    """모델 하나가 원자료에서 막힌 지점을 뽑는다."""
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": source}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(str(response.stop_details))
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["blockers"]


def merge(candidates: list[tuple[str, str]]) -> list[dict]:
    """
    (모델, 항목) 목록을 의미가 같은 것끼리 묶는다.

    로컬 임베딩으로 코사인 유사도를 재어 가까운 것끼리 합친다.
    같은 항목을 몇 개 모델이 찾았는지(support)를 함께 남겨, 사람이 검토할 때
    한 모델만 찾은 항목을 의심해 볼 수 있게 한다.
    """
    if not candidates:
        return []

    texts = [text for _, text in candidates]
    vectors = np.array(llm_router.embedding_function.embed_documents(texts))
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    groups: list[list[int]] = []
    for i in range(len(texts)):
        for group in groups:
            if float(vectors[i] @ vectors[group[0]]) >= MERGE_THRESHOLD:
                group.append(i)
                break
        else:
            groups.append([i])

    merged = []
    for group in groups:
        members = [candidates[i] for i in group]
        # 대표 문구는 가장 짧은 것 — 군더더기가 적다
        text = min((t for _, t in members), key=len)
        models = sorted({m for m, _ in members})
        merged.append({"text": text, "support": len(models), "found_by": models,
                       "variants": sorted({t for _, t in members if t != text})})

    # 여러 모델이 찾은 항목을 위로 — 검토할 때 신뢰도 순으로 보이도록
    return sorted(merged, key=lambda x: (-x["support"], x["text"]))


def main(user_id: str, only: list[str] | None = None, models: list[str] | None = None) -> int:
    models = models or POOL_MODELS
    gen_dir = LOGS / user_id

    sources = sorted(gen_dir.glob("*.sources.json"))
    dates = [s.name.removesuffix(".sources.json") for s in sources]
    if only:
        dates = [d for d in dates if d in only]
    if not dates:
        print("❌ 대상 날짜가 없습니다.")
        return 1

    client = anthropic.Anthropic()
    print(f"🏊 풀 생성: {len(dates)}일 × 모델 {len(models)}개 = {len(dates) * len(models)}회 호출")
    print(f"   기여 모델: {', '.join(models)}\n")

    for n, date in enumerate(dates, 1):
        chunks = json.loads((gen_dir / f"{date}.sources.json").read_text(encoding="utf-8"))["chunks"]
        source = "\n\n".join(c["text"] for c in chunks)

        candidates: list[tuple[str, str]] = []
        per_model = {}
        for model in models:
            try:
                found = extract(client, model, source)
            except Exception as e:
                print(f"  [{n:2d}/{len(dates)}] {date}  ⚠️ {model} 실패: {e}")
                found = []
            per_model[model] = len(found)
            candidates += [(model, t.strip()) for t in found if t.strip()]

        merged = merge(candidates)
        consensus = sum(1 for m in merged if m["support"] >= 2)

        (gen_dir / f"{date}.blockers.json").write_text(
            json.dumps({
                "date": date,
                "blockers": merged,
                "pooled_from": models,
                "note": "사람이 검토해 수정할 수 있음. 항목을 지우면 분모가 줄어든다.",
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        raw = " ".join(f"{m.split('-')[1][:2]}:{c}" for m, c in per_model.items())
        print(f"  [{n:2d}/{len(dates)}] {date}  원시 {raw}  →  병합 {len(merged)}개"
              f" (2개 이상 모델 합의 {consensus}개)")

    print(f"\n✅ {len(dates)}개 파일 생성 → {gen_dir}/*.blockers.json")
    print("   검토: uv run python -m scripts.build_blocker_pool review " + user_id)
    return 0


def review(user_id: str, top: int = 10) -> int:
    """분모가 큰 날부터 보여준다. 사람이 오탐을 골라내기 위한 화면."""
    files = sorted((LOGS / user_id).glob("*.blockers.json"))
    if not files:
        print("❌ 풀 파일이 없습니다. 먼저 생성하세요.")
        return 1

    days = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        days.append((len(data["blockers"]), data))

    total = sum(n for n, _ in days)
    solo = sum(1 for _, d in days for b in d["blockers"] if b["support"] == 1)
    print(f"전체 {len(days)}일 · 항목 {total}개 · 한 모델만 찾은 항목 {solo}개 "
          f"({solo / total:.0%} — 오탐 의심 대상)\n")

    for n, data in sorted(days, key=lambda x: -x[0])[:top]:
        print(f"━━ {data['date']} · {n}개 ━━")
        for b in data["blockers"]:
            mark = "✓" if b["support"] >= 2 else "?"
            print(f"  {mark} [{b['support']}/{len(data['pooled_from'])}] {b['text']}")
        print()
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "review":
        sys.exit(review(sys.argv[2] if len(sys.argv) > 2 else "alex"))

    user = sys.argv[1]
    only = sys.argv[sys.argv.index("--dates") + 1].split(",") if "--dates" in sys.argv else None
    mods = sys.argv[sys.argv.index("--models") + 1].split(",") if "--models" in sys.argv else None
    sys.exit(main(user, only, mods))
