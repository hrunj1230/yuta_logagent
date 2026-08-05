from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv
load_dotenv()

# 임베딩 모델

#embedding - local (완전 무료 - 제한 없음)
from langchain_huggingface import HuggingFaceEmbeddings
local_embedding = HuggingFaceEmbeddings(
    model_name="jhgan/ko-sroberta-multitask",  # https://huggingface.co/jhgan/ko-sroberta-multitask # 한국어 모델로 변경
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
) #    model_name="sentence-transformers/all-MiniLM-L6-v2",  # 작고 빠른 모델 기존 모델


#llm - anthropic
# 일지 생성에 쓰는 모델.
# 55일 비교 결과 Sonnet 5를 채택했다 — 확실한 항목(3/3 합의)에서 Opus의 98%
# 수준을 내면서 오탐 의심 항목은 Haiku 수준으로 덜 집는다.
# 근거: docs/journal-model-comparison.md
#
# Sonnet 5는 thinking이 기본으로 켜져 있고 max_tokens가 thinking과 응답을
# 합쳐서 제한하므로 넉넉히 잡는다 (LangChain 기본값 1024로는 잘린다).
ANTHROPIC_MODEL = "claude-sonnet-5"

# 테스트용 더미 데이터를 만드는 모델.
# 더미는 실험의 '입력'이므로 재는 대상(ANTHROPIC_MODEL)과 분리해 품질을 유지한다.
# 여기가 부실하면 일지 품질 저하가 모델 탓인지 재료 탓인지 구분할 수 없다.
SEED_MODEL = "claude-sonnet-5"

anthropic_llm = ChatAnthropic(
    model=ANTHROPIC_MODEL,
    max_tokens=16000,
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
)
codex_llm = ChatOpenAI(
    model="gpt-5-nano",
    max_tokens=16000,
    api_key=os.getenv("CODEX_API_KEY")
)


# 임베딩 함수 별칭 (log 도구에서 사용)
embedding_function = local_embedding

#llm -google (선택적 초기화 - API 키가 있을 때만)
google_api_key = os.getenv("GOOGLE_API_KEY")
if google_api_key:
    google_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=google_api_key
    )
else:
    google_llm = None  # API 키 없으면 None
    print("⚠️  GOOGLE_API_KEY not set. Google LLM will not be available.")
# ChromaDB 클라이언트 설정 (서버 모드)
import chromadb

CHROMADB_HOST = os.getenv("CHROMADB_HOST", "localhost")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8001"))
chroma_client = chromadb.PersistentClient(path="./chroma_db")

#https://docs.langchain.com/oss/python/integrations/providers/overview - codex oauth 제외 모델
#https://github.com/AnthonyTlei/langchain-codex-oauth