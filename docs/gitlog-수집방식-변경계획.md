# git_log 수집 방식 변경 — 정리와 후속 계획

> **작업자 안내:** 각 작업은 체크박스(`- [ ]`) 단위로 실행한다. 테스트를 먼저 쓰고,
> 실패를 확인한 뒤, 최소 구현으로 통과시키고, 작업 단위로 커밋한다.

**목표:** `git_log` 소스의 수집 명령이 바뀌면서 어긋난 곳을 모두 맞춘다.

**전제:** 수집·조회 명령 변경 자체는 이미 반영되어 있다(`src/tools/embedding.py`,
`tests/unit/test_sync_repo.py`). 이 문서는 **그 변경이 남긴 파급**을 다룬다.

**작성일:** 2026-08-04

---

## 1부. 무엇이 어떻게 바뀌었나

### 1.1 명령 두 줄

| 단계 | 이전 | 지금 |
|---|---|---|
| 클론 | `git clone --mirror <url> <dir>` | `git clone --filter=blob:none --no-checkout <url> <dir>` |
| 갱신 | `git fetch --prune origin` (bare) | `git fetch --prune origin` (동일) |
| 조회 | `git log --pretty=format:__C__%H\|%P\|%an\|%ad\|%s --date=short --name-only` | `git log --all --date=iso --pretty=format:"Commit: %H%nAuthor: %an <%ae>%nDate: %ad%nSubject: %s%n"` |

### 1.2 실측 (github.com/hrunj1230/yuta_logagent)

| 항목 | `--mirror` | `--filter=blob:none --no-checkout` |
|---|---|---|
| 저장소 크기 | 756K | **168K** |
| 팩 크기 | 661.21 KiB | **48.19 KiB** |
| 객체 수 | 451 | **261** |
| 체크아웃된 파일 | 0 | 0 |

수집 결과: 하루 문서 8개 / 커밋 67건 / 제외 0건.

### 1.3 두 변경이 서로를 필요로 하는 이유

`--no-checkout` 저장소는 작업 트리가 없어 `pull` 이 실패하므로 `fetch` 를 쓴다.
그런데 `fetch` 는 `refs/remotes/origin/*` 만 앞당기고 로컬 브랜치는 제자리에 둔다.
따라서 **조회가 `--all` 이 아니면 클론 이후의 커밋이 영원히 보이지 않는다.**
`test_클론_이후의_커밋이_재수집에_들어온다` 가 이 사슬을 잠근다.

`--mirror` 가 아니게 되면서 저장소는 더 이상 bare 가 아니다. 그래서 "이 저장소를
어떤 의도로 받았는가"를 bare 여부로 가릴 수 없고, `remote.origin.partialclonefilter`
설정으로 판별한다(`_is_partial_clone`). 서버가 필터를 지원하지 않아 객체를 전부
받아왔더라도 이 설정은 남으므로 로컬 origin 을 쓰는 테스트에서도 신뢰할 수 있다.

### 1.4 문서에서 사라진 것 (의도된 트레이드오프)

조회 명령이 파일 경로(`--name-only`)와 부모 목록(`%P`)을 받지 않으므로:

| 사라진 것 | 근거였던 데이터 | 결과 |
|---|---|---|
| `집중 영역: src/tools/(12) · docs/(3)` 줄 | 파일 경로 | 하루 요약 본문이 커밋 메시지만 남음 |
| merge 커밋 제외 | `%P` (부모 2개) | `Merge pull request #1 ...` 가 '한 일'에 섞임 |
| 빈 커밋 제외 | 파일 목록 비어 있음 | `--allow-empty` 커밋이 그대로 들어옴 |
| `files_changed` 메타데이터 | 파일 경로 | 키 자체를 제거 |

커밋 총합이 **64 → 67** 로 늘어난 것은 이 때문이다(merge 2 + 빈 커밋 1).
남은 제외 사유는 `no_date` 하나뿐이며, 실제로는 거의 발생하지 않는다.

`%ae`(작성자 메일)는 파싱하되 본문·메타데이터에 싣지 않는다. 같은 사람이 기기마다
다른 주소를 쓰면 한 사람이 여럿으로 갈라지기 때문이다(`_split_author`).

