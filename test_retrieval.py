#!/usr/bin/env python3
"""
특정 날짜 검색 테스트
"""

import chromadb
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 임베딩 모델 (llm_router.py와 동일)
local_embedding = HuggingFaceEmbeddings(
    model_name="jhgan/ko-sroberta-multitask",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

# ChromaDB 연결
client = chromadb.PersistentClient(path="./chroma_db")

# Chroma 연결 (tools.py의 retriever_vectordb와 동일)
reopened = Chroma(
    collection_name="user_hrun",  # 여기가 중요!
    embedding_function=local_embedding,
    client=client,
)

print("=" * 60)
print("🔍 2026-07-09 날짜 검색 테스트")
print("=" * 60)
print()

# 1차: 메타데이터 필터로 정확한 날짜 찾기
print("1️⃣ 메타데이터 필터 검색")
print("-" * 60)

try:
    docs = reopened.get(
        where={"date": "2026-07-09"},
        limit=5
    )

    if docs and docs.get('documents'):
        print(f"✅ 검색 성공! {len(docs['documents'])}개 문서 발견\n")

        for i, (doc, meta) in enumerate(zip(docs['documents'], docs['metadatas']), 1):
            print(f"--- 문서 {i} ---")
            print(f"메타데이터: {meta}")
            print(f"내용 미리보기: {doc[:150]}...")
            print()
    else:
        print("❌ 메타데이터 검색 실패\n")

        # 2차: 유사도 검색 시도
        print("2️⃣ 유사도 검색 (폴백)")
        print("-" * 60)

        docs_similarity = reopened.similarity_search(
            "작성 날짜: 2026년 7월 9일",
            k=5
        )

        if docs_similarity:
            print(f"✅ 유사도 검색 성공! {len(docs_similarity)}개 문서 발견\n")

            for i, doc in enumerate(docs_similarity, 1):
                print(f"--- 문서 {i} ---")
                print(f"메타데이터: {doc.metadata}")
                print(f"내용 미리보기: {doc.page_content[:150]}...")
                print()
        else:
            print("❌ 유사도 검색도 실패")

except Exception as e:
    print(f"❌ 에러 발생: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 60)

# 컬렉션 확인
print("📦 컬렉션 정보")
print("=" * 60)

collection = client.get_collection("user_hrun")
print(f"컬렉션: user_hrun")
print(f"문서 수: {collection.count()}개")

# 2026-07-09 확인
all_data = collection.get(include=["metadatas"])
dates = [m.get('date') for m in all_data['metadatas'] if m and m.get('date') == '2026-07-09']
print(f"2026-07-09 문서: {len(dates)}개")
print()
