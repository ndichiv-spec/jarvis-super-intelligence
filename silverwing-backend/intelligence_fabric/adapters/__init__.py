"""Orchestration framework adapters for the Silverwing Intelligence Fabric.

Silverwing owns the mission lifecycle.  External frameworks are adapters.
Each adapter translates between a Silverwing ``TaskSpec`` / ``MissionContext``
and the framework's native representation.
"""

from adapters.base import (
    BaseOrchestrationAdapter,
    NativeExecutionAdapter,
    get_all_adapters,
    get_adapter_info_all,
)
from adapters.langgraph_adapter import LangGraphAdapter
from adapters.langchain_adapter import LangChainAdapter
from adapters.crewai_adapter import CrewAIAdapter
from adapters.autogen_adapter import AutoGenAdapter
from adapters.pydanticai_adapter import PydanticAIAdapter
from adapters.llamaindex_adapter import LlamaIndexAdapter

__all__ = [
    "BaseOrchestrationAdapter",
    "NativeExecutionAdapter",
    "LangGraphAdapter",
    "LangChainAdapter",
    "CrewAIAdapter",
    "AutoGenAdapter",
    "PydanticAIAdapter",
    "LlamaIndexAdapter",
    "get_all_adapters",
    "get_adapter_info_all",
]


def get_adapter(name: str) -> BaseOrchestrationAdapter:
    """Return an adapter instance by name."""

    adapters = {
        "native": NativeExecutionAdapter(),
        "langgraph": LangGraphAdapter(),
        "langchain": LangChainAdapter(),
        "crewai": CrewAIAdapter(),
        "autogen": AutoGenAdapter(),
        "pydanticai": PydanticAIAdapter(),
        "llamaindex": LlamaIndexAdapter(),
    }
    return adapters.get(name, NativeExecutionAdapter())
