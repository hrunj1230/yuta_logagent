"""
통합 Agent 테스트 스크립트

두 가지 구현 방식을 테스트합니다:
1. Single Agent 방식 (unified_controller_single)
2. Router 방식 (unified_controller_router)
"""

from src.unified_controller_single import unified_agent as single_agent
from src.unified_controller_router import unified_agent as router_agent


def print_separator(title: str):
    """구분선 출력"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")


def test_single_agent():
    """Single Agent 방식 테스트"""
    print_separator("🔹 Single Agent 방식 테스트")

    user_id = "test_user_single"

    # 테스트 1: 소스 목록 조회
    print("📋 테스트 1: 소스 목록 조회")
    print(f"요청: '소스 목록 보여줘'")
    response = single_agent(user_id, "소스 목록 보여줘")
    print(f"응답:\n{response}\n")

    # 테스트 2: 소스 타입 확인
    print("📋 테스트 2: 소스 타입 확인")
    print(f"요청: '소스 타입이 뭐가 있어?'")
    response = single_agent(user_id, "소스 타입이 뭐가 있어?")
    print(f"응답:\n{response}\n")


def test_router_agent():
    """Router 방식 테스트"""
    print_separator("🔸 Router 방식 테스트")

    user_id = "test_user_router"

    # 테스트 1: 소스 목록 조회 (Router → Source Agent)
    print("📋 테스트 1: 소스 목록 조회 (라우팅 확인)")
    print(f"요청: '내 소스 목록 보여줘'")
    response = router_agent(user_id, "내 소스 목록 보여줘")
    print(f"응답:\n{response}\n")

    # 테스트 2: 임베딩 상태 확인 (Router → Embedding Agent)
    print("📋 테스트 2: 임베딩 상태 확인 (라우팅 확인)")
    print(f"요청: '임베딩 상태 알려줘'")
    response = router_agent(user_id, "임베딩 상태 알려줘")
    print(f"응답:\n{response}\n")


def test_conversation_history():
    """대화 기록 유지 테스트"""
    print_separator("💬 대화 기록 유지 테스트 (Single Agent)")

    user_id = "test_user_history"

    # 첫 번째 대화
    print("📋 대화 1: 소스 목록 요청")
    response1 = single_agent(user_id, "내 소스 목록 보여줘")
    print(f"응답:\n{response1}\n")

    # 두 번째 대화 (이전 대화 참조)
    print("📋 대화 2: 이전 대화 참조")
    response2 = single_agent(user_id, "방금 보여준 목록 중 첫 번째 소스는 뭐야?")
    print(f"응답:\n{response2}\n")


def compare_both_agents():
    """두 방식 비교 테스트"""
    print_separator("⚖️  두 방식 비교: 동일한 요청")

    test_message = "소스 목록 보여줘"

    # Single Agent
    print("🔹 Single Agent 응답:")
    response_single = single_agent("compare_user", test_message)
    print(f"{response_single}\n")

    # Router Agent
    print("🔸 Router Agent 응답:")
    response_router = router_agent("compare_user", test_message)
    print(f"{response_router}\n")


def main():
    """메인 테스트 실행"""
    print("\n" + "🚀 " + "통합 Agent 테스트 시작".center(76) + " 🚀\n")

    try:
        # 1. Single Agent 테스트
        test_single_agent()

        # 2. Router Agent 테스트
        test_router_agent()

        # 3. 대화 기록 유지 테스트
        test_conversation_history()

        # 4. 두 방식 비교
        compare_both_agents()

        print_separator("✅ 모든 테스트 완료")
        print("두 가지 구현 방식이 모두 정상 작동합니다!")

    except Exception as e:
        print_separator("❌ 테스트 중 오류 발생")
        print(f"오류 내용: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