### 1.5 현재 문서 형태

```
[2026-08-03] livecheck — 커밋 6건

한 일:
- chore: gitignore backups/ and logs/ (real user data)
- fix: make date-based retrieval actually work
- Merge pull request #1 from hrunj1230/fix/embedding-pipeline-date-metadata
```

메타데이터: `file_path=commits/{date}`, `file_hash`, `commit_shas`, `commit_count`,
`author`, `date`, `date_origin=git`, `embedded_at`.

---

## 2부. 어긋난 곳

`- ` 로 시작하는 줄의 의미가 **"바뀐 파일" → "커밋 메시지"** 로 옮겨간 것이
파급의 근원이다. 그 줄을 읽거나 자르는 코드가 전부 어긋났다.

| 파일 | 무엇이 어긋났나 | 작업 |
|---|---|---|
| `src/tools/log.py:81,97,130` | `_shrink_commit` 이 파일 목록 대신 커밋 메시지를 자른다. `keep=0` 단계는 제목만 남긴 빈 껍데기를 만든다. `agent_chatlog` 에는 아예 적용되지 않는다 | Task 1 |
| `scripts/langsmith_eval.py:79,108` | `_COMMIT_LINE` 이 `[날짜] ...` 첫 줄을 커밋 메시지로 오인해 `livecheck — 커밋 6건` 을 뽑는다 | Task 2 |
| `scripts/seed_dummy_sources.py:166-198` | 더미 문서가 '커밋 1건 = 문서 1개' 옛 형식이라 실제 수집 결과와 다르다 | Task 3 |
| `src/tools/embedding.py:151,522` | 증분 판정이 옛 키 `commit_sha`(단수)를 아직 참조한다 | Task 4 |
| `src/unified_controller_single.py:113`<br>`docs/ARCHITECTURE.md:152,166`<br>`docs/임베딩-파이프라인-문제분석.md:14`<br>`docs/임베딩-파이프라인-작업기록.md:115` | "변경 요약", "`--numstat` 기반 요약", "파일 변경 목록부터 덜어낸다" 서술이 사실과 다르다 | Task 5 |
| `data/sources/*/`, ChromaDB | 옛 `--mirror` 저장소와 옛 형식 문서가 남아 있다 | Task 6 |

### 근거: Task 1·2 는 추측이 아니다

**Task 1** — 실제 문서에 `SHRINK_STEPS` 를 적용한 결과:

```
keep=None (2229자)   [2026-07-28] livecheck — 커밋 42건 / 한 일: / - 42줄
keep=3    (223자)    ... 3줄 + "- ... 외 39개"
keep=0    (37자)     [2026-07-28] livecheck — 커밋 42건 / (빈 줄) / 한 일:
```

`keep=0` 은 "42건 했다"만 남기고 무엇을 했는지는 지운다. 자리는 차지하면서 정보가
0 이고, 빠졌다는 사실조차 알리지 않으므로 그 날짜를 통째로 빼는 것보다 나쁘다.

축약 기능 자체는 여전히 필요하다. 하루 문서 크기는 49~2229자이고 조회 상한은
92일이므로, 바쁜 날이 이어지면 **205,068자** 로 예산(40,000자)을 5배 넘긴다.

**Task 2** — 현재 정규식을 두 형식에 돌린 결과:

```
현재 형식 → ['livecheck — 커밋 6건']
옛  형식 → ['make date-based retrieval actually work']
```

'커밋 반영' 지표가 커밋 메시지가 아니라 소스 이름을 세고 있다. 이 어긋남은
이번 변경이 아니라 **날짜 묶기 도입 시점부터** 있었다.

---

## 3부. 작업

### Task 1: 하루 요약 축약을 제 역할 하게 고친다

**파일:**
- 수정: `src/tools/ingest_rules.py` (상수 이사)
- 수정: `src/tools/embedding.py:28-29` (상수 이사)
- 수정: `src/tools/log.py:32-35, 81-94, 97-113, 130-157`
- 생성: `tests/unit/test_render_budget.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/unit/test_render_budget.py`:

