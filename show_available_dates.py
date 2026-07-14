#!/usr/bin/env python3
"""
사용 가능한 날짜 목록 표시
"""

import chromadb
from datetime import datetime

client = chromadb.PersistentClient(path="./chroma_db")
collections = client.list_collections()

print("=" * 60)
print("📅 일지 생성 가능한 날짜 목록")
print("=" * 60)
print()

for coll in collections:
    if coll.count() == 0:
        continue

    print(f"컬렉션: {coll.name} ({coll.count()}개 문서)")
    print("-" * 60)

    # 모든 날짜 추출
    all_data = coll.get(include=["metadatas"])
    dates = [m.get('date') for m in all_data['metadatas'] if m and 'date' in m]
    unique_dates = sorted(set(dates))

    if unique_dates:
        print(f"\n✅ 날짜 있는 문서: {len(unique_dates)}개\n")

        # 연도별 그룹화
        dates_by_year = {}
        for d in unique_dates:
            year = d[:4]
            if year not in dates_by_year:
                dates_by_year[year] = []
            dates_by_year[year].append(d)

        for year in sorted(dates_by_year.keys()):
            print(f"📆 {year}년:")
            for date in sorted(dates_by_year[year]):
                # 한국어 형식으로 변환
                dt = datetime.strptime(date, "%Y-%m-%d")
                kr_date = dt.strftime("%Y년 %m월 %d일")

                print(f"  - {date} → \"{kr_date} 일지 작성해줘\"")

    # 날짜 없는 파일
    files_without_date = sum(1 for m in all_data['metadatas'] if m and 'date' not in m)
    if files_without_date > 0:
        print(f"\n⚠️  날짜 없는 문서: {files_without_date}개")

        # 날짜 없는 파일 이름 표시
        sources = [m.get('source') for m in all_data['metadatas'] if m and 'date' not in m]
        print("\n날짜 없는 파일들:")
        for s in sources[:5]:  # 최대 5개만
            filename = s.split('/')[-1]
            print(f"  - {filename}")

        if len(sources) > 5:
            print(f"  ... 외 {len(sources) - 5}개")

    print()

print("=" * 60)
print("💡 사용 예시:")
print("=" * 60)
print()
print("웹 UI에서 날짜 입력:")
print("  2026년 6월 3일")
print()
print("또는 API 호출:")
print('  curl -X POST http://localhost:8000/call_agent \\')
print('    -H "Content-Type: application/json" \\')
print('    -d \'{"req":"2026년 6월 3일 일지 작성해줘","thread_id":"test"}\'')
print()
