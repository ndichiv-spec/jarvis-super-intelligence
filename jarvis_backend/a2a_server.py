"""A2A (Agent2Agent) protocol server for JARVIS.

Exposes JARVIS capabilities as A2A agents.  The A2A protocol (google/A2A,
25,985 stars) is an open standard for agent-to-agent communication using
JSON-RPC 2.0 over HTTP.

This module creates an A2A server that maps incoming agentic requests to the
existing JARVIS Orchestrator, exposing JARVIS's 15 capabilities as A2A tools.

Endpoints (mounted on the existing FastAPI app):
  - ``/a2a``           — JSON-RPC 2.0 endpoint (A2A v1.0 compliant)
  - ``/a2a/rest``      — REST endpoint for message/send
  - ``/.well-known/agent-card.json`` — agent card metadata

The agent card advertises the following skills derived from JARVIS capabilities:
  - ``chat``           — conversational AI
  - ``research``       — autonomous research ingestion & semantic search
  - ``science``        — symbolic & numerical math via SymPy/SciPy
  - ``memory``         — conversation and knowledge graph management
  - ``task``           — task creation and tracking
  - ``voice``          — voice synthesis & recognition
  - ``vision``         — image analysis
  - ``image-generation`` — AI image generation
  - ``browser``        — web browsing & extraction
  - ``github``         — GitHub repository analysis
  - ``postgresql``     — PostgreSQL query execution
  - ``bio-learner``    — spaced-repetition learning
  - ``brain``          — central brain model coordination
  - ``knowledge``      — knowledge graph management
  - ``tech-tracker``   — technology trend tracking

Graceful degradation: if ``a2a-sdk`` is not installed, the module exports
``a2a_available()`` returning ``False`` and all entry-points raise
``ModuleNotFoundError``.  The existing FastAPI app continues to work.

Usage with FastAPI (additive, no new process):

    from jarvis_backend.a2a_server import create_a2a_agent_card, JarvisAgentExecutor

    # In your FastAPI app:
    # from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
    # from a2a.server.routes.rest_routes import create_rest_routes
    # from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
    # from a2a.server.routes.agent_card_routes import create_agent_card_routes
    # from a2a.server.request_handlers.default_request_handler_v2 import DefaultRequestHandlerV2
    # from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
    #
    # executor = JarvisAgentExecutor()
    # handler = DefaultRequestHandlerV2(
    #     agent_executor=executor,
    #     task_store=InMemoryTaskStore(),
    #     agent_card=create_a2a_agent_card(),
    # )
    # jsonrpc_routes = create_jsonrpc_routes(handler, '/a2a')
    # rest_routes = create_rest_routes(handler)
    # agent_card_routes = create_agent_card_routes(create_a2a_agent_card())
    # add_a2a_routes_to_fastapi(app, agent_card_routes=agent_card_routes,
    #     jsonrpc_routes=jsonrpc_routes, rest_routes=rest_routes)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.a2a_server")

# --------------------------------------------------------------------------- #
# Capability → A2A skill mapping
# --------------------------------------------------------------------------- #
# JARVIS exposes 15 capabilities; each maps to an A2A skill with appropriate
# input/output modes.
CAPABILITY_SKILLS: List[Dict[str, Any]] = [
    {
        "id": "chat",
        "name": "JARVIS Chat",
        "description": "Conversational AI backed by LLM gateway with cost tracking.",
        "tags": ["chat", "conversation", "llm"],
        "input_modes": ["text"],
        "output_modes": ["text"],
    },
    {
        "id": "research",
        "name": "Autonomous Research",
        "description": "Ingest RSS feeds, arXiv papers, web URLs, and perform semantic search over the knowledge graph.",
        "tags": ["research", "ingestion", "semantic-search", "arxiv"],
        "input_modes": ["text"],
        "output_modes": ["text", "document"],
    },
    {
        "id": "science",
        "name": "Science Engine",
        "description": "Symbolic and numerical math: solve equations, derivatives, integrals, limits, statistics, hypothesis testing.",
        "tags": ["math", "sympy", "scipy", "science"],
        "input_modes": ["text", "data"],
        "output_modes": ["text", "data"],
    },
    {
        "id": "memory",
        "name": "Memory Manager",
        "description": "Conversation and knowledge graph management with semantic search.",
        "tags": ["memory", "knowledge-graph", "semantic-search"],
        "input_modes": ["text"],
        "output_modes": ["text", "document"],
    },
    {
        "id": "task",
        "name": "Task Manager",
        "description": "Task creation, tracking, and status reporting.",
        "tags": ["tasks", "productivity", "tracking"],
        "input_modes": ["text", "data"],
        "output_modes": ["text", "data"],
    },
    {
        "id": "voice",
        "name": "Voice Interface",
        "description": "Voice synthesis and speech recognition.",
        "tags": ["voice", "audio", "tts", "asr"],
        "input_modes": ["text", "audio"],
        "output_modes": ["text", "audio"],
    },
    {
        "id": "vision",
        "name": "Vision Analysis",
        "description": "Image analysis and understanding.",
        "tags": ["vision", "image-analysis"],
        "input_modes": ["image"],
        "output_modes": ["text", "data"],
    },
    {
        "id": "image-generation",
        "name": "Image Generation",
        "description": "AI-powered image generation from text prompts.",
        "tags": ["image-generation", "ai-art"],
        "input_modes": ["text"],
        "output_modes": ["image"],
    },
    {
        "id": "browser",
        "name": "Web Browser",
        "description": "Web browsing, page extraction, and screenshot capture.",
        "tags": ["browser", "web", "extraction"],
        "input_modes": ["text"],
        "output_modes": ["text", "document"],
    },
    {
        "id": "github",
        "name": "GitHub Analysis",
        "description": "GitHub repository analysis, star counting, and activity monitoring.",
        "tags": ["github", "git", "repository"],
        "input_modes": ["text", "data"],
        "output_modes": ["text", "data"],
    },
    {
        "id": "postgresql",
        "name": "PostgreSQL Query",
        "description": "Read-only PostgreSQL query execution with result summarization.",
        "tags": ["database", "sql", "postgresql"],
        "input_modes": ["text", "data"],
        "output_modes": ["text", "data"],
    },
    {
        "id": "bio-learner",
        "name": "Bio-Learner",
        "description": "Spaced-repetition learning with SM-2 algorithm.",
        "tags": ["learning", "spaced-repetition", "sm-2"],
        "input_modes": ["text"],
        "output_modes": ["text"],
    },
    {
        "id": "brain",
        "name": "Brain Coordinator",
        "description": "Central brain model coordination and context management.",
        "tags": ["brain", "coordination", "context"],
        "input_modes": ["text"],
        "output_modes": ["text"],
    },
    {
        "id": "knowledge",
        "name": "Knowledge Graph",
        "description": "Knowledge graph management: add nodes, search, and explore relationships.",
        "tags": ["knowledge", "graph", "semantic"],
        "input_modes": ["text"],
        "output_modes": ["text", "document"],
    },
    {
        "id": "tech-tracker",
        "name": "Tech Tracker",
        "description": "Technology trend tracking and growth modeling.",
        "tags": ["tech", "trends", "tracking"],
        "input_modes": ["text"],
        "output_modes": ["text", "data"],
    },
]


def a2a_available() -> bool:
    """Check if the A2A SDK is installed."""
    try:
        import a2a  # noqa: F401
        return True
    except ImportError:
        return False


# --------------------------------------------------------------------------- #
# Agent Card creation
# --------------------------------------------------------------------------- #
def create_a2a_agent_card() -> Any:
    """Create an A2A AgentCard for JARVIS.

    Returns:
        AgentCard proto message (or a dict if a2a-sdk is not installed).
    """
    if a2a_available():
        from a2a.types import AgentCard, AgentCapabilities, AgentSkill, AgentProvider, AgentInterface

        skills = []
        for sk in CAPABILITY_SKILLS:
            skills.append(AgentSkill(
                id=sk["id"],
                name=sk["name"],
                description=sk["description"],
                tags=sk["tags"],
                input_modes=sk["input_modes"],
                output_modes=sk["output_modes"],
                examples=[
                    "What can you do?",
                    "How do I use " + sk["id"] + "?",
                ],
            ))

        return AgentCard(
            name="JARVIS AI Assistant",
            description="JARVIS (Just A Rather Intelligent System) — a modular AI platform with "
                        "15 capabilities including research, science, memory, task management, "
                        "voice, vision, and more.",
            version="1.0.0",
            supported_interfaces=[
                AgentInterface(
                    url=os.environ.get("JARVIS_A2A_URL", "http://localhost:8000/a2a"),
                    protocol_binding="JSON-RPC 2.0 over HTTP",
                )
            ],
            capabilities=AgentCapabilities(
                streaming=True,
                push_notifications=False,
                extended_agent_card=False,
            ),
            provider=AgentProvider(
                url=os.environ.get("JARVIS_A2A_URL", "http://localhost:8000/a2a"),
                organization="JARVIS",
            ),
            default_input_modes=["text"],
            default_output_modes=["text", "document"],
            skills=skills,
        )
    else:
        # Return a plain dict when a2a-sdk is not installed
        return {
            "name": "JARVIS AI Assistant",
            "description": "Modular AI platform with 15 capabilities",
            "version": "1.0.0",
            "skills": CAPABILITY_SKILLS,
        }


# --------------------------------------------------------------------------- #
# A2A Agent Executor — routes A2A requests to JARVIS Orchestrator
# --------------------------------------------------------------------------- #
class JarvisAgentExecutor:
    """A2A AgentExecutor that routes requests to the JARVIS Orchestrator.

    This class implements the A2A ``AgentExecutor`` interface.  When a message
    arrives, it:
    1. Parses the user's text to determine which capability to invoke
    2. Routes the request through the existing ``Orchestrator.execute_capability()``
    3. Publishes the response as a completion event on the A2A event queue

    Graceful degradation: if the A2A SDK is not installed, the class still
    exists with compatible method signatures but will raise ImportError on use.
    """

    # Map of skill IDs to JARVIS capability names
    SKILL_TO_CAPABILITY = {
        "chat": "conversation",
        "research": "research_cortex",
        "science": "science.engine",
        "memory": "memory",
        "task": "task",
        "voice": "voice",
        "vision": "vision",
        "image-generation": "image_generation",
        "browser": "browser",
        "github": "github",
        "postgresql": "postgresql",
        "bio-learner": "bio_learner",
        "brain": "brain",
        "knowledge": "knowledge",
        "tech-tracker": "tech_tracker",
    }

    # Expanded keyword sets for detection (checked in priority order)
    SKILL_KEYWORDS = [
        ("research", "research_cortex", ["research", "arxiv", "feed", "ingest", "search arxiv", "rss", "web crawl", "semantic search", "knowledge graph"]),
        ("science", "science.engine", ["science", "solve", "math", "equation", "integral", "derivative", "limit", "sympy", "scipy", "statistic", "hypothesis", "proof"]),
        ("memory", "memory", ["memory", "remember", "forget", "recall", "context"]),
        ("task", "task", ["task", "todo", "create task", "track"]),
        ("voice", "voice", ["voice", "speak", "listen", "audio", "tts", "speech"]),
        ("vision", "vision", ["vision", "image analysis", "see", "describe image", "what is in"]),
        ("image-generation", "image_generation", ["generate image", "image generation", "create image", "draw an image", "draw", "art", "image of a", "image of"]),
        ("browser", "browser", ["browse", "web", "website", "crawl", "extract", "screenshot"]),
        ("github", "github", ["github", "git", "repository", "repo", "star", "commit"]),
        ("postgresql", "postgresql", ["sql", "database", "postgresql", "query", "table", "schema"]),
        ("bio-learner", "bio_learner", ["study", "learn", "spaced", "review", "flashcard", "memorize"]),
        ("brain", "brain", ["brain", "think", "reason", "plan"]),
        ("knowledge", "knowledge", ["knowledge", "concept", "relationship", "node"]),
        ("tech-tracker", "tech_tracker", ["tech", "trend", "tracker", "growth", "adoption"]),
        ("chat", "conversation", ["chat", "hello", "hi", "question", "help", "talk"]),
    ]

    def __init__(self):
        self._orchestrator: Optional[Any] = None
        self._initialized = False

    async def _get_orchestrator(self):
        """Lazy-load the JARVIS Orchestrator."""
        if self._orchestrator is None:
            from jarvis_backend.capability import Orchestrator
            self._orchestrator = Orchestrator()
        return self._orchestrator

    def _detect_skill(self, user_text: str) -> Optional[str]:
        """Detect which JARVIS capability to route to based on user text."""
        text_lower = user_text.lower()

        # Check each skill's keywords in priority order
        for skill_id, _cap_name, keywords in self.SKILL_KEYWORDS:
            for kw in keywords:
                if kw in text_lower:
                    return skill_id

        # Default: conversation/chat
        return "chat"

    async def execute(
        self,
        context: Any,  # RequestContext
        event_queue: Any,  # EventQueue
    ) -> None:
        """Execute the agent — called by the A2A framework."""
        # Extract text from the incoming message
        try:
            user_text = context.get_user_input()
        except Exception:
            user_text = ""

        logger.info("A2A request: %s", user_text[:200])

        # Determine which capability to invoke
        skill_id = self._detect_skill(user_text)
        capability_name = self.SKILL_TO_CAPABILITY.get(skill_id, "conversation")

        # Build a request for the JARVIS orchestrator
        request = {
            "action": skill_id,
            "query": user_text,
            "text": user_text,
        }

        try:
            orchestrator = await self._get_orchestrator()
            result = await orchestrator.execute_capability(
                capability_name, request, None
            )

            # Extract response text
            if hasattr(result, 'data') and isinstance(result.data, dict):
                response_text = result.data.get("response", result.data.get("text", str(result.data)))
            elif hasattr(result, 'data') and result.data:
                response_text = str(result.data)
            elif hasattr(result, 'error') and result.error:
                response_text = f"Error: {result.error}"
            else:
                response_text = "JARVIS processed your request."

            # Build the A2A response message
            from a2a.types import Message, Part, Role, TaskState, TaskStatus, TaskStatusUpdateEvent

            # Publish a status update (working → completed)
            task = context.current_task
            task_id = task.id if task else context.task_id
            context_id = context.context_id

            # Send a completion message
            response_message = Message(
                message_id=f"a2a-resp-{task_id}",
                role=Role.ROLE_AGENT,
                parts=[Part(text=response_text)],
            )
            event_queue.enqueue_event(response_message)

            # Also send a task status update
            if task:
                status_update = TaskStatusUpdateEvent(
                    task_id=task_id,
                    context_id=context_id,
                    status=TaskStatus(
                        state=TaskState.TASK_STATE_COMPLETED,
                        message=Message(
                            message_id=f"a2a-status-{task_id}",
                            role=Role.ROLE_AGENT,
                            parts=[Part(text=response_text)],
                        ),
                    ),
                )
                event_queue.enqueue_event(status_update)

        except Exception as e:
            logger.error("A2A execution error: %s", e, exc_info=True)
            from a2a.types import Message, Part, Role

            error_message = f"JARVIS error: {str(e)}"
            response_message = Message(
                message_id=f"a2a-error-{context.task_id}",
                role=Role.ROLE_AGENT,
                parts=[Part(text=error_message)],
            )
            event_queue.enqueue_event(response_message)

    async def cancel(
        self,
        context: Any,  # RequestContext
        event_queue: Any,  # EventQueue
    ) -> None:
        """Cancel an ongoing A2A task."""
        from a2a.types import TaskState, TaskStatus, TaskStatusUpdateEvent, Message, Part, Role

        task = context.current_task
        task_id = task.id if task else context.task_id
        context_id = context.context_id

        cancel_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.TASK_STATE_CANCELED,
                message=Message(
                    message_id=f"a2a-cancel-{task_id}",
                    role=Role.ROLE_AGENT,
                    parts=[Part(text="Task cancelled by JARVIS.")],
                ),
            ),
        )
        event_queue.enqueue_event(cancel_event)


# --------------------------------------------------------------------------- #
# FastAPI integration
# --------------------------------------------------------------------------- #
def mount_a2a_routes(app: Any) -> bool:
    """Mount A2A routes onto the existing FastAPI application.

    Args:
        app: A FastAPI application instance.

    Returns:
        True if A2A routes were mounted, False if a2a-sdk is not installed.
    """
    if not a2a_available():
        logger.info("a2a-sdk not installed; A2A routes not mounted (graceful degradation).")
        return False

    try:
        from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
        from a2a.server.routes.rest_routes import create_rest_routes
        from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
        from a2a.server.routes.agent_card_routes import create_agent_card_routes
        from a2a.server.request_handlers.default_request_handler_v2 import DefaultRequestHandlerV2
        from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

        agent_card = create_a2a_agent_card()
        executor = JarvisAgentExecutor()
        handler = DefaultRequestHandlerV2(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
            agent_card=agent_card,
        )
        jsonrpc_routes = create_jsonrpc_routes(handler, "/a2a")
        rest_routes = create_rest_routes(handler, path_prefix="/a2a")
        agent_card_routes = create_agent_card_routes(agent_card)

        add_a2a_routes_to_fastapi(
            app,
            agent_card_routes=agent_card_routes,
            jsonrpc_routes=jsonrpc_routes,
            rest_routes=rest_routes,
        )
        logger.info("A2A routes mounted on FastAPI app at /a2a and /.well-known/agent-card.json")
        return True

    except Exception as e:
        logger.error("Failed to mount A2A routes: %s", e, exc_info=True)
        return False


__all__ = [
    "JarvisAgentExecutor",
    "create_a2a_agent_card",
    "mount_a2a_routes",
    "a2a_available",
    "CAPABILITY_SKILLS",
]
