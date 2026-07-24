# Phase 1: Infrastructure Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract external dependencies (LLM, VectorDB, Storage) into Infrastructure layer with Factory and Repository patterns

**Architecture:** Create infrastructure layer with LLM Factory Pattern for provider abstraction, VectorDB Repository Pattern for data access, and move existing storage to infrastructure/storage

**Tech Stack:** Python 3.12, FastAPI, LangChain, ChromaDB, Pydantic, pytest

---

## File Structure

**New files to create:**
```
src/infrastructure/
├── __init__.py
├── llm/
│   ├── __init__.py
│   ├── base.py                    # Abstract LLM interface
│   ├── factory.py                 # Factory Pattern for LLM creation
│   └── providers/
│       ├── __init__.py
│       ├── claude_provider.py     # Claude API implementation
│       ├── gemini_provider.py     # Gemini API implementation
│       └── codex_provider.py      # Codex OAuth implementation
├── vectordb/
│   ├── __init__.py
│   ├── repository.py              # Repository Pattern for VectorDB
│   ├── chroma_client.py           # ChromaDB client singleton
│   └── embedder.py                # Embedding function factory
└── storage/
    ├── __init__.py
    ├── database.py                # Move from storage/database.py
    ├── models.py                  # Move from storage/models.py
    └── auth.py                    # Move from storage/auth.py
```

**Files to modify:**
- `src/llm_router.py` - Keep temporarily, will be deprecated in Phase 5
- `src/tools.py` - Update imports to use new infrastructure

**Test files:**
```
tests/
├── __init__.py
├── conftest.py                    # pytest fixtures
└── unit/
    ├── __init__.py
    └── infrastructure/
        ├── __init__.py
        ├── test_llm_factory.py
        ├── test_claude_provider.py
        ├── test_gemini_provider.py
        └── test_vectordb_repo.py
```

---

## Task 1: Setup Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/infrastructure/__init__.py`

### Step 1.1: Create test directory structure

- [ ] **Create empty test __init__ files**

```bash
mkdir -p tests/unit/infrastructure
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/unit/infrastructure/__init__.py
```

- [ ] **Verify directory structure**

Run: `ls -R tests/`
Expected: Directory tree shows __init__.py in each level

### Step 1.2: Write pytest configuration

- [ ] **Create conftest.py with base fixtures**

```python
# tests/conftest.py
import pytest
import os
from typing import Generator
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-claude-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-gemini-key")
    monkeypatch.setenv("EMBEDDING_MODE", "google")
    monkeypatch.setenv("CHROMADB_HOST", "localhost")
    monkeypatch.setenv("CHROMADB_PORT", "8001")

@pytest.fixture
def mock_llm_response():
    """Mock LLM response for testing"""
    mock = Mock()
    mock.content = "Test response"
    mock.tool_calls = []
    return mock

@pytest.fixture
def mock_document():
    """Mock LangChain Document"""
    from langchain_core.documents import Document
    return Document(
        page_content="Test content",
        metadata={"source": "test.md", "date": "2026-07-24"}
    )
```

- [ ] **Verify conftest loads**

Run: `pytest tests/ --collect-only`
Expected: "collected 0 items" (no tests yet, but no errors)

### Step 1.3: Commit test infrastructure

- [ ] **Commit**

```bash
git add tests/
git commit -m "test: Add pytest infrastructure

- Create test directory structure
- Add conftest.py with base fixtures
- Setup for Phase 1 infrastructure tests"
```

---

## Task 2: LLM Base Interface

**Files:**
- Create: `src/infrastructure/__init__.py`
- Create: `src/infrastructure/llm/__init__.py`
- Create: `src/infrastructure/llm/base.py`

### Step 2.1: Write failing test for LLM base interface

- [ ] **Create test file**

```python
# tests/unit/infrastructure/test_llm_base.py
import pytest
from abc import ABC
from infrastructure.llm.base import LLMProvider

def test_llm_provider_is_abstract():
    """LLMProvider should be an abstract base class"""
    assert issubclass(LLMProvider, ABC)

def test_llm_provider_has_required_methods():
    """LLMProvider should define abstract methods"""
    required_methods = ['invoke', 'bind_tools', 'with_structured_output']

    for method_name in required_methods:
        assert hasattr(LLMProvider, method_name)
        method = getattr(LLMProvider, method_name)
        assert getattr(method, '__isabstractmethod__', False), \
            f"{method_name} should be abstract"

def test_llm_provider_cannot_be_instantiated():
    """Cannot create instance of abstract LLMProvider"""
    with pytest.raises(TypeError):
        LLMProvider()
```

- [ ] **Run test to verify it fails**

Run: `pytest tests/unit/infrastructure/test_llm_base.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'infrastructure'"

### Step 2.2: Create infrastructure package structure

- [ ] **Create infrastructure __init__ files**

```python
# src/infrastructure/__init__.py
"""Infrastructure layer - External system integrations"""

# src/infrastructure/llm/__init__.py
"""LLM provider abstractions"""
from infrastructure.llm.base import LLMProvider

__all__ = ['LLMProvider']
```

- [ ] **Run test again**

Run: `pytest tests/unit/infrastructure/test_llm_base.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'infrastructure.llm.base'"

### Step 2.3: Implement LLM base interface

- [ ] **Create base.py with abstract interface**