```python
"""
조회 결과 분량 예산 단위 테스트

왜 필요한가:
    하루 요약의 '- ' 줄은 원래 바뀐 파일 목록이었고, 예산을 넘기면 이것부터
    덜어냈다. 지금 그 줄은 커밋 메시지·대화 턴이다. 같은 코드가 이제 '무엇을
    했는가'를 지우고 있어서, 무엇을 줄이는지 테스트로 못박는다.

    ChromaDB 도 네트워크도 타지 않는다 — 렌더링 함수만 직접 부른다.
"""
from langchain_core.documents import Document

from src.tools import log


def daily(source_type: str, date: str, items: int) -> Document:
    """항목 N개짜리 하루 요약 문서를 만든다."""
    head = f"[{date}] 테스트소스 — 항목 {items}건\n\n한 일:"
    body = "\n".join(f"- 항목 {i} " + "길게 " * 40 for i in range(items))
    return Document(
        page_content=f"{head}\n{body}",
        metadata={"date": date, "source_type": source_type, "source_name": "테스트소스"},
    )


class TestShrink:
    def test_예산_안이면_그대로_보여준다(self):
        docs = [daily("git_log", "2026-01-01", 3)]

        body, note = log._render(docs)

        assert note == ""
        assert "항목 2 " in body

    def test_예산을_넘기면_항목을_줄인다(self):
        docs = [daily("git_log", f"2026-01-{d:02d}", 60) for d in range(1, 31)]

        body, note = log._render(docs)

        assert len(body) <= log.MAX_RESULT_CHARS
        assert "외 " in body  # 몇 개를 덜어냈는지 밝힌다
        assert note != ""

    def test_대화로그도_줄어든다(self):
        """agent_chatlog 는 커밋보다 부피가 큰데 지금은 축약 대상이 아니다.

        축약되지 않으면 마지막 수단인 '문서 통째로 버리기'로 넘어가, 뒤쪽
        날짜가 통으로 사라진다. 줄여서 다 담는 편이 손실이 적다.
        """
        docs = [daily("agent_chatlog", f"2026-01-{d:02d}", 60) for d in range(1, 31)]

        body, _ = log._render(docs)

        assert len(body) <= log.MAX_RESULT_CHARS
        assert "2026-01-30" in body  # 마지막 날짜까지 담긴다

    def test_줄인_뒤에도_항목이_남는다(self):
        """제목만 남은 문서는 자리만 차지하고 아무것도 답하지 못한다.

        30일치로는 keep=3 에서 예산이 맞아 keep=0 까지 가지 않는다.
        90일치(조회 상한에 가까운 기간)로 마지막 단계까지 밀어붙인다.
        """
        docs = [daily("git_log", f"2026-{m:02d}-{d:02d}", 60)
                for m in (1, 2, 3) for d in range(1, 31)]

        body, _ = log._render(docs)

        assert "- 항목 0 " in body

    def test_안내문이_무엇을_줄였는지_말한다(self):
        docs = [daily("git_log", f"2026-01-{d:02d}", 60) for d in range(1, 31)]

        _, note = log._render(docs)

        assert "파일" not in note  # 파일 목록은 더 이상 수집하지 않는다
        assert "항목" in note
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/bin/python -m pytest tests/unit/test_render_budget.py -v
```

기대: **3 failed, 2 passed** — `test_대화로그도_줄어든다`(뒤쪽 날짜가 통으로
빠짐), `test_줄인_뒤에도_항목이_남는다`(제목만 남음),
`test_안내문이_무엇을_줄였는지_말한다`(안내문이 "파일"을 말함) 실패.

이 실패 3건과 Step 4 구현안으로의 전환은 계획 작성 시 실제로 돌려 확인했다.

- [ ] **Step 3: 상수를 두 모듈이 함께 쓰는 자리로 옮긴다**

`src/tools/ingest_rules.py` 맨 아래에 추가:

```python
# 하루치를 한 덩어리로 담는 문서 타입.
# 본문이 '- ' 불릿 목록이라 청크 분할에서 빼고, 분량 축약은 항목 단위로 한다.
DAILY_SUMMARY_TYPES = {"git_log", "agent_chatlog"}
```

