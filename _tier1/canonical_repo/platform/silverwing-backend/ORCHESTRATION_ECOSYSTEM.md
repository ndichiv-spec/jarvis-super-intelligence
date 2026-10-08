# Silverwing Orchestration Ecosystem Analysis

This document analyzes the orchestration frameworks integrated as adapters in the Silverwing Intelligence Fabric.  Silverwing owns the mission lifecycle; external frameworks are **adapters**, not authority.

---

## Framework Adapter Overview

| Adapter | Status | License | Maintenance | Dependencies | Security | Performance | Usefulness |
|---------|--------|---------|-------------|--------------|----------|-------------|------------|
| **Native** | ✅ Production | MIT | — | none | ✅ Secure | ✅ Fast | ✅ Primary path |
| **LangGraph** | ✅ Adapter | MIT | Active | langgraph, langchain-core | ✅ Good | ⚠️ Overhead | ✅ For complex workflows |
| **LangChain** | ✅ Adapter | MIT | Active | langchain-core | ✅ Good | ⚠️ Overhead | ✅ For tool chaining |
| **CrewAI** | ✅ Adapter | MIT | Moderate | crewai | ⚠️ Moderate | ⚠️ Overhead | ✅ For role-playing agents |
| **AutoGen** | ✅ Adapter | MIT | Moderate | pyautogen | ⚠️ Moderate | ⚠️ Overhead | ✅ For conversation agents |
| **PydanticAI** | ✅ Adapter | MIT | Active | pydantic-ai | ✅ Good | ✅ Fast | ✅ For type safety |
| **LlamaIndex** | ✅ Adapter | Apache-2.0 | Active | llama-index | ✅ Good | ⚠️ Overhead | ✅ For RAG |

---

## Native Execution (`NativeExecutionAdapter`)

**Status: PRIMARY PATH**

Silverwing's built-in execution adapter is the default and recommended path.  It executes tasks by:

1. Sequencing through the task's steps (from TaskPlanner)
2. Using the Silverwing Tool Runtime for tool invocations
3. Using the Model Router (from the Gateway) for model selection

### When to Use

- Default for all tasks unless a specific framework adds value
- Low-latency, low-dependency execution
- Full control over the execution pipeline
- Best performance for the majority of use cases

### Strength

- No external dependencies
- Fast startup and execution
- Full visibility into each step

---

## LangGraph Adapter

**Status: ADAPTER**

### Capability

Runs tasks through a LangGraph state machine.  Ideal for:

- Complex branching workflows
- Stateful multi-agent conversations
- Human-in-the-loop review points
- Memory persistence via graph checkpoints

### Integration Strategy

The adapter builds a minimal state graph on-the-fly:

```
Task → StateGraph → execute_step → tool_invoke → update_state → StopEvent
```

Each graph node handles one step; the graph is compiled and executed asynchronously.

### When to Use

- When you need **intermediate state inspection**
- When you need **human review points** in the pipeline
- When you need **long-running, stateful workflows**

### Example

```python
from intelligence_fabric.adapters.langgraph import LangGraphAdapter
adapter = LangGraphAdapter()
result = await adapter.execute(agent, task, steps, context)
```

---

## LangChain Adapter

**Status: ADAPTER**

### Capability

Runs tasks through LangChain's Runnable expression language.  Ideal for:

- Tool chaining with LangChain's built-in tools
- Prompt templating and structured output
- Memory-backed conversations (ConversationBufferMemory)

### Integration Strategy

The adapter wraps steps in a `RunnableLambda` chain:

```
RunnableLambda(step1) → RunnableLambda(step2) → ... → RunnablePassthrough
```

Each step processes input and returns output for the next step.

### When to Use

- When you need **pre-built LangChain tools** (SQL, API, etc.)
- When you need **prompt templates** from LangChain Hub
- When you want **LangChain memory integration**

### Limitation

Silverwind still handles model calls via its own Router; the LangChain adapter does **not** delegate model selection.

---

## CrewAI Adapter

**Status: ADAPTER**

### Capability

Runs tasks through CrewAI's crew/agent/task model.  Ideal for:

- Role-playing agent teams with personalities
- Automatic task delegation between agents
- Back-and-forth multi-agent conversations

### Integration Strategy

1. Create `Agent` objects from Fabric `AgentSpec`
2. Create `Task` objects from `TaskSpec`
3. Build a `Crew` with the agents and tasks
4. Call `crew.kickoff_async()` to execute

### When to Use

- When you want **personality-driven agents**
- When you need **automatic delegation** between researcher/analyst/etc.
- When you want **team brainstorming** flows

### Example

```python
from intelligence_fabric.adapters.crewai import CrewAIAdapter
adapter = CrewAIAdapter()
result = await adapter.execute_mission(context, tasks, steps_map)
```

---

## AutoGen Adapter

**Status: ADAPTER**

### Capability

Runs tasks through Microsoft AutoGen's conversable-agent model.  Ideal for:

- Multi-agent dialogue systems
- Code-execution via AutoGen's built-in executors
- Tool calling with AutoGen's `tool` decorator

### Integration Strategy

1. Create `AssistantAgent` objects from Fabric agent specs
2. Create a `UserProxyAgent` to initiate and receive messages
3. Initiate chat with `initiate_chat()` or `initiate_chats()`

### When to Use

- When you need **iterative agent conversation**
- When you want **AutoGen's code executor** for complex computations
- When you want **tool calling** with AutoGen's message flow

