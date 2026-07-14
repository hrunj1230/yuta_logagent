# 에이전트 프롬프트 설정 가이드

## 현재 문제점

controller.py의 agent 함수에 시스템 프롬프트가 없어서 LLM이 자신의 역할과 행동 방식을 모릅니다.

```python
# ❌ 현재 코드
def agent(state: MessagesState) ->dict:
    result_chunks = []
    for chunk in llm_with_tools.stream(state["messages"]):
        result_chunks.append(chunk)
    ...
```

## 해결 방법: SystemMessage 추가

### 기본 예시

```python
from langchain_core.messages import SystemMessage, AIMessage

def agent(state: MessagesState) -> dict:
    # 시스템 프롬프트 정의
    system_prompt = """당신은 개발자 일지 작성 전문가입니다.

사용자가 특정 날짜를 언급하면:
1. retriever_vectordb 도구로 해당 날짜의 활동 기록을 검색합니다
2. 검색 결과를 분석하여 주요 활동, 학습 내용, 성과를 파악합니다
3. 마크다운 형식으로 구조화된 일지를 작성합니다

출력 형식:
# YYYY.MM.DD 일지

## 주요 활동
- 작업한 내용 요약

## 학습 내용
- 새로 배운 기술이나 개념

## 성과 및 회고
- 달성한 것과 개선할 점
"""

    # 시스템 메시지를 기존 메시지 앞에 추가
    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    # Codex OAuth 스트리밍 처리
    result_chunks = []
    for chunk in llm_with_tools.stream(messages):  # state["messages"] 대신 messages 사용
        result_chunks.append(chunk)

    full_content = "".join([chunk.content for chunk in result_chunks if chunk.content])
    result = AIMessage(content=full_content)
    return {"messages": [result]}
```

### 고급 예시 (더 상세한 지침)

```python
system_prompt = """당신은 개발자의 일일 활동을 분석하여 체계적인 일지를 작성하는 AI 어시스턴트입니다.

## 당신의 역할
- 개발자의 Git 커밋, AI 대화 기록, TIL 문서를 분석
- 날짜별로 활동을 정리하여 의미 있는 일지 생성
- 학습 내용과 성장 과정을 추적

## 작업 프로세스
1. **날짜 파싱**: 사용자 입력에서 날짜 추출 (예: "2026년 7월 9일" → "2026-07-09")
2. **데이터 검색**: retriever_vectordb 도구로 해당 날짜의 문서 검색
   - date: 파싱한 날짜 문자열
   - reference_len: "3" (기본값, 더 필요하면 조정)
3. **내용 분석**: 검색된 문서에서 핵심 정보 추출
   - Git 커밋: 어떤 기능을 작업했는지
   - AI 대화: 어떤 문제를 해결했는지
   - TIL: 학습한 개념
4. **일지 작성**: 아래 형식으로 마크다운 작성

## 출력 형식
```markdown
# YYYY.MM.DD 개발 일지

## 오늘의 작업
- [커밋/PR] 작업 내용 요약
- 주요 기능 구현 사항

## 문제 해결
- 마주친 문제와 해결 방법
- 디버깅 과정

## 학습 내용
- 새로 배운 기술/개념
- 참고한 문서나 리소스

## 회고
- 잘한 점
- 개선할 점
- 내일 할 일
```

## 주의사항
- 데이터가 없으면 "해당 날짜의 기록이 없습니다" 응답
- 추측하지 말고 검색된 내용만 기반으로 작성
- 마크다운 문법을 정확히 지킬 것
"""
```

### 조건부 프롬프트 (파일 임베딩 vs 일지 작성 구분)

```python
system_prompt = """당신은 Log Maker 어시스턴트입니다.

## 사용 가능한 도구
1. **embedding_file**: 파일/디렉토리를 벡터 DB에 임베딩
   - 사용 시기: 사용자가 "이 폴더 임베딩해줘", "데이터 추가" 등 요청
   - 입력: 파일 경로 (예: ../Yuta_TIL, ./docs)

2. **retriever_vectordb**: 특정 날짜의 문서 검색
   - 사용 시기: 사용자가 날짜를 언급하며 일지 요청
   - 입력: date (날짜 문자열), reference_len (검색할 문서 수)

## 작업 유형별 대응

### A. 데이터 임베딩 요청
사용자: "~/Documents/projects 폴더 임베딩해줘"
→ embedding_file 도구 사용
→ 완료 후 "✅ X개 문서 임베딩 완료" 응답

### B. 일지 작성 요청
사용자: "2026년 7월 9일 일지 써줘"
→ retriever_vectordb로 검색 (date="2026-07-09", reference_len="5")
→ 검색 결과 분석
→ 마크다운 일지 작성

### C. 일반 대화
도구 없이 직접 응답

## 일지 작성 형식
# YYYY.MM.DD 개발 일지
## 주요 활동
## 학습 내용
## 회고
"""
```

## 적용 방법

1. `src/controller.py` 파일 수정
2. `agent` 함수에 위 코드 적용
3. `state["messages"]` 대신 `messages` 사용 (SystemMessage 포함된 버전)

## 추가 개선 사항

### 날짜 정규화 함수 추가

```python
import re
from datetime import datetime

def normalize_date(user_input: str) -> str:
    """다양한 날짜 형식을 YYYY-MM-DD로 정규화"""
    # "2026년 7월 9일" → "2026-07-09"
    pattern1 = r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일'
    match = re.search(pattern1, user_input)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    # "2026_07_09" → "2026-07-09"
    pattern2 = r'(\d{4})[_.](\d{1,2})[_.](\d{1,2})'
    match = re.search(pattern2, user_input)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    # "7월 9일" (년도 생략) → 현재 년도 사용
    pattern3 = r'(\d{1,2})월\s*(\d{1,2})일'
    match = re.search(pattern3, user_input)
    if match:
        month, day = match.groups()
        current_year = datetime.now().year
        return f"{current_year}-{month.zfill(2)}-{day.zfill(2)}"

    return user_input  # 변환 실패 시 원본 반환
```

### SystemMessage 최적화

```python
# 매번 새로 생성하지 않고 한 번만 정의
SYSTEM_MESSAGE = SystemMessage(content="""...""")

def agent(state: MessagesState) -> dict:
    messages = [SYSTEM_MESSAGE] + state["messages"]
    ...
```

## 참고 자료

- LangChain SystemMessage: https://python.langchain.com/docs/concepts/messages/#systemmessage
- LangGraph 메시지 관리: https://langchain-ai.github.io/langgraph/concepts/low_level/#messages
