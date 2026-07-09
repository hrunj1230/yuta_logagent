from langchain_google_genai import ChatGoogleGenerativeAI
#from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langchain_codex_oauth import ChatCodexOAuth
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import GoogleGenerativeAIEmbeddings

import os

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
#llm - anthropic
anthropic_llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
)

#https://docs.langchain.com/oss/python/integrations/providers/overview - codex oauth 제외 모델
#https://github.com/AnthonyTlei/langchain-codex-oauth