---

## PydanticAI Adapter

**Status: ADAPTER**

### Capability

Runs tasks through PydanticAI's type-safe agent framework.  Ideal for:

- Structured JSON output with Pydantic models
- Dependency injection of tools
- Type-checked agent pipelines

### Integration Strategy

1. Create a `PydanticAI` model (OpenAI, Gemini, Ollama, etc.)
2. Create an `Agent` with a system prompt from `AgentSpec`
3. Run the agent with the task description

### When to Use

- When you need **strict JSON output**
- When you want **dependency injection** of services
- When you want **type safety** throughout the pipeline

### Example

```python
from intelligence_fabric.adapters.pydanticai import PydanticAIAdapter
adapter = PydanticAIAdapter()
result = await adapter.execute(agent, task, steps, context)
```

---

## LlamaIndex Adapter

**Status: ADAPTER**

### Capability

Runs tasks through LlamaIndex's workflow engine.  Ideal for:

- RAG pipelines over knowledge bases
- Knowledge graph traversal and querying
- Document indexing and retrieval

### Integration Strategy

1. Build a `StateGraph` workflow with LlamaIndex
2. Add nodes for each step
3. Use LlamaIndex's retrievers for knowledge lookup
4. Execute via `graph.ainvoke()`

### When to Use

- When you need **RAG over private documents**
- When you want **LlamaIndex's knowledge graph** features
- When you need **document parsing and indexing**

---

## Adapter Selection Matrix

| Use Case | Recommended Adapter |
|----------|---------------------|
| Default execution | Native |
| Complex branching workflow | LangGraph |
| Tool chaining with templates | LangChain |
| Role-playing agents | CrewAI |
| Multi-agent dialogue | AutoGen |
| Structured JSON output | PydanticAI |
| RAG over documents | LlamaIndex |
| Human review points | LangGraph |
| Conversation history | AutoGen or LangChain with memory |
| Code generation | Native (or PydanticAI for type safety) |

---

## Adapter Limitations

### Common Limitations

1. **Not all models supported**: Each adapter has its own set of supported LLMs
2. **Runtime overhead**: All adapters add some latency; measure for your use case
3. **State management**: External frameworks handle state differently; align with Fabric expectations
4. **Security surface**: More dependencies = larger attack surface

### Framework-Specific Limitations

| Framework | Limitation |
|-----------|------------|
| LangGraph | Requires `langgraph` package; complex for simple tasks |
| LangChain | Deprecated patterns in older code; fast changes |
| CrewAI | Heavier memory footprint; slower startup |
| AutoGen | Microsoft dependency; licensing questions for commercial use |
| PydanticAI | Younger ecosystem; fewer built-in tools |
| LlamaIndex | Focused on RAG; not general purpose orchestration |

---

## Future Integration Plans

### Short-term (Phase 2-3)

- ✅ LangGraph adapter (basic workflow execution)
- ✅ LangChain adapter (tool chaining)
- ✅ Native adapter (primary path)

### Medium-term (Phase 4-5)

- 🔄 CrewAI adapter (role-playing agents)
- 🔄 AutoGen adapter (multi-agent dialogue)
- 🔄 PydanticAI adapter (type-safe pipelines)

### Long-term (Phase 6+)

- Add adapter for **LangFlow** visual workflows
- Add adapter for **Babelfish** multi-agent system
- Consider **deterministic execution** via **Wasmtime** for sandboxed tool execution

---

## Comparison with External Framework Ownership

### What Silverwing Does NOT Do

1. **Does not import external frameworks into core** (they're in `adapters/`)
2. **Does not let external frameworks own the mission lifecycle** (Fabric does)
3. **Does not merge external state into Fabric state** (Adapter returns results)
4. **Does not auto-switch adapters** (Opt-in via `IntelligenceRequest.framework`)

### What External Framework Adapters DO

1. Translate `TaskSpec` → framework-native task
2. Execute via framework's runtime
3. Return results in Fabric-compatible format
4. Report errors as `status="failed"` with `error` message

---

## Security Considerations

All adapters are designed to be **sandboxed**:

1. **Network**: Adapters use ShieldedConnections where configured
2. **File system**: Only approved tools can access filesystem
3. **Code execution**: Python/shell tools run in a restricted sandbox
4. **API keys**: Imported from environment; never hardcoded

---

## Performance Characteristics

| Adapter | Startup | Throughput | Memory | Typical Latency |
|---------|---------|------------|--------|-----------------|
| Native | <1ms | High | Low | 100-500ms/task |
| LangGraph | ~100ms | Medium | Medium | 200-800ms/task |
| LangChain | ~50ms | Medium | Medium | 150-600ms/task |
| CrewAI | ~500ms | Low | High | 500-2000ms/task |
| AutoGen | ~200ms | Medium | Medium | 200-1000ms/task |
| PydanticAI | ~50ms | High | Low | 100-400ms/task |
| LlamaIndex | ~100ms | Medium | Medium | 150-500ms/task |

---

## Conclusion

The Silverwing Intelligence Fabric provides **multiple orchestration paths**:

- **Native** for speed and control (default)
- **LangGraph** for complex workflows
- **LangChain** for tool chaining
- **CrewAI/AutoGen** for agent teams
- **PydanticAI** for type safety
- **LlamaIndex** for RAG

Adapters are **opt-in, composable, and replaceable**.  Silverwing remains the **authoritative owner** of the mission lifecycle.