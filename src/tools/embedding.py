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