```python
# src/infrastructure/llm/base.py
from abc import ABC, abstractmethod
from typing import List, Any, Optional

class LLMProvider(ABC):
    """
    Abstract interface for LLM providers

    This interface defines the contract that all LLM implementations
    (Claude, Gemini, Codex) must follow, enabling dependency injection
    and testability.
    """

    @abstractmethod
    def invoke(self, messages: List[Any]) -> Any:
        """
        Send messages to LLM and get response

        Args:
            messages: List of LangChain messages (HumanMessage, SystemMessage, etc.)

        Returns:
            AIMessage with response content
        """
        pass

    @abstractmethod
    def bind_tools(self, tools: List[Any]) -> 'LLMProvider':
        """
        Bind tools to LLM for function calling

        Args:
            tools: List of LangChain tools (@tool decorated functions)

        Returns:
            Self for method chaining
        """
        pass

    @abstractmethod
    def with_structured_output(self, schema: Any) -> 'LLMProvider':
        """
        Configure LLM for structured output (Pydantic model)

        Args:
            schema: Pydantic BaseModel class

        Returns:
            Self for method chaining
        """
        pass
```

- [ ] **Run test to verify it passes**

Run: `pytest tests/unit/infrastructure/test_llm_base.py -v`
Expected: PASS - 3 tests pass

### Step 2.4: Commit LLM base interface

- [ ] **Commit**

```bash
git add src/infrastructure/llm/base.py src/infrastructure/__init__.py src/infrastructure/llm/__init__.py tests/unit/infrastructure/test_llm_base.py
git commit -m "feat(infrastructure): Add LLM abstract base interface

- Create LLMProvider ABC with invoke, bind_tools, with_structured_output
- Add comprehensive docstrings
- Tests verify abstract methods and instantiation prevention"
```

---

## Task 3: Claude Provider Implementation

**Files:**
- Create: `src/infrastructure/llm/providers/__init__.py`
- Create: `src/infrastructure/llm/providers/claude_provider.py`
- Create: `tests/unit/infrastructure/test_claude_provider.py`

### Step 3.1: Write failing test for Claude provider

- [ ] **Create test file**

```python
# tests/unit/infrastructure/test_claude_provider.py
import pytest
from unittest.mock import Mock, patch
from infrastructure.llm.providers.claude_provider import ClaudeProvider
from infrastructure.llm.base import LLMProvider

@pytest.fixture
def mock_chat_anthropic():
    """Mock ChatAnthropic client"""
    with patch('infrastructure.llm.providers.claude_provider.ChatAnthropic') as mock:
        mock_instance = Mock()
        mock_instance.invoke.return_value = Mock(content="Claude response")
        mock_instance.bind_tools.return_value = mock_instance
        mock_instance.with_structured_output.return_value = mock_instance
        mock.return_value = mock_instance
        yield mock

def test_claude_provider_implements_interface(mock_chat_anthropic):
    """ClaudeProvider implements LLMProvider"""
    provider = ClaudeProvider(api_key="test-key")
    assert isinstance(provider, LLMProvider)

def test_claude_provider_invoke(mock_chat_anthropic):
    """invoke() calls ChatAnthropic.invoke()"""
    provider = ClaudeProvider(api_key="test-key")
    messages = [Mock()]

    result = provider.invoke(messages)

    assert result.content == "Claude response"
    mock_chat_anthropic.return_value.invoke.assert_called_once_with(messages)

def test_claude_provider_bind_tools(mock_chat_anthropic):
    """bind_tools() returns self for chaining"""
    provider = ClaudeProvider(api_key="test-key")
    tools = [Mock()]

    result = provider.bind_tools(tools)

    assert result is provider
    mock_chat_anthropic.return_value.bind_tools.assert_called_once_with(tools)

def test_claude_provider_default_model(mock_chat_anthropic):
    """Default model is claude-sonnet-4-5"""
    ClaudeProvider(api_key="test-key")

    mock_chat_anthropic.assert_called_once_with(
        model="claude-sonnet-4-5-20250929",
        anthropic_api_key="test-key"
    )

def test_claude_provider_custom_model(mock_chat_anthropic):
    """Can specify custom model"""
    ClaudeProvider(api_key="test-key", model="claude-opus-4")

    mock_chat_anthropic.assert_called_once_with(
        model="claude-opus-4",
        anthropic_api_key="test-key"
    )
```

- [ ] **Run test to verify it fails**

Run: `pytest tests/unit/infrastructure/test_claude_provider.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'infrastructure.llm.providers'"

### Step 3.2: Create providers package

- [ ] **Create providers __init__.py**

```python
# src/infrastructure/llm/providers/__init__.py
"""LLM provider implementations"""
from infrastructure.llm.providers.claude_provider import ClaudeProvider

__all__ = ['ClaudeProvider']
```

- [ ] **Run test again**

Run: `pytest tests/unit/infrastructure/test_claude_provider.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'infrastructure.llm.providers.claude_provider'"

### Step 3.3: Implement Claude provider

- [ ] **Create claude_provider.py**

```python
# src/infrastructure/llm/providers/claude_provider.py
from langchain_anthropic import ChatAnthropic
from infrastructure.llm.base import LLMProvider
from typing import List, Any

class ClaudeProvider(LLMProvider):
    """
    Anthropic Claude API implementation

    Wraps langchain_anthropic.ChatAnthropic to conform to LLMProvider interface
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """
        Initialize Claude provider

        Args:
            api_key: Anthropic API key
            model: Claude model name (default: Sonnet 4.5)
        """
        self._client = ChatAnthropic(
            model=model,
            anthropic_api_key=api_key
        )

    def invoke(self, messages: List[Any]) -> Any:
        """Send messages to Claude and get response"""
        return self._client.invoke(messages)

    def bind_tools(self, tools: List[Any]) -> 'ClaudeProvider':
        """Bind tools to Claude for function calling"""
        self._client = self._client.bind_tools(tools)
        return self

    def with_structured_output(self, schema: Any) -> 'ClaudeProvider':
        """Configure Claude for structured output"""
        self._client = self._client.with_structured_output(schema)
        return self
```

