# LiteLLM을 사용한 고급 LLM 라우팅
# 설치: pip install litellm

from litellm import completion
from typing import Literal
import os

# 작업 복잡도별 모델 매핑
MODEL_MAPPING = {
    "simple": [
        "gemini/gemini-2.5-flash-lite",  # 1순위: 가장 저렴
        "anthropic/claude-haiku-4-20250514",  # 폴백
    ],
    "medium": [
        "gemini/gemini-2.5-flash",
        "anthropic/claude-sonnet-4-5-20250929",
    ],
    "complex": [
        "anthropic/claude-sonnet-4-5-20250929",
        "anthropic/claude-opus-4-6-20250514",
    ]
}

def get_llm_response(
    messages: list,
    complexity: Literal["simple", "medium", "complex"] = "medium",
    tools: list = None,
    temperature: float = 0.7
):
    """
    작업 복잡도에 따라 적절한 LLM 선택

    Args:
        messages: 대화 메시지
        complexity: "simple" (라우팅), "medium" (CRUD), "complex" (글쓰기)
        tools: 도구 리스트
        temperature: 생성 온도

    Returns:
        LLM 응답
    """
    models = MODEL_MAPPING[complexity]

    # 폴백 전략: 첫 번째 모델 실패 시 다음 모델 시도
    for model in models:
        try:
            response = completion(
                model=model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                # 자동 재시도
                num_retries=2,
                # 타임아웃 (초)
                timeout=30,
            )

            print(f"[LiteLLM] ✅ {model} 사용 (비용: ${response._hidden_params.get('cost', 0):.6f})")
            return response

        except Exception as e:
            print(f"[LiteLLM] ⚠️ {model} 실패: {e}")
            continue

    raise Exception(f"모든 모델 실패: {models}")


# 사용 예시
if __name__ == "__main__":
    # Router Agent (simple)
    response = get_llm_response(
        messages=[{"role": "user", "content": "이 요청을 분류해줘"}],
        complexity="simple"
    )

    # Source Agent (medium)
    response = get_llm_response(
        messages=[{"role": "user", "content": "Git 저장소 추가"}],
        complexity="medium",
        tools=[...]
    )

    # Log Agent (complex)
    response = get_llm_response(
        messages=[{"role": "user", "content": "오늘 일지 작성"}],
        complexity="complex"
    )
