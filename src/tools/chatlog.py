"""
에이전트 대화 로그 수집 모듈

Claude Code 는 세션마다 JSONL 트랜스크립트를 남긴다. 한 프로젝트의 트랜스크립트는
쉽게 수십 MB 가 되지만, 그 대부분은 도구 호출·도구 결과·thinking 이라 일지에 쓸
것이 없다. 실측하면 19MB 짜리 프로젝트에서 사람이 실제로 친 말은 17KB, 전체의
1% 도 되지 않는다.

이 모듈은 사람의 발화만 걸러 날짜별로 묶는다. 일지가 알아야 할 것 — 무엇을 물었고,
무엇을 정했고, 어디서 막혔는지 — 는 사람이 친 말에 담겨 있기 때문이다.

제공 함수:
    - read_turns: 트랜스크립트 디렉토리에서 사람의 발화를 읽는다
    - daily_documents: 발화를 날짜별로 묶어 Document 로 만든다
"""
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from langchain_core.documents import Document

# 이보다 짧은 발화는 담지 않는다.
# "A", "B", "응", "그렇게 해줘" 같은 선택지 응답·맞장구는 그 자체로는 아무것도
# 말해주지 않는다. 앞선 질문이 있어야 뜻이 사는데, 질문까지 실으면 분량이 배로
# 늘면서 정작 일지에 옮길 내용은 늘지 않는다.
MIN_TURN_CHARS = 12

# 발화 하나의 상한. 로그·코드를 통째로 붙여넣는 경우가 있어 이것을 막지 않으면
# 하루치가 수십만 자가 된다. 붙여넣기의 앞부분만 있어도 무엇을 다뤘는지는 남는다.
MAX_TURN_CHARS = 600

# 사람이 친 것처럼 보이지만 실제로는 도구가 끼워 넣은 텍스트.
# 걸러내지 않으면 하루치의 대부분을 이것들이 차지한다 (실측 67%).
NOISE_PREFIXES = ("<command-name>", "<local-command", "Caveat:", "[Request interrupted")
NOISE_MARKERS = ("<system-reminder>", "<local-command-stdout>")


def _clean(text: str) -> str:
    """
    발화를 한 줄로 펴고 상한을 적용한다.

    한 줄로 펴는 이유는 문서가 '- 발화' 목록 형태이기 때문이다. 붙여넣은
    traceback 처럼 줄바꿈이 든 발화를 그대로 두면 둘째 줄부터 목록 밖으로
    흘러나와 어디까지가 한 발화인지 알 수 없게 된다.
    """
    text = " ".join(text.split())
    if len(text) <= MAX_TURN_CHARS:
        return text
    return text[:MAX_TURN_CHARS].rstrip() + " …(생략)"


def _classify(text: str) -> str | None:
    """
    발화를 담을지 판단한다.

    Returns:
        제외 사유. 담아야 하면 None.
    """
    if not text.strip():
        return "empty"
    if any(marker in text for marker in NOISE_MARKERS):
        return "system_text"
    if text.startswith(NOISE_PREFIXES):
        return "system_text"
    if len(text.strip()) < MIN_TURN_CHARS:
        return "too_short"
    return None


def read_turns(root: str | Path) -> tuple[list[dict], dict[str, int]]:
    """
    트랜스크립트 디렉토리에서 사람의 발화를 읽는다.

    제외한 것은 사유와 함께 세어 돌려준다. 조용히 버리면 "대화가 몇 건 들어왔나"를
    검산할 수 없고, 형식이 바뀌어 0건이 되어도 드러나지 않는다.

    Returns:
        (발화 목록, {제외 사유: 건수})
    """
    root = Path(root)
    turns: list[dict] = []
    skipped: dict[str, int] = {}
    seen: set[str] = set()

    def note(reason: str):
        skipped[reason] = skipped.get(reason, 0) + 1

    for path in sorted(root.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            print(f"[chatlog] 읽기 실패 {path.name}: {e}")
            note("read_failed")
            continue

        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                note("bad_json")
                continue

            if entry.get("type") != "user":
                continue

            # 같은 세션을 이어서 열면 항목이 다시 기록될 수 있으므로 uuid 로 거른다
            uid = entry.get("uuid")
            if uid and uid in seen:
                note("duplicate")
                continue
            if uid:
                seen.add(uid)

            date = (entry.get("timestamp") or "")[:10]
            message = entry.get("message") or {}
            content = message.get("content")
            blocks = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]

            for block in blocks:
                if block.get("type") != "text":
                    # 도구 결과·이미지는 사람의 말이 아니다
                    continue

                text = block.get("text") or ""
                reason = _classify(text)
                if reason:
                    note(reason)
                    continue
                if not date:
                    note("no_date")
                    continue

                turns.append({
                    "date": date,
                    "time": (entry.get("timestamp") or "")[11:16],
                    "text": _clean(text),
                    "session": entry.get("sessionId") or path.stem,
                })

    turns.sort(key=lambda t: (t["date"], t["time"]))
    return turns, skipped


def daily_documents(turns: list[dict], source, user_id: str) -> list[Document]:
    """
    발화를 날짜별로 묶어 하루당 문서 하나로 만든다.

    커밋 이력과 같은 단위로 맞춘다. 사용자가 묻는 단위가 하루이므로, 저장도 하루
    단위여야 그날 자료가 한 덩어리로 잡힌다.
    """
    by_date: dict[str, list[dict]] = defaultdict(list)
    for turn in turns:
        by_date[turn["date"]].append(turn)

    documents = []
    for date, day in sorted(by_date.items()):
        sessions = sorted({turn["session"] for turn in day})

        lines = [f"[{date}] {source.name} — 대화 {len(day)}턴", "", "나눈 이야기:"]
        lines += [f"- {turn['text']}" for turn in day]

        content = "\n".join(lines)
        documents.append(Document(
            page_content=content,
            metadata={
                "user_id": user_id,
                "source_id": source.id,
                "source_type": "agent_chatlog",
                "source_name": source.name,
                # 하루치를 통째로 교체하기 위한 키 (증분 판정이 쓰는 이름)
                "file_path": f"chat/{date}",
                "file_hash": hashlib.sha256(content.encode()).hexdigest(),
                # 원본 트랜스크립트와 대조해 유실을 검산할 수 있도록 남긴다
                "session_ids": ",".join(s[:8] for s in sessions),
                "turn_count": len(day),
                "date": date,
                "date_origin": "chatlog",
                "embedded_at": datetime.now().isoformat(),
            },
        ))

    return documents