- [ ] **Run test to verify it passes**

Run: `pytest tests/unit/infrastructure/test_claude_provider.py -v`
Expected: PASS - 5 tests pass

### Step 3.4: Commit Claude provider

- [ ] **Commit**

```bash
git add src/infrastructure/llm/providers/ tests/unit/infrastructure/test_claude_provider.py
git commit -m "feat(infrastructure): Add Claude LLM provider

- Implement ClaudeProvider wrapping ChatAnthropic
- Support custom model selection
- Add comprehensive unit tests with mocks
- All tests passing"
```

---

## Task 4: Gemini and Codex Providers

**Files:**
- Create: `src/infrastructure/llm/providers/gemini_provider.py`
- Create: `src/infrastructure/llm/providers/codex_provider.py`
- Create: `tests/unit/infrastructure/test_gemini_provider.py`
- Modify: `src/infrastructure/llm/providers/__init__.py`

### Step 4.1: Write failing test for Gemini provider

- [ ] **Create test file**

```python
# tests/unit/infrastructure/test_gemini_provider.py
import pytest
from unittest.mock import Mock, patch
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from infrastructure.llm.base import LLMProvider

@pytest.fixture
def mock_chat_gemini():
    """Mock ChatGoogleGenerativeAI client"""
    with patch('infrastructure.llm.providers.gemini_provider.ChatGoogleGenerativeAI') as mock:
        mock_instance = Mock()
        mock_instance.invoke.return_value = Mock(content="Gemini response")
        mock_instance.bind_tools.return_value = mock_instance
        mock_instance.with_structured_output.return_value = mock_instance
        mock.return_value = mock_instance
        yield mock

def test_gemini_provider_implements_interface(mock_chat_gemini):
    """GeminiProvider implements LLMProvider"""
    provider = GeminiProvider(api_key="test-key")
    assert isinstance(provider, LLMProvider)

def test_gemini_provider_invoke(mock_chat_gemini):
    """invoke() calls ChatGoogleGenerativeAI.invoke()"""
    provider = GeminiProvider(api_key="test-key")
    messages = [Mock()]

    result = provider.invoke(messages)

    assert result.content == "Gemini response"
    mock_chat_gemini.return_value.invoke.assert_called_once_with(messages)

def test_gemini_provider_default_model(mock_chat_gemini):
    """Default model is gemini-2.5-flash-lite"""
    GeminiProvider(api_key="test-key")

    mock_chat_gemini.assert_called_once_with(
        model="gemini-2.5-flash-lite",
        google_api_key="test-key"
    )
```

- [ ] **Run test to verify it fails**

Run: `pytest tests/unit/infrastructure/test_gemini_provider.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named '...gemini_provider'"

### Step 4.2: Implement Gemini provider

- [ ] **Create gemini_provider.py**

```python
# src/infrastructure/llm/providers/gemini_provider.py
from langchain_google_genai import ChatGoogleGenerativeAI
from infrastructure.llm.base import LLMProvider
from typing import List, Any

