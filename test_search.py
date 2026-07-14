#!/usr/bin/env python3
"""ChromaDB 검색 테스트"""

from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# 로컬 임베딩 모델 (tools.py와 동일)
local_embedding = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)

# ChromaDB 열기
vectorstore = Chroma(
    embedding_function=local_embedding,
    persist_directory="./chroma_db",
)

# 전체 문서 수 확인
collection = vectorstore._collection
print(f"총 문서 수: {collection.count()}")
print()

# 여러 검색 쿼리 테스트
test_queries = [
    "2026-07-09",
    "2026년 7월 9일",
    "7월 9일",
    "07-09",
    "langgraph",
    "agent",
    "python",
]

for query in test_queries:
    print(f"=== 검색 쿼리: '{query}' ===")
    results = vectorstore.similarity_search(query, k=3)

    if not results:
        print("  검색 결과 없음")
    else:
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "unknown")
            doc_type = doc.metadata.get("type", "document")
            content_preview = doc.page_content[:150].replace("\n", " ")

            print(f"  [{i}] {source}")
            print(f"      타입: {doc_type}")
            print(f"      내용: {content_preview}...")
    print()
