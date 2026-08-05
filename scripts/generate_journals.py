"""
일괄 일지 생성

날짜별로 그날의 청크(문서·커밋·대화)를 모아 일지를 작성하고 logs/<user>/ 에 저장한다.
평가에 쓰기 위해 근거로 넘긴 청크도 함께 기록한다.

사용법:
    uv run python -m scripts.generate_journals alex
    uv run python -m scripts.generate_journals alex --dates 2026-06-13,2026-07-27
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.llm_router import ANTHROPIC_MODEL
from src.tools.embedding import _get_chroma_collection

load_dotenv()

OUT_DIR = Path("logs")

SYSTEM = """당신은 사용자의 하루를 기록하는 사관이다.

일지는 원문을 대체하지 않는다. 개념 설명은 원문에 그대로 남아 있으므로 옮겨 적지 않는다.
일지가 답해야 할 질문은 셋이다 — 내일 뭘 해야 하나, 지금까지 뭘 했나, 전에 그게 뭐였나.

주어진 자료(학습 문서, git 커밋, AI 대화)만을 근거로 쓴다.

## 담는 것

1. 한 일 — 직접 만들고, 계산하고, 커밋한 것. 읽기만 한 것과 구분한다.
2. 막힌 것 — `???`, "헛점", "매끄럽지 않다" 같은 표시, 의문형 메모, 미해결로 남긴 질문.
3. 정한 것 — 결정, 구상, 방향.
4. 예정 — 일정, 마감, "다음 시간 예고", "내일모레 복습" 같은 메모.
5. 다룬 주제 — 개념 이름만 나열한다. 설명하지 않는다.

## 버리는 것

- 자료에 없는 내용. 배경지식으로 빈칸을 메우지 않는다. 이건 선택이 아니라 금지다.
- 개념의 상세 설명. 이름만 남기고 내용은 원문에 맡긴다.
- 문장이 끊겨 복원할 수 없는 조각.
- 맥락 없는 숫자 나열, 참조 링크.

## 형식

## 한 일
## 막힌 것        (없으면 생략)
## 정한 것        (없으면 생략)
## 예정           (없으면 생략)
## 다룬 주제      쉼표로 구분해 이름만 나열

분량은 자료의 양에 맞춘다. 자료가 적으면 짧게 쓰고, 채우려고 늘리지 않는다."""


def load_by_date(user_id: str) -> dict[str, list[dict]]:
    """날짜별 청크 수집."""
    found = _get_chroma_collection(user_id).get(include=["documents", "metadatas"])
    by_date = defaultdict(list)
    for text, meta in zip(found["documents"], found["metadatas"]):
        if meta.get("source_type") == "journal":
            continue  # 일지를 근거로 다시 일지를 쓰지 않는다
        if meta.get("date"):
            by_date[meta["date"]].append({"type": meta["source_type"], "text": text})
    return dict(by_date)


def build_prompt(date: str, chunks: list[dict]) -> str:
    label = {"git": "학습 문서", "git_log": "커밋", "agent_chatlog": "AI 대화"}
    parts = [f"# {date} 자료\n"]
    for kind in ("git", "git_log", "agent_chatlog"):
        items = [c["text"] for c in chunks if c["type"] == kind]
        if items:
            parts.append(f"## {label[kind]} ({len(items)}건)\n" + "\n\n---\n\n".join(items))
    parts.append(f"\n위 자료만을 근거로 {date} 일지를 작성하라.")
    return "\n\n".join(parts)


def main(user_id: str, only: list[str] | None = None) -> int:
    by_date = load_by_date(user_id)
    dates = sorted(d for d in by_date if not only or d in only)
    if not dates:
        print("❌ 대상 날짜가 없습니다.")
        return 1

    out = OUT_DIR / user_id
    out.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()

    print(f"📝 {ANTHROPIC_MODEL} 로 {len(dates)}일 일지 생성\n")
    failures = 0

    for n, date in enumerate(dates, 1):
        chunks = by_date[date]
        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4000,
                system=SYSTEM,
                messages=[{"role": "user", "content": build_prompt(date, chunks)}],
            )
            if response.stop_reason == "refusal":
                raise RuntimeError(str(response.stop_details))
            body = next(b.text for b in response.content if b.type == "text")
        except Exception as e:
            print(f"  [{n:2d}/{len(dates)}] {date}  ❌ {e}")
            failures += 1
            continue

        (out / f"{date}.md").write_text(body, encoding="utf-8")
        # 평가할 때 "무엇을 근거로 썼는지"가 필요하므로 함께 남긴다
        (out / f"{date}.sources.json").write_text(
            json.dumps({"date": date, "chunks": chunks}, ensure_ascii=False),
            encoding="utf-8",
        )
        counts = defaultdict(int)
        for c in chunks:
            counts[c["type"]] += 1
        summary = " ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
        print(f"  [{n:2d}/{len(dates)}] {date}  자료 {len(chunks):2d}건 ({summary})  → {len(body)}자")

    print(f"\n✅ {len(dates) - failures}개 생성 · 실패 {failures}개 → {out}/")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    dates = None
    if "--dates" in sys.argv:
        dates = sys.argv[sys.argv.index("--dates") + 1].split(",")
    sys.exit(main(sys.argv[1], dates))