`src/tools/embedding.py` — 기존 정의를 지우고 import 에 얹는다:

```python
from .ingest_rules import (
    DAILY_SUMMARY_TYPES,
    git_file_dates,
    normalize_date,
    resolve_date,
    should_collect,
)
```

지울 부분(`embedding.py:28-29`):

```python
# 하루치를 한 덩어리로 담는 문서 타입. 청크 분할에서 제외한다.
DAILY_SUMMARY_TYPES = {"git_log", "agent_chatlog"}
```

- [ ] **Step 4: `log.py` 를 고친다**

`src/tools/log.py:23` import 교체:

```python
from .ingest_rules import DAILY_SUMMARY_TYPES, normalize_date, parse_user_date
```

`src/tools/log.py:32-35` 교체:

```python
# 예산을 넘겼을 때 하루당 남길 항목 수. 앞에서부터 차례로 시도한다.
# 하루 문서의 부피는 대부분 항목 목록(커밋 메시지·대화 턴)이 차지한다.
# 0 은 두지 않는다 — 제목만 남은 문서는 자리를 차지하면서 아무것도 답하지 못하고,
# 무엇이 빠졌는지도 알리지 못해 그 날짜를 통째로 빼느니만 못하다.
SHRINK_STEPS = (20, 5)
```

`src/tools/log.py:81-94` 교체:

```python
def _shrink_daily(text: str, keep_items: int) -> str:
    """
    하루 요약에서 '- ' 항목을 keep_items 개만 남긴다.

    항목은 커밋 메시지(git_log) 또는 대화 턴(agent_chatlog)이다. 제목 줄과
    '한 일:' 같은 머리말은 그대로 두고 목록만 줄인다.
    """
    lines = text.split("\n")
    head = [line for line in lines if not line.startswith("- ")]
    # 이미 붙어 있는 '... 외 N개' 표시는 여기서 다시 계산한다
    items = [
        line for line in lines
        if line.startswith("- ") and not line.startswith("- ...")
    ]

    if len(items) <= keep_items:
        return text

    kept = items[:keep_items]
    # 몇 개를 덜어냈는지 반드시 밝힌다. 조용히 지우면 그날 한 일이
    # 원래 그것뿐이었던 것처럼 읽힌다.
    kept.append(f"- ... 외 {len(items) - keep_items}개")
    return "\n".join(head + kept)
```

`src/tools/log.py:97-102` 교체:

```python
def _render_doc(index: int, doc: Document, keep_items: int | None) -> str:
    """문서 하나를 결과 블록으로 만든다."""
    meta = doc.metadata
    content = doc.page_content
    if keep_items is not None and meta.get("source_type") in DAILY_SUMMARY_TYPES:
        content = _shrink_daily(content, keep_items)
```

`src/tools/log.py:116-157` 의 `_render` 를 통째로 교체:

```python
def _render(docs: list[Document]) -> tuple[str, str]:
    """
    문서 목록을 분량 예산 안에 들어가는 본문으로 만든다.

    개수로 자르지 않는다. 날짜 필터는 정확일치라 문서 사이에 우열이 없어서,
    개수로 자르면 '중요한 N건'이 아니라 '먼저 저장된 N건'이 남는다. 그러면
    나중에 임베딩한 소스가 통째로 밀려난다.

    대신 분량이 넘칠 때 하루 요약의 항목 수부터 줄인다. 하루를 통째로 버리는
    것보다 손실이 적고, 줄인 자리에는 '외 N개'가 남아 무엇이 빠졌는지 보인다.

    Returns:
        (본문, 안내문). 덜어낸 것이 없으면 안내문은 빈 문자열.
    """
    for keep in (None, *SHRINK_STEPS):
        body = "".join(_render_doc(i, doc, keep) for i, doc in enumerate(docs, 1))
        if len(body) <= MAX_RESULT_CHARS:
            if keep is None:
                return body, ""
            return body, f"\n(분량이 커서 하루당 항목을 {keep}개로 줄였습니다.)"

    # 가장 짧게 줄여도 넘치면 문서 수를 줄인다.
    # docs 는 날짜순이므로 앞에서부터 채우면 '앞 기간은 온전하고 뒤가 잘린다'가 되어
    # 무엇이 빠졌는지 말할 수 있다. 저장 순서대로 자르면 나중에 임베딩한 소스가
    # 통째로 빠지면서, 빠진 것이 무엇인지조차 알 수 없다.
    smallest = SHRINK_STEPS[-1]
    kept: list[str] = []
    size = 0
    for i, doc in enumerate(docs, 1):
        block = _render_doc(i, doc, keep_items=smallest)
        if size + len(block) > MAX_RESULT_CHARS:
            break
        kept.append(block)
        size += len(block)

    omitted = len(docs) - len(kept)
    covered = docs[len(kept) - 1].metadata.get("date") if kept else None
    span = f" {docs[0].metadata.get('date')} ~ {covered} 까지만 담겼습니다." if covered else ""
    return "".join(kept), (
        f"\n⚠️ 분량이 커서 하루당 항목을 {smallest}개로 줄이고 {omitted}개 문서를"
        f" 제외했습니다 (전체 {len(docs)}개 중 {len(kept)}개 표시).{span}"
        " 기간을 좁혀 다시 조회하세요."
    )
```