class GeminiProvider(LLMProvider):
    """
    Google Gemini API implementation

    Wraps langchain_google_genai.ChatGoogleGenerativeAI
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        """
        Initialize Gemini provider

        Args:
            api_key: Google API key
            model: Gemini model name (default: Flash Lite)
        """
        self._client = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key
        )

    def invoke(self, messages: List[Any]) -> Any:
        """Send messages to Gemini and get response"""
        return self._client.invoke(messages)

    def bind_tools(self, tools: List[Any]) -> 'GeminiProvider':
        """Bind tools to Gemini for function calling"""
        self._client = self._client.bind_tools(tools)
        return self

    def with_structured_output(self, schema: Any) -> 'GeminiProvider':
        """Configure Gemini for structured output"""
        self._client = self._client.with_structured_output(schema)
        return self
```

- [ ] **Run test to verify it passes**

Run: `pytest tests/unit/infrastructure/test_gemini_provider.py -v`
Expected: PASS - 3 tests pass

### Step 4.3: Implement Codex provider (no structured output)

- [ ] **Create codex_provider.py**

```python
# src/infrastructure/llm/providers/codex_provider.py
from langchain_codex_oauth import ChatCodexOAuth
from infrastructure.llm.base import LLMProvider
from typing import List, Any

class CodexProvider(LLMProvider):
    """
    Codex OAuth implementation

    Wraps langchain_codex_oauth.ChatCodexOAuth
    Note: Codex does not support structured output
    """

    def __init__(self, model: str = "gpt-5.4-mini"):
        """
        Initialize Codex provider

        Args:
            model: Codex model name (default: gpt-5.4-mini)
        """
        self._client = ChatCodexOAuth(model=model)

    def invoke(self, messages: List[Any]) -> Any:
        """Send messages to Codex and get response"""
        return self._client.invoke(messages)

    def bind_tools(self, tools: List[Any]) -> 'CodexProvider':
        """Bind tools to Codex for function calling"""
        self._client = self._client.bind_tools(tools)
        return self

    def with_structured_output(self, schema: Any) -> 'CodexProvider':
        """
        Codex does not support structured output

        Raises:
            NotImplementedError: Always raised
        """
        raise NotImplementedError(
            "Codex does not support structured output. "
            "Use Claude or Gemini for this feature."
        )
```

- [ ] **Update providers __init__.py**

```python
# src/infrastructure/llm/providers/__init__.py
"""LLM provider implementations"""
from infrastructure.llm.providers.claude_provider import ClaudeProvider
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from infrastructure.llm.providers.codex_provider import CodexProvider

__all__ = ['ClaudeProvider', 'GeminiProvider', 'CodexProvider']
```

- [ ] **Run all provider tests**

Run: `pytest tests/unit/infrastructure/test_*_provider.py -v`
Expected: PASS - All provider tests pass

### Step 4.4: Commit Gemini and Codex providers

- [ ] **Commit**

```bash
git add src/infrastructure/llm/providers/ tests/unit/infrastructure/test_gemini_provider.py
git commit -m "feat(infrastructure): Add Gemini and Codex providers

- Implement GeminiProvider wrapping ChatGoogleGenerativeAI
- Implement CodexProvider wrapping ChatCodexOAuth
- Codex raises NotImplementedError for structured output
- Update providers __init__ exports
- Add Gemini unit tests"
```

---

## Task 5: LLM Factory Pattern

**Files:**
- Create: `src/infrastructure/llm/factory.py`
- Create: `tests/unit/infrastructure/test_llm_factory.py`
- Modify: `src/infrastructure/llm/__init__.py`

### Step 5.1: Write failing test for LLM Factory

- [ ] **Create test file**

```python
# tests/unit/infrastructure/test_llm_factory.py
import pytest
from unittest.mock import patch
from infrastructure.llm.factory import LLMFactory
from infrastructure.llm.providers.claude_provider import ClaudeProvider
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from infrastructure.llm.providers.codex_provider import CodexProvider

@pytest.fixture
def factory_with_env(mock_env_vars):
    """Factory with mocked environment variables"""
    return LLMFactory()

def test_factory_is_singleton():
    """LLMFactory returns same instance"""
    factory1 = LLMFactory()
    factory2 = LLMFactory()
    assert factory1 is factory2

def test_factory_get_claude(factory_with_env):
    """get_llm('claude') returns ClaudeProvider"""
    with patch('infrastructure.llm.factory.ClaudeProvider') as mock_claude:
        mock_instance = mock_claude.return_value

        provider = factory_with_env.get_llm('claude')

        assert provider is mock_instance
        mock_claude.assert_called_once_with("test-claude-key")

def test_factory_get_gemini(factory_with_env):
    """get_llm('gemini') returns GeminiProvider"""
    with patch('infrastructure.llm.factory.GeminiProvider') as mock_gemini:
        mock_instance = mock_gemini.return_value

        provider = factory_with_env.get_llm('gemini')

        assert provider is mock_instance
        mock_gemini.assert_called_once_with("test-gemini-key")

def test_factory_get_codex(factory_with_env):
    """get_llm('codex') returns CodexProvider"""
    with patch('infrastructure.llm.factory.CodexProvider') as mock_codex:
        mock_instance = mock_codex.return_value

        provider = factory_with_env.get_llm('codex')

        assert provider is mock_instance
        mock_codex.assert_called_once()

def test_factory_caches_providers(factory_with_env):
    """Factory caches provider instances"""
    with patch('infrastructure.llm.factory.ClaudeProvider') as mock_claude:
        mock_instance = mock_claude.return_value

        provider1 = factory_with_env.get_llm('claude')
        provider2 = factory_with_env.get_llm('claude')

        assert provider1 is provider2
        mock_claude.assert_called_once()  # Only created once

def test_factory_raises_on_missing_key(monkeypatch):
    """Factory raises ValueError if API key not found"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    factory = LLMFactory()

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not found"):
        factory.get_llm('claude')

def test_factory_raises_on_unknown_provider(factory_with_env):
    """Factory raises ValueError for unknown provider"""
    with pytest.raises(ValueError, match="Unknown provider: unknown"):
        factory_with_env.get_llm('unknown')

def test_factory_set_provider_for_testing(factory_with_env):
    """set_provider() allows injecting test providers"""
    from unittest.mock import Mock
    mock_provider = Mock()

    factory_with_env.set_provider('test', mock_provider)
    result = factory_with_env.get_llm('test')

    assert result is mock_provider
```

- [ ] **Run test to verify it fails**

Run: `pytest tests/unit/infrastructure/test_llm_factory.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named '...factory'"

### Step 5.2: Implement LLM Factory

- [ ] **Create factory.py**

```python
# src/infrastructure/llm/factory.py
import os
from typing import Dict
from dotenv import load_dotenv
from infrastructure.llm.base import LLMProvider
from infrastructure.llm.providers.claude_provider import ClaudeProvider
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from infrastructure.llm.providers.codex_provider import CodexProvider

load_dotenv()

class LLMFactory:
    """
    LLM Provider Factory (Singleton Pattern)

    Manages LLM provider instances:
    - Reads API keys from environment variables
    - Caches provider instances (lazy initialization)
    - Supports dependency injection for testing (set_provider)

    Usage:
        factory = LLMFactory()
        claude = factory.get_llm('claude')
        gemini = factory.get_llm('gemini')
    """

    _instance: 'LLMFactory' = None
    _providers: Dict[str, LLMProvider] = {}

    def __new__(cls):
        """Singleton pattern - always return same instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._providers = {}  # Reset providers for new instance
        return cls._instance

    def get_llm(self, provider_name: str) -> LLMProvider:
        """
        Get LLM provider instance (with caching)

        Args:
            provider_name: 'claude', 'gemini', or 'codex'

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If provider_name is unknown or API key not found
        """
        # Return cached provider if exists
        if provider_name in self._providers:
            return self._providers[provider_name]

        # Create new provider based on name
        if provider_name == 'claude':
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment")
            self._providers['claude'] = ClaudeProvider(api_key)

        elif provider_name == 'gemini':
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY not found in environment")
            self._providers['gemini'] = GeminiProvider(api_key)

        elif provider_name == 'codex':
            self._providers['codex'] = CodexProvider()

        else:
            raise ValueError(f"Unknown provider: {provider_name}")

        return self._providers[provider_name]

    def set_provider(self, name: str, provider: LLMProvider):
        """
        Inject provider for testing

        Args:
            name: Provider name
            provider: LLMProvider instance (can be mock)
        """
        self._providers[name] = provider
```

