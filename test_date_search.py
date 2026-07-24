#!/usr/bin/env python3
"""
날짜 검색 테스트: 청킹 후에도 날짜 메타데이터가 제대로 작동하는지 확인
"""

from langchain_chroma import Chroma
import src.llm_router as llm_router

def test_date_search(user_id: str = "hrun", test_date: str = "2026-07-20"):
    """
    날짜 검색 테스트

    Args:
        user_id: 사용자 ID
        test_date: 테스트할 날짜 (YYYY-MM-DD)
    """
    collection_name = f"user_{user_id}"

    print(f"🔍 날짜 검색 테스트: {test_date}")
    print("=" * 60)

    try:
        # Chroma 컬렉션 연결
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=llm_router.embedding_function,
            client=llm_router.chroma_client
        )

        # 전체 데이터 확인
        all_data = vectorstore.get(include=["metadatas"])
        print(f"✅ 전체 청크: {len(all_data['ids'])}개")

        # 날짜별 청크 수 확인
        date_counts = {}
        for meta in all_data["metadatas"]:
            date = meta.get("date", "날짜 없음")
            date_counts[date] = date_counts.get(date, 0) + 1

        print(f"\n📅 날짜별 청크 분포:")
        for date, count in sorted(date_counts.items()):
            print(f"  {date}: {count}개")

        # 특정 날짜 검색 (메타데이터 필터)
        print(f"\n🎯 '{test_date}' 날짜 검색 (메타데이터 필터):")
        print("-" * 60)

        filtered_docs = vectorstore.get(
            where={"date": test_date},
            include=["metadatas", "documents"]
        )

        found_count = len(filtered_docs["ids"])

        if found_count == 0:
            print(f"❌ '{test_date}' 날짜의 청크를 찾을 수 없습니다.")
            print(f"💡 사용 가능한 날짜: {list(date_counts.keys())}")
            return False

        print(f"✅ {found_count}개 청크 발견!")

        # 각 청크 확인
        for i, (doc_id, meta, doc) in enumerate(zip(
            filtered_docs["ids"],
            filtered_docs["metadatas"],
            filtered_docs["documents"]
        ), 1):
            source = meta.get("source", "unknown")
            date = meta.get("date", "없음")
            content_hash = meta.get("content_hash", "없음")[:16]

            print(f"\n[청크 {i}]")
            print(f"  ID: {doc_id[:16]}...")
            print(f"  Source: {source}")
            print(f"  Date: {date} {'✅' if date == test_date else '❌'}")
            print(f"  Hash: {content_hash}...")
            print(f"  길이: {len(doc)}자")
            print(f"  미리보기: {doc[:100]}...")

        # 유사도 검색 테스트
        print(f"\n🔎 '{test_date}' 유사도 검색:")
        print("-" * 60)

        similarity_docs = vectorstore.similarity_search(
            f"작성 날짜: {test_date}",
            k=3
        )

        print(f"✅ {len(similarity_docs)}개 문서 발견")

        for i, doc in enumerate(similarity_docs, 1):
            date = doc.metadata.get("date", "없음")
            print(f"[{i}] Date: {date}, 길이: {len(doc.page_content)}자")

        print()
        print("=" * 60)
        print("✅ 날짜 검색 테스트 성공!")
        return True

    except Exception as e:
        print(f"❌ 에러: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_all_dates(user_id: str = "hrun"):
    """모든 날짜에 대해 검색 테스트"""
    collection_name = f"user_{user_id}"

    try:
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=llm_router.embedding_function,
            client=llm_router.chroma_client
        )

        # 모든 날짜 추출
        all_data = vectorstore.get(include=["metadatas"])
        dates = set(meta.get("date") for meta in all_data["metadatas"] if meta.get("date"))

        print(f"🗓️ 전체 날짜 검색 테스트")
        print("=" * 60)

        success_count = 0
        fail_count = 0

        for date in sorted(dates):
            filtered = vectorstore.get(where={"date": date})
            count = len(filtered["ids"])

            if count > 0:
                print(f"✅ {date}: {count}개")
                success_count += 1
            else:
                print(f"❌ {date}: 0개 (메타데이터 문제!)")
                fail_count += 1

        print("=" * 60)
        print(f"결과: 성공 {success_count}개, 실패 {fail_count}개")

        return fail_count == 0

    except Exception as e:
        print(f"❌ 에러: {str(e)}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="날짜 검색 테스트")
    parser.add_argument("--user-id", default="hrun", help="사용자 ID")
    parser.add_argument("--date", help="테스트할 날짜 (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="모든 날짜 테스트")

    args = parser.parse_args()

    if args.all:
        test_all_dates(args.user_id)
    elif args.date:
        test_date_search(args.user_id, args.date)
    else:
        # 기본: 오늘 날짜로 테스트
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        test_date_search(args.user_id, today)
