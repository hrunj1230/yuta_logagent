from langchain_google_genai import ChatGoogleGenerativeAI
#from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langchain_codex_oauth import ChatCodexOAuth
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import GoogleGenerativeAIEmbeddings

import os
from dotenv import load_dotenv
load_dotenv()
#embedding - google
google_embedding = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key = os.getenv("GOOGLE_API_KEY")
)

#llm -google (embedding 으로 인해 임시 제외)
google_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    google_api_key = os.getenv("GOOGLE_API_KEY")
)
#llm -openai oauth(local test)
codex_llm = ChatCodexOAuth(
    model="gpt-5.4-mini"
)
# 임베딩은 local_embedding 사용 (아래에 정의됨)
#llm - anthropic
anthropic_llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929",  # 최신 Sonnet 4.5 모델
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
)

#embedding - local (완전 무료 - 제한 없음)
from langchain_huggingface import HuggingFaceEmbeddings
local_embedding = HuggingFaceEmbeddings(
    model_name="jhgan/ko-sroberta-multitask",  # https://huggingface.co/jhgan/ko-sroberta-multitask # 한국어 모델로 변경
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
) #    model_name="sentence-transformers/all-MiniLM-L6-v2",  # 작고 빠른 모델 기존 모델


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