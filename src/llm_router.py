from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from dotenv import load_dotenv
load_dotenv()
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

# 임베딩 함수 별칭 (log 도구에서 사용)
embedding_function = local_embedding

#llm -google
google_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    google_api_key = os.getenv("GOOGLE_API_KEY")
)
# ChromaDB 클라이언트 설정 (서버 모드)
import chromadb

CHROMADB_HOST = os.getenv("CHROMADB_HOST", "localhost")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8001"))
chroma_client = chromadb.PersistentClient(path="./chroma_db")

#https://docs.langchain.com/oss/python/integrations/providers/overview - codex oauth 제외 모델
#https://github.com/AnthonyTlei/langchain-codex-oauth