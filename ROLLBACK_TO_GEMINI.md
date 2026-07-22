# Codex 문제 발생 시 Gemini로 롤백

## 빠른 롤백 방법

### src/controller.py 수정

```python
# Line 146: Source Manager
llm_source_manager = llm.google_llm.bind_tools(source_tools)

# Line 219: Git URL 강제 호출
llm_forced = llm.google_llm.bind_tools(
    source_tools,
    tool_choice="add_source_to_db"
)

# Line 300: Router
router_llm = llm.google_llm.with_structured_output(RouteDecision)
```

## 각 모델 비교

| 모델 | Tool Calling | Structured Output | 비용 | 속도 |
|------|--------------|-------------------|------|------|
| **Codex Mini** | ❓ 테스트 필요 | ❓ 테스트 필요 | 구독 (가장 저렴) | 빠름 |
| **Gemini Flash** | ✅ 지원 | ✅ 지원 | $0.075/M | 매우 빠름 |
| **Claude Sonnet** | ✅ 지원 | ✅ 지원 | $3/M | 중간 |

## 문제별 대응

### 1. Tool Calling 미지원
- 증상: `add_source_to_db` 호출 실패
- 해결: Gemini Flash로 변경

### 2. Structured Output 미지원
- 증상: Router가 RouteDecision 파싱 실패
- 해결: Gemini Flash로 변경

### 3. 일부만 작동
- Router는 작동, Source는 실패 → Source만 Gemini로 변경
- 혼합 사용 가능!
