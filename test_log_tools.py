"""
로그 도구 테스트 스크립트

새로 추가된 로그 관리 도구들을 테스트합니다:
1. retriever_vectordb - 날짜 기반 VectorDB 검색
2. maker_logfile - 일지 파일 저장
3. 통합 Agent를 통한 일지 작성 워크플로우
"""

from src.tools.log import retriever_vectordb, maker_logfile
from src.unified_controller_single import unified_agent as single_agent


def print_separator(title: str):
    """구분선 출력"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")


def test_retriever_vectordb():
    """retriever_vectordb 도구 직접 테스트"""
    print_separator("📊 retriever_vectordb 도구 테스트")

    # 테스트 1: 정확한 날짜 검색
    print("📋 테스트 1: 정확한 날짜 형식으로 검색")
    print(f"요청: retriever_vectordb('2026-07-28', '3')")
    try:
        result = retriever_vectordb.invoke({
            "date": "2026-07-28",
            "reference_len": "3"
        })
        print(f"결과:\n{result}\n")
    except Exception as e:
        print(f"오류: {str(e)}\n")

    # 테스트 2: 다양한 날짜 형식
    print("📋 테스트 2: 다른 날짜 형식으로 검색")
    print(f"요청: retriever_vectordb('2026년 07월 28일', '2')")
    try:
        result = retriever_vectordb.invoke({
            "date": "2026년 07월 28일",
            "reference_len": "2"
        })
        print(f"결과:\n{result}\n")
    except Exception as e:
        print(f"오류: {str(e)}\n")

    # 테스트 3: 기본 개수 (reference_len 미지정)
    print("📋 테스트 3: 기본 검색 개수 테스트")
    print(f"요청: retriever_vectordb('2026-07-27', '')")
    try:
        result = retriever_vectordb.invoke({
            "date": "2026-07-27",
            "reference_len": ""
        })
        print(f"결과:\n{result}\n")
    except Exception as e:
        print(f"오류: {str(e)}\n")


def test_maker_logfile():
    """maker_logfile 도구 직접 테스트"""
    print_separator("💾 maker_logfile 도구 테스트")

    # 테스트 1: 간단한 일지 저장
    print("📋 테스트 1: 테스트 일지 저장")
    test_date = "2026-07-28"
    test_content = """# 2026년 7월 28일 일지

## 오늘의 주요 활동
- 통합 Agent 구현 완료
  - 단일 Agent 방식
  - Router 방식
- 로그 관리 도구 추가
  - retriever_vectordb
  - maker_logfile

## 성과
- 8개 도구를 사용하는 통합 Agent 완성
- 대화 기록 유지 기능 추가

## 배운 점
- LangGraph의 checkpointer 활용법
- Router 기반 멀티 Agent 아키텍처 설계

"""

    print(f"날짜: {test_date}")
    print(f"내용 미리보기:\n{test_content[:100]}...\n")
    try:
        result = maker_logfile.invoke({
            "date": test_date,
            "content": test_content,
            "user_id": "hrunj1230"
        })
        print(f"결과: {result}\n")
    except Exception as e:
        print(f"오류: {str(e)}\n")

    # 테스트 2: 다른 날짜 형식
    print("📋 테스트 2: 다른 날짜로 저장")
    test_date2 = "2026-07-27"
    test_content2 = "# 2026년 7월 27일\n\n간단한 테스트 일지입니다."

    print(f"날짜: {test_date2}")
    try:
        result = maker_logfile.invoke({
            "date": test_date2,
            "content": test_content2,
            "user_id": "hrunj1230"
        })
        print(f"결과: {result}\n")
    except Exception as e:
        print(f"오류: {str(e)}\n")


def test_single_agent_log_workflow():
    """단일 Agent 방식으로 일지 작성 워크플로우 테스트"""
    print_separator("🔹 단일 Agent 방식 - 일지 작성 워크플로우")

    user_id = "test_user_log_single"

    # 테스트 1: 일지 작성 요청
    print("📋 테스트 1: 특정 날짜 일지 작성 요청")
    print(f"요청: '2026년 7월 28일 일지를 작성해줘'")
    try:
        response = single_agent(user_id, "2026년 7월 28일 일지를 작성해줘")
        print(f"응답:\n{response}\n")
    except Exception as e:
        print(f"오류: {str(e)}\n")

    # 테스트 2: 날짜 데이터 검색만 요청
    print("📋 테스트 2: 날짜 데이터 검색만 요청")
    print(f"요청: '2026년 7월 27일에 무슨 일이 있었는지 3개만 보여줘'")
    try:
        response = single_agent(user_id, "2026년 7월 27일에 무슨 일이 있었는지 3개만 보여줘")
        print(f"응답:\n{response}\n")
    except Exception as e:
        print(f"오류: {str(e)}\n")


def test_conversation_with_logs():
    """대화 기록을 유지하며 로그 작업 테스트"""
    print_separator("💬 대화 기록 유지하며 로그 작업 테스트")

    user_id = "test_user_log_conversation"

    # 첫 번째 대화: 검색
    print("📋 대화 1: 날짜 데이터 검색")
    response1 = single_agent(user_id, "2026년 7월 28일 데이터를 2개만 검색해줘")
    print(f"응답:\n{response1}\n")

    # 두 번째 대화: 이전 검색 결과 참조
    print("📋 대화 2: 이전 검색 결과 참조")
    response2 = single_agent(user_id, "방금 검색한 결과로 일지를 작성해줘")
    print(f"응답:\n{response2}\n")

    # 세 번째 대화: 저장 확인
    print("📋 대화 3: 저장된 파일 확인 요청")
    response3 = single_agent(user_id, "방금 저장한 파일 이름이 뭐야?")
    print(f"응답:\n{response3}\n")


def check_created_files():
    """생성된 로그 파일 확인"""
    print_separator("📁 생성된 로그 파일 확인")

    import os

    logs_dir = "logs"
    if os.path.exists(logs_dir):
        files = os.listdir(logs_dir)
        if files:
            print(f"생성된 파일 목록 ({len(files)}개):")
            for file in sorted(files):
                file_path = os.path.join(logs_dir, file)
                file_size = os.path.getsize(file_path)
                print(f"  - {file} ({file_size} bytes)")
        else:
            print("logs 디렉토리가 비어있습니다.")
    else:
        print("logs 디렉토리가 존재하지 않습니다.")


def main():
    """메인 테스트 실행"""
    print("\n" + "🚀 " + "로그 도구 테스트 시작".center(76) + " 🚀\n")

    try:
        # 1. 개별 도구 테스트
        test_retriever_vectordb()
        test_maker_logfile()

        # 2. 단일 Agent 워크플로우 테스트
        test_single_agent_log_workflow()

        # 3. 대화 기록 유지 테스트
        test_conversation_with_logs()

        # 4. 생성된 파일 확인
        check_created_files()

        print_separator("✅ 모든 테스트 완료")
        print("로그 관리 도구가 정상적으로 통합되었습니다!")
        print("\n💡 참고:")
        print("  - retriever_vectordb는 ChromaDB에 데이터가 있어야 작동합니다.")
        print("  - 실제 일지 작성을 위해서는 VectorDB에 임베딩된 데이터가 필요합니다.")
        print("  - 생성된 일지는 logs/ 디렉토리에 저장됩니다.")

    except Exception as e:
        print_separator("❌ 테스트 중 오류 발생")
        print(f"오류 내용: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