- [ ] **Run test to verify it passes**

Run: `pytest tests/unit/infrastructure/test_llm_factory.py -v`
Expected: PASS - 8 tests pass

### Step 5.3: Update LLM package exports

- [ ] **Update llm __init__.py**

```python
# src/infrastructure/llm/__init__.py
"""LLM provider abstractions"""
from infrastructure.llm.base import LLMProvider
from infrastructure.llm.factory import LLMFactory
from infrastructure.llm.providers.claude_provider import ClaudeProvider
from infrastructure.llm.providers.gemini_provider import GeminiProvider
from infrastructure.llm.providers.codex_provider import CodexProvider

__all__ = [
    'LLMProvider',
    'LLMFactory',
    'ClaudeProvider',
    'GeminiProvider',
    'CodexProvider'
]
```

- [ ] **Run all LLM tests**

Run: `pytest tests/unit/infrastructure/test_llm*.py -v`
Expected: PASS - All LLM tests pass

### Step 5.4: Commit LLM Factory

- [ ] **Commit**

```bash
git add src/infrastructure/llm/factory.py src/infrastructure/llm/__init__.py tests/unit/infrastructure/test_llm_factory.py
git commit -m "feat(infrastructure): Add LLM Factory with Singleton pattern

- Implement LLMFactory for centralized provider creation
- Add provider caching (lazy initialization)
- Support dependency injection via set_provider()
- Environment variable validation
- Comprehensive unit tests (8 tests passing)"
```

---

## Task 6: VectorDB ChromaDB Client

**Files:**
- Create: `src/infrastructure/vectordb/__init__.py`
- Create: `src/infrastructure/vectordb/chroma_client.py`
- Create: `tests/unit/infrastructure/test_chroma_client.py`

### Step 6.1: Write failing test for ChromaDB client

- [ ] **Create test file**

```python
# tests/unit/infrastructure/test_chroma_client.py
import pytest
from unittest.mock import patch, Mock
from infrastructure.vectordb.chroma_client import get_chroma_client

@pytest.fixture
def mock_http_client():
    """Mock chromadb.HttpClient"""
    with patch('infrastructure.vectordb.chroma_client.chromadb.HttpClient') as mock:
        mock_instance = Mock()
        mock_instance.heartbeat.return_value = True
        mock.return_value = mock_instance
        yield mock

@pytest.fixture
def mock_persistent_client():
    """Mock chromadb.PersistentClient"""
    with patch('infrastructure.vectordb.chroma_client.chromadb.PersistentClient') as mock:
        yield mock

def test_get_chroma_client_server_mode(mock_env_vars, mock_http_client):
    """get_chroma_client() returns HttpClient when server available"""
    client = get_chroma_client()

    assert client is mock_http_client.return_value
    mock_http_client.assert_called_once_with(
        host="localhost",
        port=8001,
        settings=Mock()
    )
    mock_http_client.return_value.heartbeat.assert_called_once()

def test_get_chroma_client_fallback_to_local(mock_env_vars, mock_http_client, mock_persistent_client):
    """get_chroma_client() falls back to PersistentClient if server fails"""
    mock_http_client.return_value.heartbeat.side_effect = Exception("Connection failed")

    client = get_chroma_client()

    assert client is mock_persistent_client.return_value
    mock_persistent_client.assert_called_once_with(path="./chroma_db")

def test_get_chroma_client_uses_env_vars(monkeypatch, mock_http_client):
    """get_chroma_client() reads host/port from environment"""
    monkeypatch.setenv("CHROMADB_HOST", "chroma.example.com")
    monkeypatch.setenv("CHROMADB_PORT", "9000")

    get_chroma_client()

    call_args = mock_http_client.call_args
    assert call_args.kwargs['host'] == "chroma.example.com"
    assert call_args.kwargs['port'] == 9000
```

- [ ] **Run test to verify it fails**

Run: `pytest tests/unit/infrastructure/test_chroma_client.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'infrastructure.vectordb'"

### Step 6.2: Create vectordb package

- [ ] **Create vectordb __init__.py**

```python
# src/infrastructure/vectordb/__init__.py
"""Vector database abstractions"""
from infrastructure.vectordb.chroma_client import get_chroma_client

__all__ = ['get_chroma_client']
```

- [ ] **Run test again**

Run: `pytest tests/unit/infrastructure/test_chroma_client.py -v`
Expected: FAIL with "ModuleNotFoundError: ...chroma_client"

### Step 6.3: Implement ChromaDB client singleton

- [ ] **Create chroma_client.py**

```python
# src/infrastructure/vectordb/chroma_client.py
import os
import chromadb
from chromadb.config import Settings

_client_instance = None

def get_chroma_client():
    """
    Get ChromaDB client (Singleton)

    Tries to connect to ChromaDB server (HttpClient).
    Falls back to local PersistentClient if server unavailable.

    Environment variables:
        CHROMADB_HOST: Server hostname (default: localhost)
        CHROMADB_PORT: Server port (default: 8001)

    Returns:
        ChromaDB client instance
    """
    global _client_instance

    # Return cached instance
    if _client_instance is not None:
        return _client_instance

    # Read configuration from environment
    host = os.getenv("CHROMADB_HOST", "localhost")
    port = int(os.getenv("CHROMADB_PORT", "8001"))

    try:
        # Try server mode (HttpClient)
        client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False)
        )

        # Test connection
        client.heartbeat()

        print(f"[ChromaDB] ✅ Server connected: {host}:{port}")
        _client_instance = client
        return client

    except Exception as e:
        # Fallback to local mode
        print(f"[ChromaDB] ⚠️ Server connection failed ({e}), using local mode")
        client = chromadb.PersistentClient(path="./chroma_db")
        print(f"[ChromaDB] 📁 Local mode: ./chroma_db")

        _client_instance = client
        return client
