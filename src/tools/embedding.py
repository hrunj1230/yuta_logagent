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


def _split_documents(documents: list[Document]) -> list[Document]:
    """문서를 청크로 분할"""
    if not documents:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    chunks = []
    for doc in documents:
        doc_chunks = splitter.split_documents([doc])

        # 청크 인덱스 추가
        for idx, chunk in enumerate(doc_chunks):
            chunk.metadata["chunk_index"] = idx
            chunks.append(chunk)

    return chunks


def _filter_new_documents(documents: list[Document], user_id: str, source_id: int) -> tuple[list[Document], int]:
    """기존 임베딩과 비교하여 새 문서만 반환"""
    try:
        collection = _get_chroma_collection(user_id)

        # 기존 해시 목록 가져오기
        results = collection.get(
            where={"source_id": source_id},
            include=["metadatas"]
        )
        existing_hashes = set()
        for metadata in results.get("metadatas", []):
            if "file_hash" in metadata:
                existing_hashes.add(metadata["file_hash"])
            elif "commit_sha" in metadata:
                existing_hashes.add(metadata["commit_sha"])
    except Exception as e:
        print(f"기존 임베딩 조회 중 오류 (새 Collection 생성): {e}")
        existing_hashes = set()

    # 새 문서 필터링
    new_docs = []
    skipped = 0

    for doc in documents:
        doc_hash = doc.metadata.get("file_hash") or doc.metadata.get("commit_sha")
        if doc_hash not in existing_hashes:
            new_docs.append(doc)
        else:
            skipped += 1

    return new_docs, skipped


def _collect_git_files(source: Source, user_id: str) -> list[Document]:
    """Git 저장소를 clone하고 텍스트 파일 수집"""
    repo_dir = DATA_DIR / user_id / source.name

    # Clone 또는 Pull
    if repo_dir.exists():
        # Git pull
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "pull"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git pull 실패: {result.stderr}")
    else:
        # Git clone
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", source.location, str(repo_dir)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git clone 실패: {result.stderr}")

    # 텍스트 파일 수집
    documents = []

    for file_path in repo_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix in TEXT_EXTENSIONS:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 파일 해시 계산
                file_hash = hashlib.sha256(content.encode()).hexdigest()

                # 상대 경로
                rel_path = file_path.relative_to(repo_dir)

                doc = Document(
                    page_content=content,
                    metadata={
                        "user_id": user_id,
                        "source_id": source.id,
                        "source_type": source.type.value,
                        "source_name": source.name,
                        "file_path": str(rel_path),
                        "file_hash": file_hash,
                        "embedded_at": datetime.now().isoformat()
                    }
                )
                documents.append(doc)

            except Exception as e:
                print(f"파일 읽기 실패 {file_path}: {e}")
                continue

    return documents
