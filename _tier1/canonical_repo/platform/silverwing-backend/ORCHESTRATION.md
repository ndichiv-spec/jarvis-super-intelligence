# Orchestration Framework Integration Guide

This document maps Silverwing's model-provider string format
(`<provider>:<model-id>`) onto the major Python orchestration frameworks:
**Pydantic-AI**, **LangChain**, **LangGraph**, **LlamaIndex**, **CrewAI**,
and **AutoGen**.

Silverwing's canonical provider strings are defined in
`backend/model_provider.py` and the full model catalogue lives in
`backend/model_catalog.py`. All routing goes through a single
`ModelManager` singleton, so the same string works across every entry point:
the `/api/models/chat` HTTP endpoint, the `model_provider` agent tool, the
Training Advisor, and any external orchestrator.

---

## 1. Provider String Format

Every model is identified by:

```
<provider>:<model-id>
```

Registered providers:

| Provider (Silverwing) | Aliases | SDK / API |
|-----------------------|---------|-----------|
| `openai`   | `openai-compatible` | OpenAI SDK |
| `anthropic`| `claude` | Anthropic SDK |
| `google`  | `gemini` | `google.genai` SDK |
| `groq`    | `groqcloud` | Groq SDK |
| `deepseek`| `deepseekai` | OpenAI SDK (custom base_url) |
| `ollama`  | — | Ollama SDK |
| `llamacpp`| `llama_cpp`, `llamacpp_server` | OpenAI SDK (custom base_url) |
| `bedrock` | `aws_bedrock` | `boto3` |
| `vertex`  | `vertexai`, `vertex_ai` | `google-cloud-aiplatform` |
| `local`   | — | deterministic echo (no SDK) |

**Example references:**

```
openai:gpt-5.6-sol
anthropic:claude-opus-5
google:gemini-2.5-pro
groq:llama-3.3-70b-versatile
deepseek:deepseek-v4-pro
ollama:llama3.3:70b
llamacpp:Qwen3-32B-Q4_K_M.gguf
bedrock:anthropic.claude-opus-5-v1:0
vertex:publishers/google/models/gemini-2.5-pro
local-rule
```

When a provider is unavailable (no key/SDK/server configured), Silverwing
falls back to `local-rule` automatically.

---

## 2. Pydantic-AI

Pydantic-AI natively understands the `provider:model` syntax via its
`Agent(model=...)` constructor. The model string is passed directly:

```python
from pydantic_ai import Agent

# Direct provider reference
agent = Agent('openai:gpt-5.6-sol')

# The manager resolves availability at runtime
from model_provider import ModelManager
mgr = ModelManager()
provider, model = mgr.provider_for('google:gemini-2.5-pro')
print(provider.name, model)  # → google, gemini-2.5-pro (if available) or local-rule

# Fallback: if the key isn't set, Pydantic-AI will error; instead use the
# manager's resolution:
agent = Agent(mgr.provider_for('anthropic:claude-opus-5')[1])  # safe
```

Pydantic-AI's `models.OpenAIModel`, `models.AnthropicModel`, etc. can also
be constructed directly with the appropriate model ID and API key.

---

## 3. LangChain / LangGraph

LangChain uses `ChatOpenAI`, `ChatAnthropic`, `ChatGoogleGenerativeAI`, etc.
The provider string maps to a specific constructor:

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# Parse the provider string:
ref = "openai:gpt-5.6-sol"
provider, model_id = ref.split(":", 1)

if provider == "openai":
    llm = ChatOpenAI(model=model_id)
elif provider == "anthropic":
    llm = ChatAnthropic(model=model_id)
elif provider == "google":
    llm = ChatGoogleGenerativeAI(model=model_id)
elif provider == "groq":
    llm = ChatGroq(model=model_id)
```

**LangGraph** uses the same `ChatModel` objects in a stateful graph:

```python
from langgraph.graph import StateGraph

graph = StateGraph(...)
graph.add_node("agent", agent_node(llm))  # llm from above
```

---

## 4. LlamaIndex

LlamaIndex uses `LLM` subclasses with a `model` parameter:

```python
from llama_index.llms.openai import OpenAI
from llama_index.llms.anthropic import Anthropic
from llama_index.llms.gemini import Gemini
from llama_index.llms.groq import Groq

llm_map = {
    "openai": OpenAI,
    "anthropic": Anthropic,
    "google": Gemini,
    "groq": Groq,
}

provider, model_id = "google:gemini-2.5-pro".split(":", 1)
llm = llm_map[provider](model=model_id)
```

---

## 5. CrewAI

CrewAI uses `LLM` from `crewai`:

```python
from crewai import LLM

# Same provider:model format
llm = LLM(model="openai/gpt-5.6-sol")  # CrewAI uses slash separator
# Or use the manager's resolution:
from model_provider import ModelManager
mgr = ModelManager()
provider, model = mgr.provider_for("anthropic:claude-opus-5")
llm = LLM(model=f"{provider}/{model}")
```

Note: CrewAI expects `provider/model` (slash) whereas Silverwing uses
`provider:model` (colon). Convert between them with a simple `.replace(":", "/", 1)`.

---

## 6. AutoGen

AutoGen uses `config_list` with `model` and `api_key`:

```python
from autogen import GroupChat, GroupChatManager

config_list = [
    {
        "model": "gpt-5.6-sol",
        "api_key": os.environ["OPENAI_API_KEY"],
        "model_provider": "openai",  # or use the base_url for custom providers
    }
]
```

For DeepSeek (OpenAI-compatible endpoint):
```python
config_list = [
    {
        "model": "deepseek-chat",
        "api_key": os.environ["DEEPSEEK_API_KEY"],
        "base_url": "https://api.deepseek.com/v1",
        "model_provider": "openai",
    }
]
```

---

## 7. Silverwing's Own Orchestrators

Silverwing's comprehensive backend
(`silverwing/backend/`) already uses several of these frameworks:

- **`langchain`** is in `requirements.txt` — used for prompt chains and tools.
- **`langchain-openai`** and **`langchain-anthropic`** — LLM bindings.

The `ModelManager` singleton (initialized as `_MODEL_MANAGER` in
`backend/main.py`) provides a single resolution point. Agents and runtimes
should use it rather than constructing SDK clients directly:

```python
from model_provider import ModelManager, ModelRequest

mgr = ModelManager()
# Routes to available provider, falls back to local-rule
resp = await mgr.achat(ModelRequest(
    model="openai:gpt-5.6-sol",
    messages=[{"role": "user", "content": "Hello"}],
    system="You are a helpful assistant.",
))
```

---

## 8. Serving Recommendations

| Use case | Recommended provider | Rationale |
|----------|---------------------|-----------|
| Highest quality, budget no object | `openai:gpt-5.6-sol` or `anthropic:claude-fable-5-1` | Frontier reasoning |
| Best cost/performance | `google:gemini-2.5-flash` or `groq:llama-3.3-70b-versatile` | Price-efficient, fast |
| No internet / privacy | `ollama:llama3.3:70b` or `llamacpp:Qwen3-32B-Q4_K_M` | Fully self-hosted |
| Free tier experimentation | `deepseek:deepseek-v4-pro` | Generous free quota |
| Enterprise / compliance | `bedrock:anthropic.claude-opus-5-v1:0` or `vertex:gemini-2.5-pro` | Cloud IAM + VPC endpoints |
| Open-weights research | `openai:gpt-oss-120b` or `google:gemma-4-27b` | Fully open, self-hostable |