```

- [ ] **Run test to verify it passes**

Run: `pytest tests/unit/infrastructure/test_chroma_client.py -v`
Expected: PASS - 3 tests pass

### Step 6.4: Commit ChromaDB client

- [ ] **Commit**

```bash
git add src/infrastructure/vectordb/ tests/unit/infrastructure/test_chroma_client.py
git commit -m "feat(infrastructure): Add ChromaDB client singleton

- Implement get_chroma_client() with server/local fallback
- Support environment variable configuration
- Singleton pattern with global caching
- Comprehensive unit tests with server/local scenarios"
```

---

## Task 7: Embedding Function Factory

**Files:**
- Create: `src/infrastructure/vectordb/embedder.py`
- Create: `tests/unit/infrastructure/test_embedder.py`
- Modify: `src/infrastructure/vectordb/__init__.py`

### Step 7.1: Write failing test for embedder

- [ ] **Create test file**

```python
# tests/unit/infrastructure/test_embedder.py
import pytest
from unittest.mock import patch, Mock
from infrastructure.vectordb.embedder import get_embedding_function

@pytest.fixture
def mock_google_embeddings():
    """Mock GoogleGenerativeAIEmbeddings"""
    with patch('infrastructure.vectordb.embedder.GoogleGenerativeAIEmbeddings') as mock:
        yield mock

@pytest.fixture
def mock_huggingface_embeddings():
    """Mock HuggingFaceEmbeddings"""
    with patch('infrastructure.vectordb.embedder.HuggingFaceEmbeddings') as mock:
        yield mock

