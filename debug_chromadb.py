#!/usr/bin/env python3
"""
ChromaDB 데이터 확인 스크립트
임베딩 후 메타데이터가 제대로 저장되었는지 확인
"""

import chromadb
from chromadb.config import Settings
import os

def check_chromadb():
    print("=" * 60)
    print("ChromaDB 데이터 확인")
    print("=" * 60)
    print()

    # ChromaDB 연결 (로컬 모드)
    try:
        client = chromadb.PersistentClient(path="./chroma_db")
        print("✅ ChromaDB 연결 성공: ./chroma_db")
    except Exception as e:
        print(f"❌ ChromaDB 연결 실패: {e}")
        return

    # 모든 컬렉션 조회
    collections = client.list_collections()

    if not collections:
        print("⚠️  컬렉션이 없습니다!")
        print("\n해결 방법:")
        print("  1. Git 동기화를 다시 실행하세요")
        print("  2. POST /sync_git_repo")
        return

    print(f"\n📦 총 {len(collections)}개 컬렉션 발견:\n")

    for coll in collections:
        print(f"{'='*60}")
        print(f"컬렉션: {coll.name}")
        print(f"{'='*60}")

        # 문서 수
        count = coll.count()
        print(f"📊 문서 수: {count}개")

        if count == 0:
            print("⚠️  빈 컬렉션입니다!\n")
            continue

        # 샘플 데이터 조회 (최대 3개)
        sample = coll.get(
            limit=min(3, count),
            include=["documents", "metadatas"]
        )

        print(f"\n📄 샘플 데이터 (최대 3개):\n")

        for i, (doc_id, metadata, content) in enumerate(zip(
            sample['ids'],
            sample['metadatas'],
            sample['documents']
        ), 1):
            print(f"--- 문서 {i} ---")
            print(f"ID: {doc_id[:32]}...")
            print(f"메타데이터: {metadata}")
            print(f"내용 미리보기: {content[:100]}...")
            print()

        # 메타데이터 필드 분석
        print(f"🔍 메타데이터 분석:")

        all_data = coll.get(include=["metadatas"])
        metadatas = all_data['metadatas']

        # 날짜 필드 확인
        dates_found = sum(1 for m in metadatas if m and 'date' in m)
        print(f"  - 'date' 필드 있는 문서: {dates_found}/{count}개")

        # 날짜 샘플
        date_samples = [m.get('date') for m in metadatas if m and 'date' in m][:5]
        if date_samples:
            print(f"  - 날짜 샘플: {date_samples}")
        else:
            print(f"  - ⚠️  날짜 필드가 없습니다!")

        # source 필드 확인
        sources_found = sum(1 for m in metadatas if m and 'source' in m)
        print(f"  - 'source' 필드 있는 문서: {sources_found}/{count}개")

        # source 샘플
        source_samples = [m.get('source') for m in metadatas if m and 'source' in m][:3]
        if source_samples:
            print(f"  - source 샘플:")
            for s in source_samples:
                print(f"    - {s}")

        print()

    # 특정 날짜로 검색 테스트
    print(f"{'='*60}")
    print("🔎 메타데이터 필터 테스트")
    print(f"{'='*60}\n")

    # 가장 큰 컬렉션 선택
    largest_coll = max(collections, key=lambda c: c.count())
    print(f"컬렉션: {largest_coll.name} (문서 {largest_coll.count()}개)")

    # 모든 날짜 추출
    all_data = largest_coll.get(include=["metadatas"])
    dates = [m.get('date') for m in all_data['metadatas'] if m and 'date' in m]
    unique_dates = sorted(set(dates))

    if unique_dates:
        print(f"\n📅 저장된 날짜 목록 ({len(unique_dates)}개):")
        for d in unique_dates[:10]:  # 최대 10개만 표시
            print(f"  - {d}")

        # 첫 번째 날짜로 검색 테스트
        test_date = unique_dates[0]
        print(f"\n🧪 테스트: '{test_date}' 날짜로 검색")

        try:
            results = largest_coll.get(
                where={"date": test_date},
                limit=5,
                include=["metadatas", "documents"]
            )

            if results['ids']:
                print(f"✅ 검색 성공! {len(results['ids'])}개 문서 발견")
                print(f"\n첫 번째 결과:")
                print(f"  - 메타데이터: {results['metadatas'][0]}")
                print(f"  - 내용: {results['documents'][0][:100]}...")
            else:
                print(f"⚠️  검색 결과 없음")
        except Exception as e:
            print(f"❌ 검색 실패: {e}")
    else:
        print("⚠️  날짜 메타데이터가 없습니다!")
        print("\n원인:")
        print("  - 파일명에 날짜 형식이 없음 (YYYY_MM_DD 또는 YYYY-MM-DD)")
        print("  - 임베딩 중 날짜 추출 실패")

    print()
    print("=" * 60)
    print("확인 완료!")
    print("=" * 60)

if __name__ == "__main__":
    check_chromadb()