- [ ] **Step 5: 통과를 확인한다**

```bash
.venv/bin/python -m pytest tests/unit/test_render_budget.py -v
.venv/bin/python -m pytest tests/ -q
```

기대: 새 테스트 5개 전부 PASS, 전체 스위트 91 passed.

- [ ] **Step 6: 커밋**

```bash
git add src/tools/log.py src/tools/ingest_rules.py src/tools/embedding.py tests/unit/test_render_budget.py
git commit -m "fix: shrink daily summaries by item, not by phantom file lists"
```

---

### Task 2: 평가 스크립트의 커밋 추출을 하루 요약에 맞춘다

**파일:**
- 수정: `scripts/langsmith_eval.py:78-79, 106-112`
- 생성: `tests/unit/test_eval_extraction.py`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/unit/test_eval_extraction.py`:

```python
"""
평가 스크립트의 커밋 추출 단위 테스트

왜 필요한가:
    '커밋 반영' 지표는 그날 커밋한 내용이 일지에 나타나는지를 센다. 추출이
    어긋나면 지표는 계속 숫자를 내놓지만 그 숫자가 무엇을 센 것인지 알 수 없다.
    실제로 날짜 묶기 이후 이 정규식은 소스 이름('livecheck — 커밋 6건')을
    커밋 메시지로 뽑고 있었다.
"""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def eval_module():
    """스크립트를 모듈로 불러온다 (패키지가 아니므로 경로로 로드)."""
    path = Path(__file__).resolve().parents[2] / "scripts" / "langsmith_eval.py"
    spec = importlib.util.spec_from_file_location("langsmith_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DAILY = """[2026-08-03] 커밋이력 — 커밋 3건

한 일:
- chore: gitignore backups and logs
- fix: make date-based retrieval actually work
- Merge pull request #1 from hrunj1230/fix/embedding
"""


def test_불릿에서_커밋_메시지를_뽑는다(eval_module):
    found = eval_module.find_commits([{"type": "git_log", "text": DAILY}])

    assert "make date-based retrieval actually work" in found
    assert "gitignore backups and logs" in found


def test_제목_줄은_커밋으로_세지_않는다(eval_module):
    found = eval_module.find_commits([{"type": "git_log", "text": DAILY}])

    assert not any("커밋 3건" in m for m in found)


def test_생략_표시는_커밋으로_세지_않는다(eval_module):
    """분량 예산이 붙인 '- ... 외 N개'가 커밋으로 잡히면 안 된다."""
    text = DAILY + "- ... 외 39개\n"

    found = eval_module.find_commits([{"type": "git_log", "text": text}])

    assert not any(m.startswith("...") for m in found)


def test_다른_타입은_보지_않는다(eval_module):
    found = eval_module.find_commits([{"type": "agent_chatlog", "text": DAILY}])

    assert found == []
```

- [ ] **Step 2: 실패를 확인한다**

```bash
.venv/bin/python -m pytest tests/unit/test_eval_extraction.py -v
```

기대: `test_불릿에서_커밋_메시지를_뽑는다`, `test_제목_줄은_커밋으로_세지_않는다` 실패.

- [ ] **Step 3: 정규식과 추출 함수를 고친다**

`scripts/langsmith_eval.py:78-79` 교체:

```python
# 하루 요약의 '한 일:' 아래 불릿이 커밋 메시지다.
# conventional commit 접두어(feat:, fix:, feat(scope)!: ...)는 떼고 내용만 남긴다.
_COMMIT_LINE = re.compile(r"^- (?:\w+(?:\([^)]*\))?!?:\s*)?(.+)$", re.MULTILINE)
```

`scripts/langsmith_eval.py:106-112` 교체:

```python
def find_commits(chunks: list[dict]) -> list[str]:
    """하루 요약에서 커밋 메시지 본문만 뽑는다."""
    messages = []
    for c in chunks:
        if c.get("type") == "git_log":
            messages += [
                m.strip() for m in _COMMIT_LINE.findall(c["text"])
                # 분량 예산이 붙인 '... 외 N개'는 커밋이 아니다
                if not m.startswith("...")
            ]
    return messages
```

- [ ] **Step 4: 통과를 확인한다**

```bash
.venv/bin/python -m pytest tests/unit/test_eval_extraction.py -v
```

기대: 4개 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add scripts/langsmith_eval.py tests/unit/test_eval_extraction.py
git commit -m "fix: extract commit messages from daily summary bullets in eval"
```

---

### Task 3: 더미 소스 생성기를 현재 형식에 맞춘다

**파일:**
- 수정: `scripts/seed_dummy_sources.py:165-198`

더미 문서가 옛 '커밋 1건 = 문서 1개' 형식이라 평가가 실제와 다른 데이터를 본다.
Task 2 의 추출도 이 더미 위에서는 계속 어긋난다.

- [ ] **Step 1: `_commit_document` 를 하루 묶음 생성기로 교체한다**

`scripts/seed_dummy_sources.py:165-198` 의 `_commit_document` 를 지우고:

```python
def _daily_commit_document(day: dict, user_id: str, source_id: int) -> Document:
    """하루치 커밋을 실제 git_log 수집 결과와 같은 형식의 Document로 만든다."""
    commits = day.get("commits") or []

    lines = [
        f"[{day['date']}] {DUMMY_SOURCES[SourceType.GIT_LOG]} — 커밋 {len(commits)}건",
        "",
        "한 일:",
    ]
    lines += [f"- {c['message']}" for c in commits]
    content = "\n".join(lines)

    return Document(
        page_content=content,
        metadata={
            "user_id": user_id,
            "source_id": source_id,
            "source_type": "git_log",
            "source_name": DUMMY_SOURCES[SourceType.GIT_LOG],
            # 하루치를 한 덩어리로 교체하기 위한 키
            "file_path": f"commits/{day['date']}",
            "file_hash": hashlib.sha256(content.encode()).hexdigest(),
            # 실제 커밋 SHA가 아니므로 합성임이 드러나는 형태로 만든다
            "commit_shas": ",".join(
                f"synth{i:03d}" for i in range(len(commits))
            ),
            "commit_count": len(commits),
            "author": user_id,
            "date": day["date"],
            "date_origin": "synthetic",
            "synthetic": True,
            "embedded_at": datetime.now().isoformat(),
        },
    )
```

`scripts/seed_dummy_sources.py:18-21` import 에 추가:

```python
import hashlib
```

- [ ] **Step 2: 호출부를 고친다**

`scripts/seed_dummy_sources.py:295-299` — 커밋마다 한 번씩 돌던 이중 반복문을
하루당 한 번으로 바꾼다.

이전:

```python
    commits = [
        _commit_document(day, c, i, user_id, source_ids[SourceType.GIT_LOG])
        for day in valid
        for i, c in enumerate(day.get("commits") or [])
    ]
```

이후:

```python
    commits = [
        _daily_commit_document(day, user_id, source_ids[SourceType.GIT_LOG])
        for day in valid
    ]
```

- [ ] **Step 3: 문법과 형식을 확인한다**

```bash
.venv/bin/python -c "
import ast, pathlib
ast.parse(pathlib.Path('scripts/seed_dummy_sources.py').read_text())
print('구문 이상 없음')
"
```

- [ ] **Step 4: 커밋**

```bash
git add scripts/seed_dummy_sources.py
git commit -m "fix: seed dummy git_log sources in the daily summary shape"
```

---

### Task 4: 옛 스키마 잔재를 걷어낸다

**파일:**
- 수정: `src/tools/embedding.py:137-141, 151, 510-514, 524-539`

`commit_sha`(단수)는 커밋 1건 = 문서 1개이던 시절의 키다. 지금 쓰이는 키는
`file_hash` 와 `file_path` 이고, `commit_shas`(복수)는 검산용이다. 지금은
`file_hash` 가 먼저 잡혀 동작에 문제가 없지만, 읽는 사람을 잘못된 곳으로 보낸다.

- [ ] **Step 1: `_filter_new_documents` 에서 지운다**

`src/tools/embedding.py:136-141` 교체:

```python
        existing_hashes = set()
        for metadata in results.get("metadatas", []):
            if "file_hash" in metadata:
                existing_hashes.add(metadata["file_hash"])
```

`src/tools/embedding.py:155` 교체:

```python
        doc_hash = doc.metadata.get("file_hash")
```

- [ ] **Step 2: `_delete_stale_chunks` 에서 지운다**

`src/tools/embedding.py:510-514` 교체:

```python
    keys = {doc.metadata.get("file_path") for doc in documents}
    keys.discard(None)
```

`src/tools/embedding.py:524-539` 의 이중 반복문에서 `commit_sha` 를 뺀다:

```python
    deleted = 0
    for key in keys:
        try:
            found = collection.get(where={"$and": [
                {"source_id": source_id},
                {"file_path": key},
            ]})
        except Exception:
            continue

        ids = found.get("ids", [])
        if ids:
            collection.delete(ids=ids)
            deleted += len(ids)

    return deleted
```

- [ ] **Step 3: 전체 테스트로 회귀를 확인한다**

```bash
.venv/bin/python -m pytest tests/ -q
```

기대: 95 passed (현재 86 + Task 1 의 5 + Task 2 의 4).

- [ ] **Step 4: 커밋**

```bash
git add src/tools/embedding.py
git commit -m "refactor: drop the per-commit metadata key left over from daily grouping"
```

---

### Task 5: 서술을 사실에 맞춘다

**파일:**
- 수정: `src/unified_controller_single.py:113`
- 수정: `docs/ARCHITECTURE.md:152, 166`
- 수정: `docs/임베딩-파이프라인-문제분석.md:14`
- 수정: `docs/임베딩-파이프라인-작업기록.md:115`

- [ ] **Step 1: 에이전트 프롬프트를 고친다**

`src/unified_controller_single.py:113` 교체:

```
- 코드 프로젝트는 git_log 타입 — 커밋 메시지를 날짜별로 묶어 임베딩합니다. 코드 본문과 파일 목록은 수집하지 않습니다.
```

- [ ] **Step 2: 아키텍처 문서를 고친다**

`docs/ARCHITECTURE.md:152` 교체:

```
             → 소스 타입별 파일 수집 (git: clone, git_log: git log --all, local: 로컬 경로)
```

`docs/ARCHITECTURE.md:166` 교체:

```
        개수 제한 없이 그날 문서를 모두 가져오고, 분량이 넘치면
        하루 요약의 항목 수부터 줄인다 (MAX_RESULT_CHARS)
```

- [ ] **Step 3: 과거 기록 문서에 주석을 단다**

`docs/임베딩-파이프라인-문제분석.md:14` 와 `docs/임베딩-파이프라인-작업기록.md:115`
는 그 시점의 판단을 남긴 기록이므로 본문을 고치지 않는다. 대신 각 파일 맨 위에
한 줄을 넣어 지금과 다르다는 것을 알린다:

```markdown
> ⚠️ 2026-08-04 이후 `git_log` 는 `--numstat`/파일 목록을 수집하지 않습니다.
> 현재 방식은 [gitlog-수집방식-변경계획.md](gitlog-수집방식-변경계획.md) 참고.
```

- [ ] **Step 4: 커밋**

```bash
git add src/unified_controller_single.py docs/
git commit -m "docs: describe git_log collection as it actually works now"
```

---

### Task 6: 기존 소스를 새 형식으로 다시 받는다

**대상:** `data/sources/*/`, ChromaDB 컬렉션

옛 `--mirror` 저장소는 bare 라서 `_sync_repo` 가 stale 로 판정해 자동으로 다시
받는다. 벡터DB의 옛 문서도 `file_path: commits/{date}` 키가 같으므로
`_delete_stale_chunks` 가 교체한다. **다만 재임베딩을 실행해야 일어난다.**

- [ ] **Step 1: 현재 상태를 기록한다**

```bash
.venv/bin/python -c "
from src.storage.database import SessionLocal
from src.storage.models import Source, SourceType
db = SessionLocal()
for s in db.query(Source).filter_by(type=SourceType.GIT_LOG).all():
    print(s.id, s.user_id, s.name, s.embedding_status.value)
"
du -sh data/sources/*/*
```

- [ ] **Step 2: git_log 소스를 재임베딩한다**

```bash
.venv/bin/python scripts/reindex.py
```

- [ ] **Step 3: 결과를 검산한다**

저장소가 작아졌는지, 문서가 새 형식인지, 커밋 수가 원본과 맞는지 본다:

```bash
du -sh data/sources/*/*
.venv/bin/python -c "
from src.tools.embedding import _get_chroma_collection
c = _get_chroma_collection('hrunj1230')
got = c.get(where={'source_type': 'git_log'}, include=['documents','metadatas'])
print('문서 수:', len(got['ids']))
print('커밋 합:', sum(m.get('commit_count', 0) for m in got['metadatas']))
print('files_changed 잔존:', sum('files_changed' in m for m in got['metadatas']))
print()
print(got['documents'][0][:300])
"
```

기대: `files_changed 잔존: 0`, 본문에 `집중 영역:` 없음, 저장소 크기 감소.

- [ ] **Step 4: 커밋 (해당 없음)**

운영 작업이므로 커밋할 파일이 없다. 결과 수치만 이 문서 4부에 적는다.

---

## 4부. 결정 기록

### merge·빈 커밋을 다시 걸러낼 것인가 — 보류

현재 조회 명령에는 `%P` 가 없어 부모 수를 알 수 없고, 파일 목록이 없어 빈 커밋을
가릴 수 없다. 되살리려면 `--pretty` 에 `%P` 를 넣고(merge), `--name-only` 를
붙여야 한다(빈 커밋).

`--name-only` 를 다시 붙일 경우 **rename 탐지가 blob 을 요구**해 partial clone 이
lazy fetch 를 시도하다 실패한다. 실측으로 확인했다:

```
fatal: could not fetch 605d0ff... from promisor remote
```

`--no-renames` 를 함께 붙이면 오프라인에서도 전체 클론과 출력이 완전히 일치했다
(375줄 동일). rename 은 삭제+추가 두 줄로 나뉘어 경로 줄이 300 → 308 로 늘었다.

**지금은 사용자 결정에 따라 보류한다.** 되살릴 때 필요한 명령은 다음과 같다:

```bash
git log --all --date=iso --no-renames --name-only \
  --pretty=format:"Commit: %H%nParents: %P%nAuthor: %an <%ae>%nDate: %ad%nSubject: %s%n"
```

`tests/unit/test_sync_repo.py::test_merge_커밋도_그대로_들어온다` 가 현재 동작을
못박고 있으므로, 되살릴 때는 그 테스트부터 뒤집으면 된다.

---

## 실행 순서

Task 1 → 2 → 3 → 4 → 5 → 6.

1·2 는 사용자에게 보이는 결과가 어긋나 있으므로 먼저 한다. 3 은 2 의 검증 데이터를
맞추는 일이라 2 다음이다. 4·5 는 독립적이며 순서를 바꿔도 된다. 6 은 코드가
모두 자리 잡은 뒤에 한 번만 돌린다.
