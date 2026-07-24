#!/usr/bin/env python3
"""
ChromaDB 임베딩 확인 스크립트
사용법: python check_embeddings.py [user_id]
"""

import sys
from langchain_chroma import Chroma
import src.llm_router as llm_router

def check_embeddings(user_id: str = "hrun"):
    """
    특정 사용자의 임베딩 확인

    Args:
        user_id: 사용자 ID (기본값: "hrun")
    """
    collection_name = f"user_{user_id}"

    print(f"🔍 컬렉션 확인: {collection_name}")
    print("=" * 60)

    try:
        # Chroma 컬렉션 가져오기
        vectorstore = Chroma(
            collection_name=collection_name,
            embedding_function=llm_router.embedding_function,
            client=llm_router.chroma_client
        )

        # 전체 데이터 가져오기 (메타데이터 포함)
        data = vectorstore.get(include=["metadatas", "documents", "embeddings"])

        total_count = len(data.get("ids", []))

        if total_count == 0:
            print(f"❌ 임베딩 없음. 첫 동기화를 해주세요.")
            return

        print(f"✅ 총 {total_count}개 청크 발견")
        print()

        # 파일별로 그룹화
        file_chunks = {}
        for i, (doc_id, metadata, document) in enumerate(zip(
            data["ids"],
            data["metadatas"],
            data["documents"]
        )):
            source = metadata.get("source", "unknown")
            content_hash = metadata.get("content_hash", "없음")

            if source not in file_chunks:
                file_chunks[source] = []

            file_chunks[source].append({
                "id": doc_id,
                "hash": content_hash,
                "length": len(document),
                "preview": document[:100] + "..." if len(document) > 100 else document
            })

        # 파일별 통계
        print(f"📁 파일별 청크 현황:")
        print("-" * 60)

        for source, chunks in sorted(file_chunks.items()):
            print(f"\n{source}")
            print(f"  청크 수: {len(chunks)}개")
            print(f"  Content Hash: {chunks[0]['hash'][:16]}...")

            # 첫 번째 청크 미리보기
            if len(chunks) > 0:
                print(f"  첫 청크 미리보기: {chunks[0]['preview']}")

        print()
        print("=" * 60)
        print(f"📊 요약:")
        print(f"  - 총 파일: {len(file_chunks)}개")
        print(f"  - 총 청크: {total_count}개")
        print(f"  - 평균 청크/파일: {total_count / len(file_chunks):.1f}개")

        # 벡터 차원 확인 (임베딩이 실제로 있는지)
        if data.get("embeddings") and len(data["embeddings"]) > 0:
            embedding_dim = len(data["embeddings"][0])
            print(f"  - 벡터 차원: {embedding_dim}차원 ✅")
        else:
            print(f"  - 벡터 차원: 확인 불가 ❌")

    except Exception as e:
        print(f"❌ 에러: {str(e)}")
        print(f"💡 컬렉션 '{collection_name}'이 존재하지 않을 수 있습니다.")


def list_all_collections():
    """모든 컬렉션 목록 확인"""
    print("🗂️ 전체 컬렉션 목록:")
    print("=" * 60)

    try:
        collections = llm_router.chroma_client.list_collections()

        if not collections:
            print("❌ 컬렉션 없음")
            return

        for collection in collections:
            print(f"\n📦 {collection.name}")
            print(f"  - 문서 수: {collection.count()}개")

    except Exception as e:
        print(f"❌ 에러: {str(e)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ChromaDB 임베딩 확인")
    parser.add_argument("user_id", nargs="?", default="hrun", help="사용자 ID (기본값: hrun)")
    parser.add_argument("--list", action="store_true", help="모든 컬렉션 목록 보기")

    args = parser.parse_args()

    if args.list:
        list_all_collections()
    else:
        check_embeddings(args.user_id)