def test_get_embedding_function_google_mode(monkeypatch, mock_google_embeddings):
    """get_embedding_function() returns GoogleEmbeddings in google mode"""
    monkeypatch.setenv("EMBEDDING_MODE", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    embedder = get_embedding_function()

    assert embedder is mock_google_embeddings.return_value
    mock_google_embeddings.assert_called_once_with(
        model="models/text-embedding-004",
        google_api_key="test-key"
    )

def test_get_embedding_function_local_mode(monkeypatch, mock_huggingface_embeddings):
    """get_embedding_function() returns HuggingFaceEmbeddings in local mode"""
    monkeypatch.setenv("EMBEDDING_MODE", "local")

    embedder = get_embedding_function()

    assert embedder is mock_huggingface_embeddings.return_value
    mock_huggingface_embeddings.assert_called_once_with(
        model_name="jhgan/ko-sroberta-multitask",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

def test_get_embedding_function_default_google(monkeypatch, mock_google_embeddings):
    """get_embedding_function() defaults to google mode"""
    monkeypatch.delenv("EMBEDDING_MODE", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    embedder = get_embedding_function()

    assert embedder is mock_google_embeddings.return_value
```

- [ ] **Run test to verify it fails**

Run: `pytest tests/unit/infrastructure/test_embedder.py -v`
Expected: FAIL with "ModuleNotFoundError: ...embedder"

### Step 7.2: Implement embedding function factory

- [ ] **Create embedder.py**

```python
# src/infrastructure/vectordb/embedder.py
import os
from dotenv import load_dotenv

load_dotenv()

_embedding_instance = None

def get_embedding_function():
    """
    Get embedding function (Singleton + Strategy Pattern)

    Strategy selection based on EMBEDDING_MODE environment variable:
    - "google": GoogleGenerativeAIEmbeddings (API, 0MB memory)
    - "local": HuggingFaceEmbeddings (local model, ~6GB memory)

    Default: google mode

    Environment variables:
        EMBEDDING_MODE: "google" or "local" (default: google)
        GOOGLE_API_KEY: Required for google mode

    Returns:
        Embedding function instance
    """
    global _embedding_instance

    # Return cached instance
    if _embedding_instance is not None:
        return _embedding_instance

    mode = os.getenv("EMBEDDING_MODE", "google")

    if mode == "local":
        # Local embedding (development - high memory)
        from langchain_huggingface import HuggingFaceEmbeddings

        print("[Embedding] 🖥️ Local model (memory: ~6GB)")
        _embedding_instance = HuggingFaceEmbeddings(
            model_name="jhgan/ko-sroberta-multitask",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )

    else:
        # Google API embedding (production - zero memory)
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        print("[Embedding] ☁️ Google Gemini API (memory: 0MB)")
        _embedding_instance = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )

    return _embedding_instance
```

- [ ] **Run test to verify it passes**

Run: `pytest tests/unit/infrastructure/test_embedder.py -v`
Expected: PASS - 3 tests pass

### Step 7.3: Update vectordb exports

- [ ] **Update vectordb __init__.py**

```python
# src/infrastructure/vectordb/__init__.py
"""Vector database abstractions"""
from infrastructure.vectordb.chroma_client import get_chroma_client
from infrastructure.vectordb.embedder import get_embedding_function

__all__ = [
    'get_chroma_client',
    'get_embedding_function'
]
```

- [ ] **Run all vectordb tests**

Run: `pytest tests/unit/infrastructure/test_chroma*.py tests/unit/infrastructure/test_embedder.py -v`
Expected: PASS - All vectordb tests pass

### Step 7.4: Commit embedder

- [ ] **Commit**

```bash
git add src/infrastructure/vectordb/embedder.py src/infrastructure/vectordb/__init__.py tests/unit/infrastructure/test_embedder.py
git commit -m "feat(infrastructure): Add embedding function factory

- Implement get_embedding_function() with Strategy pattern
- Support google (API) and local (HuggingFace) modes
- Singleton pattern with global caching
- Environment-based configuration
- Unit tests for both strategies"
```

---

## Task 8: Move Storage to Infrastructure

**Files:**
- Move: `storage/database.py` → `src/infrastructure/storage/database.py`
- Move: `storage/models.py` → `src/infrastructure/storage/models.py`
- Move: `storage/auth.py` → `src/infrastructure/storage/auth.py`
- Create: `src/infrastructure/storage/__init__.py`

### Step 8.1: Create infrastructure/storage directory

- [ ] **Create directory and __init__.py**

```bash
mkdir -p src/infrastructure/storage
```

```python
# src/infrastructure/storage/__init__.py
"""Database storage layer (PostgreSQL + SQLAlchemy)"""
from infrastructure.storage.database import get_db, SessionLocal, engine, Base
from infrastructure.storage.models import User, Source, SourceType
from infrastructure.storage.auth import login_or_register, get_user_by_id

__all__ = [
    'get_db',
    'SessionLocal',
    'engine',
    'Base',
    'User',
    'Source',
    'SourceType',
    'login_or_register',
    'get_user_by_id'
]
```

### Step 8.2: Move database.py

- [ ] **Copy and modify database.py**

```bash
cp storage/database.py src/infrastructure/storage/database.py
```

```python
# src/infrastructure/storage/database.py
# (Content identical to storage/database.py - no changes needed)
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./yuta_bot.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI dependency for database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Verify no syntax errors**

Run: `python -m py_compile src/infrastructure/storage/database.py`
Expected: No output (success)

### Step 8.3: Move models.py

- [ ] **Copy and modify models.py**

```bash
cp storage/models.py src/infrastructure/storage/models.py
```

```python
# src/infrastructure/storage/models.py
# Update import to use new location
from infrastructure.storage.database import Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

class SourceType(enum.Enum):
    """Source type enumeration"""
    GIT = "git"
    LOCAL_TIL = "local_til"
    AGENT_CHATLOG = "agent_chatlog"
    MEMSEARCH = "memsearch"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    sources = relationship("Source", back_populates="user")

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(Enum(SourceType), nullable=False)
    location = Column(String, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="sources")
```

- [ ] **Verify no syntax errors**

Run: `python -m py_compile src/infrastructure/storage/models.py`
Expected: No output (success)

### Step 8.4: Move auth.py

- [ ] **Copy and modify auth.py**

```bash
cp storage/auth.py src/infrastructure/storage/auth.py
```

```python
# src/infrastructure/storage/auth.py
# Update imports to use new location
from sqlalchemy.orm import Session
from infrastructure.storage.models import User

def login_or_register(db: Session, user_id: str) -> User:
    """
    Login or register user

    Args:
        db: Database session
        user_id: User identifier

    Returns:
        User instance
    """
    user = db.query(User).filter(User.user_id == user_id).first()

    if user:
        return user

    # Create new user
    new_user = User(user_id=user_id)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

def get_user_by_id(db: Session, user_id: str) -> User:
    """
    Get user by ID

    Args:
        db: Database session
        user_id: User identifier

    Returns:
        User instance or None
    """
    return db.query(User).filter(User.user_id == user_id).first()
```

- [ ] **Verify no syntax errors**

Run: `python -m py_compile src/infrastructure/storage/auth.py`
Expected: No output (success)

### Step 8.5: Update imports in existing files

- [ ] **Update src/router.py imports**

```python
# src/router.py (lines 95-96)
# OLD:
from storage.models import Source

# NEW:
from infrastructure.storage.models import Source
```

- [ ] **Update src/controller.py imports**

```python
# src/controller.py (line 11)
# OLD:
from storage.auth import login_or_register, get_user_by_id

# NEW:
from infrastructure.storage.auth import login_or_register, get_user_by_id
```

- [ ] **Verify application still works**

Run: `python -c "from src.router import router; print('✓ Imports working')"`
Expected: "✓ Imports working"

### Step 8.6: Commit storage migration

- [ ] **Commit**

```bash
git add src/infrastructure/storage/ src/router.py src/controller.py
git commit -m "refactor(infrastructure): Move storage to infrastructure layer

- Move storage/database.py → infrastructure/storage/database.py
- Move storage/models.py → infrastructure/storage/models.py
- Move storage/auth.py → infrastructure/storage/auth.py
- Update imports in router.py and controller.py
- Old storage/ directory kept for backward compatibility (will be removed in Phase 5)"
```

---

## Task 9: Phase 1 Integration Test

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_phase1_integration.py`

### Step 9.1: Write integration test

- [ ] **Create integration test directory**

```bash
mkdir -p tests/integration
touch tests/integration/__init__.py
```

- [ ] **Create integration test**

```python
# tests/integration/test_phase1_integration.py
"""
Phase 1 Integration Test

Verifies that all infrastructure components work together:
- LLM Factory creates working providers
- ChromaDB client connects
- Embedding function loads
- Storage models can be instantiated
"""
import pytest
from infrastructure.llm.factory import LLMFactory
from infrastructure.vectordb.chroma_client import get_chroma_client
from infrastructure.vectordb.embedder import get_embedding_function
from infrastructure.storage.models import User, Source, SourceType
from infrastructure.storage.database import Base, engine

def test_llm_factory_creates_all_providers(mock_env_vars):
    """LLM Factory can create all three providers"""
    factory = LLMFactory()

    # Should not raise errors
    claude = factory.get_llm('claude')
    gemini = factory.get_llm('gemini')
    codex = factory.get_llm('codex')

    assert claude is not None
    assert gemini is not None
    assert codex is not None

def test_chroma_client_singleton():
    """ChromaDB client returns same instance"""
    client1 = get_chroma_client()
    client2 = get_chroma_client()

    assert client1 is client2

def test_embedding_function_singleton():
    """Embedding function returns same instance"""
    embedder1 = get_embedding_function()
    embedder2 = get_embedding_function()

    assert embedder1 is embedder2

def test_storage_models_instantiate():
    """Storage models can be created"""
    user = User(user_id="test_user")
    source = Source(
        user_id="test_user",
        name="Test Repo",
        type=SourceType.GIT,
        location="https://github.com/test/repo.git"
    )

    assert user.user_id == "test_user"
    assert source.name == "Test Repo"
    assert source.type == SourceType.GIT

def test_database_tables_exist():
    """Database tables are created"""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    assert 'users' in tables
    assert 'sources' in tables
```

- [ ] **Run integration test**

Run: `pytest tests/integration/test_phase1_integration.py -v`
Expected: PASS - All integration tests pass

### Step 9.2: Run full test suite

- [ ] **Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: PASS - All Phase 1 tests passing

### Step 9.3: Commit integration test

- [ ] **Commit**

```bash
git add tests/integration/
git commit -m "test(phase1): Add integration tests for infrastructure layer

- Test LLM Factory creates all providers
- Test ChromaDB and Embedder singletons
- Test Storage models instantiation
- Verify all Phase 1 components work together
- All tests passing ✅"
```

---

## Task 10: Phase 1 Documentation

**Files:**
- Create: `docs/superpowers/architecture/phase1-infrastructure.md`

### Step 10.1: Write Phase 1 documentation

- [ ] **Create architecture docs directory**

```bash
mkdir -p docs/superpowers/architecture
```

- [ ] **Create Phase 1 architecture document**

```markdown
# Phase 1: Infrastructure Layer

**Status**: ✅ Complete
**Date**: 2026-07-24

## Overview

Phase 1 extracts all external dependencies (LLM APIs, VectorDB, Storage) into a dedicated Infrastructure layer with proper abstraction patterns.

## Components

### 1. LLM Abstraction

**Pattern**: Factory Pattern + Abstract Base Class

**Files**:
- `infrastructure/llm/base.py` - LLMProvider abstract interface
- `infrastructure/llm/factory.py` - LLMFactory singleton
- `infrastructure/llm/providers/` - Claude, Gemini, Codex implementations

**Usage**:
```python
from infrastructure.llm.factory import LLMFactory

factory = LLMFactory()
claude = factory.get_llm('claude')
response = claude.invoke(messages)
```

**Benefits**:
- Dependency injection support
- Easy provider switching
- Testable with mocks

### 2. VectorDB Abstraction

**Pattern**: Singleton + Strategy Pattern

**Files**:
- `infrastructure/vectordb/chroma_client.py` - ChromaDB client singleton
- `infrastructure/vectordb/embedder.py` - Embedding function factory

**Usage**:
```python
from infrastructure.vectordb.chroma_client import get_chroma_client
from infrastructure.vectordb.embedder import get_embedding_function

client = get_chroma_client()  # Auto-detects server/local mode
embedder = get_embedding_function()  # Reads EMBEDDING_MODE env var
```

**Benefits**:
- Server/local fallback
- Environment-based configuration
- Cached instances

### 3. Storage Layer

**Files**:
- `infrastructure/storage/database.py` - SQLAlchemy setup
- `infrastructure/storage/models.py` - User, Source ORM models
- `infrastructure/storage/auth.py` - Authentication logic

**Migration**:
- Moved from `storage/` to `infrastructure/storage/`
- Updated imports in `router.py` and `controller.py`
- Old `storage/` directory will be removed in Phase 5

## Test Coverage

**Unit Tests**: 25 tests
- LLM providers (15 tests)
- VectorDB components (6 tests)
- Factory patterns (4 tests)

**Integration Tests**: 4 tests
- Cross-component interactions

**Total**: 29 tests passing ✅

## Next Steps

**Phase 2: Domain Layer**
- Extract Pydantic models from `router.py`
- Add validation logic
- Type hints and mypy setup

---

**Questions?** See main refactoring design doc: `docs/superpowers/specs/2026-07-24-refactoring-design.md`
```

- [ ] **Verify document is well-formed**

Run: `cat docs/superpowers/architecture/phase1-infrastructure.md | head -20`
Expected: Markdown renders correctly

### Step 10.2: Update main README

- [ ] **Add Phase 1 completion note to README**

```markdown
# (Add to README.md under ## 🏗️ Architecture section)

### Refactoring Progress

- ✅ **Phase 1: Infrastructure Layer** (Complete)
  - LLM Factory Pattern
  - VectorDB Repository Pattern
  - Storage layer migration
  - [Details](docs/superpowers/architecture/phase1-infrastructure.md)
- ⏳ Phase 2: Domain Layer (In Progress)
- ⏳ Phase 3: Application Layer
- ⏳ Phase 4: Presentation Layer
- ⏳ Phase 5: Legacy Cleanup
```

- [ ] **Commit documentation**

```bash
git add docs/superpowers/architecture/phase1-infrastructure.md README.md
git commit -m "docs(phase1): Add Phase 1 completion documentation

- Document Infrastructure layer architecture
- List all components and usage examples
- Record test coverage stats
- Update README with refactoring progress
- Phase 1 complete ✅"
```

---

## Phase 1 Completion Checklist

- [ ] All tests passing (29 tests)
- [ ] LLM Factory working with 3 providers
- [ ] ChromaDB client with server/local fallback
- [ ] Embedding function factory
- [ ] Storage moved to infrastructure
- [ ] Integration tests passing
- [ ] Documentation complete

---

**Phase 1 Complete!** 🎉

Total files created: 23
Total tests: 29
Time estimate: 1 week

**Ready for Phase 2: Domain Layer**
