from langchain_google_genai import ChatGoogleGenerativeAI
#from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langchain_codex_oauth import ChatCodexOAuth
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import GoogleGenerativeAIEmbeddings

import os
from dotenv import load_dotenv
load_dotenv()
#embedding - google (AWS 배포용 - 메모리 절약)
google_embedding = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",  # 최신 임베딩 모델
    google_api_key = os.getenv("GOOGLE_API_KEY")
)

#llm -google
google_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    google_api_key = os.getenv("GOOGLE_API_KEY")
)

#llm -openai oauth(local test)
codex_llm = ChatCodexOAuth(
    model="gpt-5.4-mini"
)

#llm - anthropic
anthropic_llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929",  # 최신 Sonnet 4.5 모델
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
)

# ========== 임베딩 모델 선택 (환경변수로 제어) ==========
EMBEDDING_MODE = os.getenv("EMBEDDING_MODE", "google")  # "google" 또는 "local"

if EMBEDDING_MODE == "local":
    # 로컬 임베딩 (개발 환경용 - 메모리 5-6GB 필요)
    print("[Embedding] 🖥️ 로컬 모델 사용 (메모리: ~6GB)")
    from langchain_huggingface import HuggingFaceEmbeddings
    local_embedding = HuggingFaceEmbeddings(
        model_name="jhgan/ko-sroberta-multitask",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )
    # 사용할 임베딩
    embedding_function = local_embedding
else:
    # Google API 임베딩 (프로덕션/AWS용 - 메모리 0MB)
    print("[Embedding] ☁️ Google Gemini API 사용 (메모리: 0MB)")
    # 사용할 임베딩
    embedding_function = google_embedding


# ChromaDB 클라이언트 설정 (서버 모드)
import chromadb
from chromadb.config import Settings

CHROMADB_HOST = os.getenv("CHROMADB_HOST", "localhost")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8001"))

try:
    # 서버 모드 시도
    chroma_client = chromadb.HttpClient(
        host=CHROMADB_HOST,
        port=CHROMADB_PORT,
        settings=Settings(
            anonymized_telemetry=False
        )
    )
    # 서버 연결 테스트
    chroma_client.heartbeat()
    print(f"[ChromaDB] ✅ 서버 연결 성공: {CHROMADB_HOST}:{CHROMADB_PORT}")
except Exception as e:
    # 서버 연결 실패 시 로컬 모드로 폴백
    print(f"[ChromaDB] ⚠️ 서버 연결 실패 ({e}), 로컬 모드로 전환")
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    print(f"[ChromaDB] 📁 로컬 모드 사용: ./chroma_db")

#https://docs.langchain.com/oss/python/integrations/providers/overview - codex oauth 제외 모델
#https://github.com/AnthonyTlei/langchain-codex-oauth