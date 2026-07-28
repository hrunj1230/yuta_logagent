from langchain_core.tools import tool
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from ..storage.database import SessionLocal
from ..storage.models import Source, SourceType, EmbeddingStatus
from ..llm_router import google_embedding
import os
import hashlib
import subprocess
import json
from pathlib import Path
from datetime import datetime
import time

# 설정
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 400
DATA_DIR = Path("./data/sources")
CHROMA_DIR = Path("./chroma_db")
TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".tsx", ".jsx", ".java", ".go", ".rs", ".c", ".cpp", ".h"}


def _get_chroma_collection(user_id: str):
    """사용자별 ChromaDB Collection 가져오기"""
    collection_name = f"user_{user_id}"

    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=google_embedding,
        persist_directory=str(CHROMA_DIR)
    )

    return vectorstore._collection


def _save_to_chromadb(chunks: list[Document], user_id: str):
    """청크를 ChromaDB에 저장"""
    if not chunks:
        return

    collection_name = f"user_{user_id}"

    Chroma.from_documents(
        documents=chunks,
        embedding=google_embedding,
        collection_name=collection_name,
        persist_directory=str(CHROMA_DIR)
    )


def _delete_source_embeddings(user_id: str, source_id: int) -> int:
    """특정 소스의 모든 임베딩 삭제"""
    try:
        collection = _get_chroma_collection(user_id)

        results = collection.get(
            where={"source_id": source_id},
            include=["metadatas"]
        )

        ids_to_delete = results.get("ids", [])

        if ids_to_delete:
            collection.delete(ids=ids_to_delete)

        return len(ids_to_delete)
    except Exception as e:
        print(f"ChromaDB 삭제 중 오류: {e}")
        return 0
