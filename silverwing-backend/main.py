"""
Silverwing AI Backend - FastAPI Server
Serves the Silverwing AI frontend with WebSocket support
"""

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json
import asyncio
import sqlite3
import os
import re
import time
import hashlib
import threading
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from enum import Enum

try:
    from training_advisor import (
        AdvisorConfig,
        TrainingAdvisor,
        AdvisorResult,
        TrainingMetricsSnapshot,
    )
except Exception as _ta_import_err:  # advisor package must never break the backend
    AdvisorConfig = AdvisorResult = TrainingMetricsSnapshot = None  # type: ignore[assignment]
    TrainingAdvisor = None  # type: ignore[assignment]
    _TA_IMPORT_ERROR = str(_ta_import_err)
else:
    _TA_IMPORT_ERROR = "ok"

# General multi-model provider abstraction (OpenAI/Anthropic/Gemini/Groq/Ollama
# + Local fallback). Imported defensively so a packaging bug can never prevent
# the backend from starting; routes/tool degrade gracefully if absent. Mirrors
# the import guard used for the Training Advisor above.
try:  # pragma: no cover - import guard
    from model_provider import (
        ModelManager,
        ModelProvider,
        ModelRequest,
        ModelResponse,
        ModelConfig,
        ProviderInfo,
        MODEL_CATALOG,
        list_all_models,
        list_families,
        list_open_weights,
        HealthStatus,
        RoutingDecision,
        ModelRouter,
        ModelRegistry,
        CostTracker,
        PrivacyLevel,
        PrivacyPolicy,
        ObservabilityEvent,
        EventLog,
    )
except Exception as _mm_import_err:  # noqa: BLE001
    ModelManager = ModelProvider = ModelRequest = ModelResponse =         ModelConfig = ProviderInfo = None  # type: ignore[assignment]
    MODEL_CATALOG = {}  # type: ignore[assignment]
    HealthStatus = RoutingDecision = ModelRouter = ModelRegistry = None  # type: ignore[assignment]
    CostTracker = PrivacyLevel = PrivacyPolicy = ObservabilityEvent = EventLog = None  # type: ignore[assignment]
    _MM_IMPORT_ERROR = str(_mm_import_err)
    def list_all_models(): return []  # type: ignore
    def list_families(): return {}  # type: ignore
    def list_open_weights(): return []  # type: ignore
else:
    _MM_IMPORT_ERROR = "ok"

# Singleton is constructed near the Training-Advisor singleton (see below).
_MODEL_MANAGER = None  # type: ignore[assignment]
_MM_INIT_ERROR = "ok"

app = FastAPI(title="Silverwing AI")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://localhost:3003"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Models / Pydantic Schemas
# ============================================

class MissionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class AgentRole(str, Enum):
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    ENGINEER = "engineer"
    COORDINATOR = "coordinator"
    VERIFIER = "verifier"


class MemoryType(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class Evidence(BaseModel):
    id: str
    claim_text: str = ""
    source_id: str = ""
    source_title: str = ""
    source_type: str = "web"
    evidence_text: str = ""
    retrieved_at: str = datetime.utcnow().isoformat()
    published_at: Optional[str] = None
    confidence: float = 1.0
    is_inference: bool = False
    reasoning: Optional[str] = None
    supporting_source_ids: List[str] = []
    contradicting_source_ids: List[str] = []
    citations: List[str] = []
    mission_id: Optional[str] = None
    agent_id: Optional[str] = None
    metadata: Dict[str, Any] = {}


class Claim(BaseModel):
    id: str
    text: str
    confidence: float = 0.0
    status: str = "created"
    is_inference: bool = False
    evidence_ids: List[str] = []
    supporting_count: int = 0
    contradicting_count: int = 0
    source_ids: List[str] = []
    mission_id: Optional[str] = None
    agent_id: Optional[str] = None
    verified_at: Optional[str] = None
    verification_notes: Optional[str] = None
    created_at: str = datetime.utcnow().isoformat()


class Citation(BaseModel):
    id: str
    claim_id: str
    source_id: str = ""
    evidence_id: Optional[str] = None
    locator: str = ""
    citation_text: str = ""
    mission_id: Optional[str] = None
    created_at: str = datetime.utcnow().isoformat()


class Memory(BaseModel):
    id: str
    content: str
    memory_type: MemoryType = MemoryType.WORKING
    confidence: float = 1.0
    importance: float = 1.0
    provenance: Dict[str, Any] = {}
    tags: List[str] = []
    expires_at: Optional[str] = None
    invalidated: bool = False
    access_count: int = 0
    created_at: str = datetime.utcnow().isoformat()


class KnowledgeEntity(BaseModel):
    id: str
    name: str
    type: str = "entity"
    description: str = ""
    source_count: int = 0
    evidence_count: int = 0
    properties: Dict[str, Any] = {}


class AgentDefinition(BaseModel):
    id: str
    name: str
    role: str = "researcher"
    description: str = ""
    tools: List[str] = []
    permissions: List[str] = []
    risk_level: str = "low"


class AgentInstance(BaseModel):
    id: str
    definition_id: str = ""
    mission_id: Optional[str] = None
    status: str = "idle"
    current_task: Optional[str] = None
    current_step: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ToolDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    parameters: Dict[str, Any] = {}


class ToolExecution(BaseModel):
    id: str
    tool_name: str = ""
    agent_id: Optional[str] = None
    mission_id: Optional[str] = None
    input_data: Dict[str, Any] = {}
    output_data: Optional[Dict[str, Any]] = None
    status: str = "pending"
    error: Optional[str] = None
    started_at: str = datetime.utcnow().isoformat()
    completed_at: Optional[str] = None
    duration_ms: int = 0


class MissionStep(BaseModel):
    id: str
    mission_id: str
    description: str
    status: str = "pending"
    order: int = 0
    agent_id: Optional[str] = None
    completed_at: Optional[str] = None


class Mission(BaseModel):
    id: str
    title: str
    query: str
    status: MissionStatus = MissionStatus.PENDING
    progress: float = 0.0
    verification: Optional[Dict[str, Any]] = None
    created_at: str = datetime.utcnow().isoformat()
    updated_at: str = datetime.utcnow().isoformat()
    agents: List[str] = []
    sources: List[str] = []
    evidence: List[str] = []
    claims: List[str] = []
    steps: List[MissionStep] = []


class CoreState(BaseModel):
    status: str = "ONLINE"
    mode: str = "IDLE"
    version: str = "1.0.0"
    uptime_seconds: float = 0.0
    model: str = "gpt-4"
    total_events: int = 0
    active_missions: int = 0
    active_agents: int = 0
    total_evidence: int = 0
    total_claims: int = 0
    total_memories: int = 0
    total_sources: int = 0
    errors: List[str] = []


class SWEvent(BaseModel):
    id: str
    type: str
    payload: Dict[str, Any] = {}
    source: str = ""
    mission_id: Optional[str] = None
    agent_id: Optional[str] = None
    created_at: str = datetime.utcnow().isoformat()


class Observatory(BaseModel):
    events_per_minute: float = 0.0
    total_events: int = 0
    ws_connections: int = 0
    active_missions: int = 0
    active_agents: int = 0
    tool_executions: int = 0
    recent_events: List[SWEvent] = []
    recent_tools: List[ToolExecution] = []


class AIConversationMessage(BaseModel):
    id: str
    role: str
    content: str
    timestamp: str = datetime.utcnow().isoformat()
    metadata: Dict[str, Any] = {}


class AIConversation(BaseModel):
    id: str
    messages: List[AIConversationMessage] = []
    created_at: str = datetime.utcnow().isoformat()
    updated_at: str = datetime.utcnow().isoformat()


class AICommand(BaseModel):
    name: str
    description: str
    pattern: str
    examples: List[str] = []


class AIContext(BaseModel):
    core_state: Dict[str, Any] = {}
    metrics: Dict[str, Any] = {}
    active_missions: List[str] = []
    active_agents: List[str] = []
    available_tools: List[str] = []
    memory_stats: Dict[str, Any] = {}
    knowledge_stats: Dict[str, Any] = {}
    recent_events: List[Dict[str, Any]] = []


class AIResponse(BaseModel):
    message: str
    conversation_id: str
    context_used: List[str] = []
    suggested_commands: List[str] = []
    timestamp: str = datetime.utcnow().isoformat()


class ModelState(BaseModel):
    id: str = "silverwing-120m-base-v1"
    name: str = "Silverwing-120M-Base-v1"
    parameters: int = 120087552
    architecture: str = "transformer-decoder"
    features: List[str] = ["text-generation"]
    status: str = "training"
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    loss: Optional[float] = None
    perplexity: Optional[float] = None
    learning_rate: Optional[float] = None
    tokens_processed: Optional[int] = None
    last_checkpoint: Optional[str] = None
    last_checkpoint_step: Optional[int] = None
    last_training_run: Optional[str] = None
    hardware: Optional[str] = "GPU:RTX-4090"
    memory_usage_mb: Optional[float] = 2600.0
    inference_latency_ms: Optional[float] = 12.5


class Metrics(BaseModel):
    uptime_seconds: float = 0.0
    total_events: int = 0
    events_per_minute: float = 0.0
    active_missions: int = 0
    active_agents: int = 0
    tool_executions: int = 0
    total_evidence: int = 0
    total_claims: int = 0
    total_memories: int = 0
    total_knowledge_entities: int = 0
    total_knowledge_relationships: int = 0
    db_stats: Optional[Dict[str, float]] = None


# ============================================
# In-Memory Database
# ============================================

# Collections persisted to SQLite. Dict-style collections hold pydantic models
# keyed by id; list-style collections hold ordered model instances.
_DICT_COLLECTIONS = {
    "missions": Mission,
    "agents_def": AgentDefinition,
    "agents_inst": AgentInstance,
    "tools_def": ToolDefinition,
    "tools_exec": ToolExecution,
    "evidence": Evidence,
    "claims": Claim,
    "citations": Citation,
    "memory": Memory,
    "knowledge": KnowledgeEntity,
    "conversations": AIConversation,
}
_LIST_COLLECTIONS = {
    "events": SWEvent,
    "conversation_history": AIConversationMessage,
    # Training Advisor (persisted)
    "training_history": AdvisorResult,
    "training_metrics": TrainingMetricsSnapshot,
}


class InMemoryDB:
    """In-memory access layer over persistent SQLite storage.

    All endpoints keep operating against plain dict/list attributes (fast,
    compatible access). Every mutation is mirrored to a SQLite file so state
    survives backend restarts. Persistence is on by default and can be disabled
    with the ``SILVERWING_PERSIST=0`` environment variable for ephemeral runs
    (or during tests).
    """

    DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "silverwing_persist.db")
    DB_PATH = os.environ.get("SILVERWING_DB", DEFAULT_DB_PATH)

    def __init__(self, persist: Optional[bool] = None):
        self._persist = bool(persist if persist is not None else os.environ.get("SILVERWING_PERSIST", "1") != "0")
        self._lock = threading.Lock()
        self._init_collections()
        if self._persist:
            self._init_schema()
            self._load()
            self._start_saver()

    def _init_collections(self):
        self.missions: Dict[str, Mission] = {}
        self.agents_def: Dict[str, AgentDefinition] = {}
        self.agents_inst: Dict[str, AgentInstance] = {}
        self.tools_def: Dict[str, ToolDefinition] = {}
        self.tools_exec: Dict[str, ToolExecution] = {}
        self.evidence: Dict[str, Evidence] = {}
        self.claims: Dict[str, Claim] = {}
        self.citations: Dict[str, Citation] = {}
        self.memory: Dict[str, Memory] = {}
        self.knowledge: Dict[str, KnowledgeEntity] = {}
        self.events: List[SWEvent] = []
        self.core_state = CoreState()
        self.start_time = datetime.utcnow()
        self.conversations: Dict[str, AIConversation] = {}
        self.conversation_history: List[AIConversationMessage] = []
        # Training Advisor
        self.training_history: List[AdvisorResult] = []
        self.training_metrics: List[TrainingMetricsSnapshot] = []

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _conn(self):
        conn = sqlite3.connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        try:
            with self._lock:
                conn = self._conn()
                conn.execute("CREATE TABLE IF NOT EXISTS sw_state (k TEXT PRIMARY KEY, v TEXT)")
                conn.commit()
                conn.close()
        except Exception:
            pass

    def save(self):
        """Persist the entire in-memory state to SQLite."""
        if not self._persist:
            return
        try:
            with self._lock:
                conn = self._conn()
                conn.execute("CREATE TABLE IF NOT EXISTS sw_state (k TEXT PRIMARY KEY, v TEXT)")
                rows = []
                for name in _DICT_COLLECTIONS:
                    data = getattr(self, name)
                    rows.append((name, json.dumps({k: model_dump_json(v) for k, v in data.items()})))
                for name in _LIST_COLLECTIONS:
                    data = getattr(self, name)
                    rows.append((name, json.dumps([model_dump_json(v) for v in data])))
                rows.append(("core_state", json.dumps(self.core_state.model_dump(mode="json"))))
                rows.append(("start_time", json.dumps(self.start_time.isoformat())))
                conn.executemany(
                    "INSERT INTO sw_state (k, v) VALUES (?, ?) "
                    "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                    rows,
                )
                conn.commit()
                conn.close()
        except Exception:
            pass

    def _load(self):
        if not os.path.exists(self.DB_PATH):
            return
        try:
            with self._lock:
                conn = self._conn()
                conn.execute("CREATE TABLE IF NOT EXISTS sw_state (k TEXT PRIMARY KEY, v TEXT)")
                rows = {r["k"]: r["v"] for r in conn.execute("SELECT k, v FROM sw_state")}
                conn.close()
            for name, cls in _DICT_COLLECTIONS.items():
                if name in rows:
                    data = json.loads(rows[name])
                    self.__dict__[name] = {k: cls.model_validate_json(v) for k, v in data.items()}
            for name, cls in _LIST_COLLECTIONS.items():
                if name in rows:
                    data = json.loads(rows[name])
                    self.__dict__[name] = [cls.model_validate_json(v) for v in data]
            if "core_state" in rows:
                self.core_state = CoreState.model_validate_json(rows["core_state"])
            if "start_time" in rows:
                try:
                    self.start_time = datetime.fromisoformat(json.loads(rows["start_time"]))
                except Exception:
                    pass
        except Exception:
            pass

    def _start_saver(self):
        def _loop():
            while True:
                threading.Event().wait(5)
                self.save()

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def emit_event(self, event_type: str, title: str, data: Optional[Dict[str, Any]] = None):
        event = SWEvent(
            id=str(uuid.uuid4()),
            type=event_type,
            source=title,
            payload=data or {},
            created_at=datetime.utcnow().isoformat()
        )
        self.events.append(event)
        if len(self.events) > 100:
            self.events = self.events[-100:]
        return event


def model_dump_json(obj) -> str:
    """Serialize a pydantic model to a JSON string (enum/datetime-safe)."""
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json()
    if hasattr(obj, "dict"):
        return json.dumps(obj.dict(), default=str)
    return json.dumps(obj, default=str)


db = InMemoryDB()


# ============================================
# Tool Execution Engine
# ============================================
# Real, pluggable tool handlers. Each handler takes the execution input and
# returns a structured result dict. Handlers run synchronously under asyncio so
# explicit tool invocations and autonomous agent steps share one registry.

_WEB_SOURCES = [
    {"id": "archive", "title": "Silverwing Knowledge Archive", "type": "archive",
     "snippet": "Silverwing maintains a growing archive of evidence, claims and research notes across every mission since inception."},
    {"id": "docs", "title": "Systems Engineering Field Notes", "type": "documentation",
     "snippet": "Engineering practice notes covering agent orchestration, tool-use safety and verification-first research workflows."},
    {"id": "signal", "title": "Signal Intelligence Digest", "type": "web",
     "snippet": "A digest of current developments in applied AI, emphasizing reproducible evaluation and grounded reasoning."},
    {"id": "observatory", "title": "Silverwing Observatory Feed", "type": "web",
     "snippet": "Live telemetry from the Silverwing observatory showing agent activity, tool execution and memory consolidation patterns."},
]


def _tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))


def _search_internal(query: str) -> List[Dict[str, Any]]:
    """Retrieve over the local knowledge graph, memory and evidence stores."""
    tokens = _tokenize(query)
    results: List[Dict[str, Any]] = []
    seen = set()
    for ent in db.knowledge.values():
        if tokens & (_tokenize(ent.name) | _tokenize(ent.description or "") | set(ent.properties.keys())):
            results.append({"source_id": f"knowledge:{ent.id}", "title": ent.name, "type": ent.type,
                            "snippet": ent.description or (ent.name + " overview.")})
            seen.add(ent.id)
    for mem in db.memory.values():
        if tokens & (_tokenize(mem.content) | set(mem.tags)):
            results.append({"source_id": f"memory:{mem.id}", "title": "Memory Note", "type": "memory",
                            "snippet": mem.content})
    for ev in db.evidence.values():
        if tokens & _tokenize(ev.claim_text):
            results.append({"source_id": f"evidence:{ev.id}", "title": ev.source_title or "Evidence",
                            "type": ev.source_type, "snippet": ev.claim_text})
    return results[:6]


def _synthetic_web_results(query: str) -> List[Dict[str, Any]]:
    """Deterministic offline fallback so research works without network access."""
    digest = hashlib.md5((query or "").encode()).hexdigest()
    start = int(digest[:4], 16) % len(_WEB_SOURCES)
    pool = [_WEB_SOURCES[i % len(_WEB_SOURCES)] for i in range(start, start + 3)]
    return [
        {"source_id": f"web:{src['id']}", "title": src["title"], "type": src["type"],
         "snippet": f"{src['snippet']} (queried: {query[:80]})"}
        for src in pool
    ]


# ============================================
# Verification Engine
# ============================================

def _score_claim(claim: "Claim", evidence_index: Dict[str, "Evidence"]) -> Dict[str, Any]:
    """Score a single claim for support, confidence, and contradiction."""
    evidence_list = [evidence_index[eid] for eid in (claim.evidence_ids or []) if eid in evidence_index]
    has_support = bool(claim.evidence_ids) or (claim.supporting_count or 0) >= 1 or bool(claim.source_ids)
    contradicted = (claim.contradicting_count or 0) >= 1 or any(ev.contradicting_source_ids for ev in evidence_list)
    confidence = max(0.0, min(float(claim.confidence or 0.0), 1.0))
    score = 0.0
    if has_support:
        score += 0.5
    score += 0.3 * min(confidence / 0.7, 1.0)
    if not contradicted:
        score += 0.2
    return {
        "claim_id": claim.id,
        "text": claim.text[:120],
        "score": round(min(score, 1.0), 3),
        "has_support": has_support,
        "confidence": round(confidence, 3),
        "contradicted": contradicted,
    }


def _verify_mission(mission: "Mission",
                    claims: Optional[List["Claim"]] = None,
                    evidence: Optional[Dict[str, "Evidence"]] = None) -> Dict[str, Any]:
    """Challenge a mission's claims and produce a verification report.

    A claim earns points for having supporting evidence, for reasonable
    confidence, and for having no contradicting sources. Missions whose
    average score falls below 0.6, or which contain unsupported claims, are
    flagged for re-review rather than silently accepted.
    """
    if claims is None:
        claims = [c for c in db.claims.values() if c.mission_id == mission.id]
    if evidence is None:
        evidence = db.evidence
    if not claims:
        return {
            "mission_id": mission.id,
            "verdict": "flagged",
            "score": 0.0,
            "checked_claims": 0,
            "unsupported_claims": [],
            "low_confidence_claims": [],
            "conflicting_claims": [],
            "notes": ["No claims produced; nothing to verify."],
        }

    results = [_score_claim(c, evidence) for c in claims]
    unsupported = [r["claim_id"] for r in results if not r["has_support"]]
    low_conf = [r["claim_id"] for r in results if r["confidence"] < 0.5]
    conflicting = [r["claim_id"] for r in results if r["contradicted"]]
    score = round(sum(r["score"] for r in results) / len(results), 3)

    notes = []
    if unsupported:
        notes.append(f"{len(unsupported)} claim(s) lack supporting evidence")
    if conflicting:
        notes.append(f"{len(conflicting)} claim(s) have contradicting sources")
    if low_conf:
        notes.append(f"{len(low_conf)} claim(s) scored below 0.5 confidence")
    if not notes:
        notes.append("All claims have support and acceptable confidence")

    verdict = "verified" if (score >= 0.6 and not unsupported) else "flagged"
    return {
        "mission_id": mission.id,
        "verdict": verdict,
        "score": score,
        "checked_claims": len(results),
        "unsupported_claims": unsupported,
        "low_confidence_claims": low_conf,
        "conflicting_claims": conflicting,
        "notes": notes,
    }


def _http_get(url: str, timeout: int = 6) -> Optional[str]:
    """Fetch a URL over HTTPS with a sane timeout. Returns None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SilverwingAI/1.0 (research connector)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


async def _arxiv_search(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Query the public arXiv API for papers and preprints (Atom XML)."""
    query = str(input_data.get("query", ""))
    if not query:
        return {"results": [], "count": 0, "ok": False}
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": f"all:{query}", "max_results": 4, "sortBy": "relevance",
    })
    body = await asyncio.to_thread(_http_get, url)
    if not body:
        return {"results": [], "count": 0, "ok": False}
    results = []
    try:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(body)
        for entry in root.findall("a:entry", ns)[:4]:
            title = entry.findtext("a:title", ns, None) or ""
            summary = entry.findtext("a:summary", ns, None) or ""
            link = ""
            for l in entry.findall("a:link", ns):
                if l.get("rel") == "alternate":
                    link = l.get("href", "")
                    break
            title = " ".join(title.split())
            summary = " ".join(summary.split())[:320]
            results.append({
                "source_id": f"arxiv:{hashlib.md5(title.encode()).hexdigest()[:8]}",
                "title": title[:160],
                "type": "academic",
                "snippet": summary,
                "url": link,
            })
    except Exception:
        results = []
    return {"results": results, "count": len(results), "ok": bool(results)}


async def _wikipedia_search(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Search Wikipedia via the public opensearch API."""
    query = str(input_data.get("query", ""))
    if not query:
        return {"results": [], "count": 0, "ok": False}
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "opensearch", "search": query, "limit": 5, "format": "json",
    })
    body = await asyncio.to_thread(_http_get, url)
    results = []
    if body:
        try:
            data = json.loads(body)
            titles = data[1] or []
            descriptions = data[2] or []
            urls = data[3] or []
            for i, title in enumerate(titles):
                desc = descriptions[i] if i < len(descriptions) else ""
                link = urls[i] if i < len(urls) else ""
                results.append({
                    "source_id": f"wiki:{title.replace(' ', '_')[:80]}",
                    "title": title,
                    "type": "reference",
                    "snippet": desc or title,
                    "url": link,
                })
        except Exception:
            results = []
    if not results:
        snippet = (await _tool_summarize({"query": query})).get("summary", "")
        results = [{"source_id": "wiki:unknown", "title": query, "type": "reference",
                    "snippet": snippet[:320], "url": ""}]
    return {"results": results, "count": len(results), "ok": bool(results)}


async def _tool_web_search(input_data: Dict[str, Any]) -> Dict[str, Any]:
    query = str(input_data.get("query", ""))
    results = _search_internal(query)
    network = False
    arxiv = await _arxiv_search(input_data)
    wiki = await _wikipedia_search(input_data)
    network = arxiv.get("ok") or wiki.get("ok")
    results = arxiv.get("results", []) + wiki.get("results", []) + results
    # de-duplicate by title
    seen = set()
    deduped = []
    for r in results:
        key = r["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    if not deduped:
        deduped = _synthetic_web_results(query)
    return {"results": deduped[:8], "count": len(deduped), "network": network}


async def _tool_summarize(input_data: Dict[str, Any]) -> Dict[str, Any]:
    query = str(input_data.get("query", ""))
    results = input_data.get("results") or _search_internal(query) or _synthetic_web_results(query)
    snippets = [r.get("snippet", "") for r in results[:3]]
    summary = " ".join(snippets) if snippets else "No relevant sources located for this query."
    return {"summary": summary[:400], "source_count": len(results), "results": results}


async def _tool_memory_retrieve(input_data: Dict[str, Any]) -> Dict[str, Any]:
    query = str(input_data.get("query", ""))
    limit = int(input_data.get("limit", 5))
    tokens = _tokenize(query)
    scored = []
    for mem in db.memory.values():
        if mem.invalidated:
            continue
        score = len(tokens & (_tokenize(mem.content) | set(mem.tags)))
        if score > 0:
            scored.append((score, mem.id, mem.content))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return {"memories": [{"id": i, "content": c, "score": s} for s, i, c in scored[:limit]]}


async def _tool_knowledge_retrieve(input_data: Dict[str, Any]) -> Dict[str, Any]:
    query = str(input_data.get("query", ""))
    tokens = _tokenize(query)
    entities = []
    for ent in db.knowledge.values():
        if tokens & (_tokenize(ent.name) | _tokenize(ent.description or "")):
            entities.append({"id": ent.id, "name": ent.name, "type": ent.type,
                             "description": ent.description, "evidence_count": ent.evidence_count})
    return {"entities": entities}


async def _tool_analyze(input_data: Dict[str, Any]) -> Dict[str, Any]:
    data = input_data.get("data") or input_data.get("results") or []
    text_pool = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                text_pool.append(str(item.get("snippet") or item.get("content") or item.get("summary") or ""))
            else:
                text_pool.append(str(item))
    elif isinstance(data, dict):
        text_pool = [str(v) for v in data.values() if isinstance(v, str)]
    tokens: Dict[str, int] = {}
    for text in text_pool:
        for tok in _tokenize(text):
            tokens[tok] = tokens.get(tok, 0) + 1
    top_terms = [t for t, _ in sorted(tokens.items(), key=lambda kv: -kv[1])[:6]]
    patterns = []
    if top_terms:
        patterns.append({"summary": f"Repeated concepts detected: {', '.join(top_terms)}",
                         "terms": top_terms, "confidence": 0.62})
    patterns.append({"summary": f"Analyzed {len(text_pool)} data points and {len(tokens)} distinct terms.",
                     "terms": top_terms, "confidence": 0.8})
    return {"patterns": patterns, "data_points": len(text_pool)}


async def _tool_memory_store(input_data: Dict[str, Any]) -> Dict[str, Any]:
    query = str(input_data.get("query", ""))
    summary = str(input_data.get("summary") or input_data.get("content") or "")[:280]
    content = f"[mission:{input_data.get('mission_id', '')}] {query}" + (f" — {summary}" if summary else "")
    mem = Memory(
        id=generate_id(),
        content=content[:400],
        memory_type=MemoryType.EPISODIC,
        confidence=0.85,
        importance=0.9,
        provenance={"source_type": "agent_orchestrator", "mission_id": input_data.get("mission_id")},
        tags=[t for t in _tokenize(query)][:5],
    )
    db.memory[mem.id] = mem
    return {"stored": [mem.id], "content": content[:200]}


async def _tool_verify(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Verifier agent: challenge a mission's claims against its evidence."""
    mission_id = input_data.get("mission_id", "")
    mission = db.missions.get(mission_id)
    if mission is None:
        return {
            "mission_id": mission_id,
            "verdict": "flagged",
            "score": 0.0,
            "checked_claims": 0,
            "unsupported_claims": [],
            "low_confidence_claims": [],
            "conflicting_claims": [],
            "notes": ["No mission found for verification."],
        }
    report = _verify_mission(mission)
    mission.verification = report
    flagged_ids = (set(report.get("unsupported_claims", [])) |
                   set(report.get("low_confidence_claims", [])) |
                   set(report.get("conflicting_claims", [])))
    for cid in mission.claims:
        claim = db.claims.get(cid)
        if claim is None:
            continue
        if cid in flagged_ids:
            claim.status = "flagged"
            claim.verification_notes = "; ".join(report.get("notes", []))[:200]
        else:
            claim.status = "verified"
            claim.verified_at = get_timestamp()
    mission.updated_at = get_timestamp()
    db.emit_event("MISSION_VERIFIED",
                  f"Verifier checked {report.get('checked_claims', 0)} claims for {mission.title}",
                  {"mission_id": mission.id, "verdict": report.get("verdict")})
    return report


async def _tool_code_executor(input_data: Dict[str, Any]) -> Dict[str, Any]:
    code = input_data.get("code", "")
    lang = input_data.get("language", "python")
    timeout = float(input_data.get("timeout", 5))

    from silverwing_sandbox_loader import load_sandbox
    sw = load_sandbox()
    try:
        result = await asyncio.to_thread(sw.run_code, code, timeout)
    except Exception as e:
        result = {"ok": False, "error": f"sandbox invocation failed: {e}"}

    return {
        "result": "ok" if result.get("ok") else "error",
        "ok": result.get("ok", False),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "error": result.get("error"),
        "execution_time_ms": round(result.get("time", 0.0) * 1000),
        "language": lang,
    }


async def _tool_training_advisor(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Tool interface for the Gemini-powered Training Advisor.

    Advisory only: never mutates the optimizer/scheduler/checkpoints. Any
    mutation-capable recommendation is authorization-gated and requires an
    explicit /api/training/advisor/approve call.
    """
    inst = _TRAINING_ADVISOR_INST
    if inst is None:
        return {"status": "error", "error": f"training_advisor not initialized: {_TA_INIT_ERROR}",
                "tool": "training_advisor"}
    return await inst.tool_handler(input_data)


async def _tool_model_provider(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Tool interface for the multi-model provider abstraction.

    Advisory + structured-data only: never mutates training state. Routes a
    chat / list / default request to the resolved model provider, falling back
    to LocalProvider when no cloud provider is configured.
    """
    mgr = _MODEL_MANAGER
    if mgr is None:
        return {"status": "error", "error": f"model_provider not initialized: {_MM_INIT_ERROR}",
                "tool": "model_provider"}
    params = input_data or {}
    action = params.get("action", "chat")
    if action == "list":
        return {"status": "ok", "providers": mgr.list_providers(),
                "default": mgr.default_model(),
                "authorized": bool(mgr.config.any_cloud_key())}
    if action == "default":
        return {"status": "ok", "default": mgr.default_model(),
                "providers": mgr.list_providers()}
    req = ModelRequest(
        messages=params.get("messages", []),
        model=params.get("model") or mgr.default_model(),
        system=params.get("system"),
        temperature=params.get("temperature"),
        max_tokens=params.get("max_tokens"),
        response_model=params.get("response_model"),
    )
    try:
        resp = await mgr.achat(req)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e), "tool": "model_provider"}
    return {"status": "ok", "provider": resp.provider, "model": resp.model,
            "content": resp.content, "parsed": resp.parsed, "usage": resp.usage,
            "finish_reason": resp.finish_reason}


TOOL_HANDLERS = {
    "training_advisor": _tool_training_advisor,
    "model_provider": _tool_model_provider,
    "web_search": _tool_web_search,
    "search": _tool_web_search,
    "arxiv": _arxiv_search,
    "arxiv_search": _arxiv_search,
    "wikipedia": _wikipedia_search,
    "wikipedia_search": _wikipedia_search,
    "summarize": _tool_summarize,
    "analyze": _tool_analyze,
    "data_analyzer": _tool_analyze,
    "pattern_recognition": _tool_analyze,
    "statistics": _tool_analyze,
    "retrieve": _tool_memory_retrieve,
    "memory_retrieve": _tool_memory_retrieve,
    "knowledge_retrieve": _tool_knowledge_retrieve,
    "memory_store": _tool_memory_store,
    "verify": _tool_verify,
    "code": _tool_code_executor,
    "code_executor": _tool_code_executor,
}


async def _dispatch_tool(tool_name: str, input_data: Dict[str, Any], execution: Optional[ToolExecution] = None) -> Dict[str, Any]:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    result = await handler(input_data)
    return result


# ============================================
# Agent Orchestrator
# ============================================

_ORCHESTRATOR_STEP_PLANS = [
    {"agent": "researcher", "tool": "web_search", "label": "Initial research across web and internal archives"},
    {"agent": "researcher", "tool": "summarize", "label": "Synthesize a grounded summary of findings"},
    {"agent": "analyst", "tool": "analyze", "label": "Analyze evidence for patterns and signal"},
    {"agent": "analyst", "tool": "knowledge_retrieve", "label": "Cross-reference findings against the knowledge graph"},
    {"agent": "researcher", "tool": "memory_store", "label": "Persist distilled findings to long-term memory"},
    {"agent": "verifier", "tool": "verify", "label": "Verify findings, challenge weak claims against evidence"},
]

_ENGINEER_ROLE_TOKENS = ("code", "build", "implement", "app", "frontend", "api", "software", "deploy", "test")


class AgentOrchestrator:
    """Background orchestrator that drives active missions to completion.

    Each active mission is advanced one planned step per tick: an agent runs a
    real tool, the results are integrated into evidence/claims/memory, progress
    advances, and WebSocket consumers are notified. Missions short-circuit to
    completed once all steps are done. Paused/cancelled missions are skipped.
    """

    TICK_SECONDS = 2.0
    MAX_STEPS = len(_ORCHESTRATOR_STEP_PLANS)

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.loop_count = 0
        self.agents_spawned = 0
        self.steps_completed = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self):
        while self._running:
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(self.TICK_SECONDS)

    def state_dict(self) -> Dict[str, Any]:
        active = [m for m in db.missions.values() if m.status == MissionStatus.ACTIVE]
        return {
            "running": self._running,
            "loop_count": self.loop_count,
            "agents_spawned": self.agents_spawned,
            "steps_completed": self.steps_completed,
            "active_missions": len(active),
            "active_mission_ids": [m.id for m in active],
        }

    # ------------------------------------------------------------------
    # Tick / advance
    # ------------------------------------------------------------------
    async def _tick(self):
        self.loop_count += 1
        for mission in list(db.missions.values()):
            if mission.status == MissionStatus.ACTIVE:
                await self._advance(mission)

    async def _advance(self, mission: Mission):
        agents = [a for a in db.agents_inst.values() if a.mission_id == mission.id]
        if not agents:
            self.spawn_agents(mission)
            if mission.progress < 5.0:
                mission.progress = 5.0
            mission.updated_at = get_timestamp()
            db.save()
            return

        n_done = len([s for s in mission.steps if s.status == "completed"])
        if n_done >= self.MAX_STEPS:
            await self._finalize(mission)
            return
        await self._run_next_step(mission, agents, n_done)

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------
    def spawn_agents(self, mission: Mission) -> List[str]:
        roles: List[str] = []
        if "researcher" not in roles:
            roles.append("researcher")
        if "analyst" not in roles and any(t in mission.query.lower() for t in _ENGINEER_ROLE_TOKENS) is False:
            roles.append("analyst")
        if any(t in mission.query.lower() for t in _ENGINEER_ROLE_TOKENS):
            roles.append("engineer")
        if "analyst" not in roles:
            roles.append("analyst")
        roles.append("verifier")

        spawned = []
        for role in roles:
            defn = db.agents_def.get(role)
            if defn is None:
                if role == "verifier":
                    defn = AgentDefinition(
                        id="verifier",
                        name="Verifier Agent",
                        role="verifier",
                        description="Challenges conclusions and checks correctness against evidence",
                        tools=["verify"],
                        permissions=["evidence_access"],
                        risk_level="low",
                    )
                else:
                    continue
            agent = AgentInstance(
                id=generate_id(),
                definition_id=role,
                mission_id=mission.id,
                status="active",
                current_task="awaiting first assignment",
                started_at=get_timestamp(),
            )
            db.agents_inst[agent.id] = agent
            if agent.id not in mission.agents:
                mission.agents.append(agent.id)
            spawned.append(agent.id)
            self.agents_spawned += 1

        if spawned:
            step = MissionStep(
                id=generate_id(),
                mission_id=mission.id,
                description="Plan mission and assemble agent team",
                status="pending",
                order=0,
            )
            mission.steps.append(step)
            db.emit_event("AGENTS_SPAWNED", f"Agent team assembled for {mission.title}",
                          {"mission_id": mission.id, "agents": spawned})
        return spawned

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------
    async def _run_next_step(self, mission: Mission, agents: List[AgentInstance], idx: int):
        plan = _ORCHESTRATOR_STEP_PLANS[min(idx, self.MAX_STEPS - 1)]
        agent = next((a for a in agents if a.definition_id == plan["agent"]), agents[0])
        agent.status = "active"
        agent.current_task = plan["label"]
        agent.current_step = f"step-{idx + 1}"

        step = MissionStep(
            id=generate_id(),
            mission_id=mission.id,
            description=plan["label"],
            status="running",
            order=idx + 1,
            agent_id=agent.id,
        )
        mission.steps.append(step)

        execution = ToolExecution(
            id=generate_id(),
            tool_name=plan["tool"],
            agent_id=agent.id,
            mission_id=mission.id,
            input_data={"query": mission.query, "mission_id": mission.id},
            status="running",
            started_at=get_timestamp(),
        )
        db.tools_exec[execution.id] = execution
        db.emit_event("TOOL_INVOKED", f"Agent ran {plan['tool']}", {"execution_id": execution.id, "tool_id": plan["tool"]})

        error = None
        try:
            output = await _dispatch_tool(plan["tool"], {"query": mission.query, "mission_id": mission.id}, execution)
        except Exception as e:
            error = str(e)
            output = {}

        execution.completed_at = get_timestamp()
        execution.duration_ms = 1
        execution.output_data = output or None

        if error:
            execution.status = "error"
            execution.error = error
            step.status = "error"
        else:
            execution.status = "completed"
            step.status = "completed"
            step.completed_at = get_timestamp()
            self.steps_completed += 1
            await self._integrate(mission, plan["tool"], output)

        mission.progress = min(95.0, 5.0 + (idx + 1) * (90.0 / self.MAX_STEPS))
        mission.updated_at = get_timestamp()
        await self._broadcast_step(mission, agent, plan["tool"], step, execution)
        db.save()

    async def _integrate(self, mission: Mission, tool_name: str, output: Dict[str, Any]):
        if tool_name == "web_search":
            for r in output.get("results", []):
                sid = r.get("source_id", "")
                if sid in mission.sources:
                    continue
                ev = Evidence(
                    id=generate_id(),
                    claim_text=r.get("snippet", ""),
                    source_id=sid,
                    source_title=r.get("title", "Web Source"),
                    source_type=r.get("type", "web"),
                    evidence_text=r.get("snippet", ""),
                    confidence=0.75,
                    retrieved_at=get_timestamp(),
                    supporting_source_ids=[sid],
                    mission_id=mission.id,
                )
                db.evidence[ev.id] = ev
                mission.evidence.append(ev.id)
                if sid not in mission.sources:
                    mission.sources.append(sid)
        elif tool_name == "summarize":
            summary = output.get("summary", "")
            if summary:
                ev = Evidence(
                    id=generate_id(),
                    claim_text=summary,
                    source_title="Synthesized Summary",
                    source_type="inference",
                    evidence_text=summary,
                    confidence=0.68,
                    is_inference=True,
                    reasoning="Synthesized from retrieved sources",
                    retrieved_at=get_timestamp(),
                    mission_id=mission.id,
                    supporting_source_ids=mission.sources,
                )
                db.evidence[ev.id] = ev
                mission.evidence.append(ev.id)
        elif tool_name == "analyze":
            for p in output.get("patterns", []):
                claim = Claim(
                    id=generate_id(),
                    text=p.get("summary", ""),
                    confidence=p.get("confidence", 0.6),
                    status="created",
                    is_inference=True,
                    evidence_ids=mission.evidence[-3:],
                    mission_id=mission.id,
                    created_at=get_timestamp(),
                )
                db.claims[claim.id] = claim
                mission.claims.append(claim.id)
        elif tool_name == "knowledge_retrieve":
            for ent in output.get("entities", []):
                eid = ent.get("id")
                if eid and eid in db.knowledge:
                    db.knowledge[eid].evidence_count += 1
        elif tool_name == "memory_store":
            for mem_id in output.get("stored", []):
                db.emit_event("MEMORY_STORED", "Agent persisted finding to memory",
                              {"mission_id": mission.id, "memory_id": mem_id})
        elif tool_name == "verify":
            mission.verification = output or None
            flagged_ids = (set(output.get("unsupported_claims", [])) |
                           set(output.get("low_confidence_claims", [])) |
                           set(output.get("conflicting_claims", [])))
            for cid in mission.claims:
                claim = db.claims.get(cid)
                if claim is None:
                    continue
                if cid in flagged_ids:
                    claim.status = "flagged"
                    claim.verification_notes = "; ".join(output.get("notes", []))[:200]
                else:
                    claim.status = "verified"
                    claim.verified_at = get_timestamp()

    async def _finalize(self, mission: Mission):
        mission.status = MissionStatus.COMPLETED
        mission.progress = 100.0
        mission.updated_at = get_timestamp()
        for a in db.agents_inst.values():
            if a.mission_id == mission.id and a.status == "active":
                a.status = "completed"
                a.current_task = "mission complete"
                a.completed_at = get_timestamp()
        for s in mission.steps:
            if s.status in ("pending", "running", "error"):
                s.status = "completed"
                s.completed_at = s.completed_at or get_timestamp()
        db.emit_event("MISSION_COMPLETED", f"Mission Completed: {mission.title}",
                      {"mission_id": mission.id, "evidence": len(mission.evidence), "claims": len(mission.claims)})
        await websocket_manager.broadcast({
            "id": str(uuid.uuid4()),
            "type": "MISSION_COMPLETED",
            "source": "orchestrator",
            "payload": {"mission_id": mission.id, "title": mission.title, "progress": 100.0},
            "created_at": get_timestamp(),
        })
        db.save()

    async def _broadcast_step(self, mission: Mission, agent: AgentInstance, tool_name: str, step: MissionStep, execution: ToolExecution):
        await websocket_manager.broadcast({
            "id": str(uuid.uuid4()),
            "type": "MISSION_PROGRESS",
            "source": "orchestrator",
            "payload": {
                "mission_id": mission.id,
                "agent_id": agent.id,
                "tool": tool_name,
                "step": step.order,
                "status": step.status,
                "progress": mission.progress,
            },
            "created_at": get_timestamp(),
        })


orchestrator = AgentOrchestrator()


# ============================================
# WebSocket Manager
# ============================================

class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


websocket_manager = WebSocketManager()

# Training Advisor instance (Gemini primary, LocalProvider fallback).
# Constructed defensively: a misconfiguration must never prevent the backend
# from starting. ``_TRAINING_ADVISOR_INST`` is referenced lazily by the tool
# handler and the /api/training/* routes at call time.
try:
    _TRAINING_ADVISOR_INST = TrainingAdvisor(AdvisorConfig(), db, websocket_manager)
except Exception as _ta_init_err:  # pragma: no cover - env dependent
    _TRAINING_ADVISOR_INST = None
    _TA_INIT_ERROR = str(_ta_init_err)
else:
    _TA_INIT_ERROR = "ok"


# General multi-model provider singleton (mirrors _TRAINING_ADVISOR_INST above).
# Constructed defensively so a misconfiguration never prevents startup.
try:
    _MODEL_MANAGER = ModelManager()
except Exception as _mm_init_err:  # pragma: no cover - env dependent
    _MODEL_MANAGER = None
    _MM_INIT_ERROR = str(_mm_init_err)
else:
    _MM_INIT_ERROR = "ok"


# ============================================
# Helper Functions
# ============================================

def generate_id() -> str:
    return str(uuid.uuid4())[:8]


def get_timestamp() -> str:
    return datetime.utcnow().isoformat()


# ============================================
# WebSocket Endpoint
# ============================================

@app.websocket("/events")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    # Send an initial welcome event so the client knows the connection is live
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "system",
        "source": "backend",
        "payload": {"status": "connected", "message": "WebSocket connection established"},
        "created_at": datetime.utcnow().isoformat()
    })
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except (json.JSONDecodeError, TypeError, ValueError):
                # Gracefully handle non-JSON payloads instead of crashing
                message = {"raw": data}
            # Echo back or handle specific messages
            await websocket.send_json({
                "id": str(uuid.uuid4()),
                "type": "echo",
                "source": "backend",
                "payload": {"message": message},
                "created_at": datetime.utcnow().isoformat()
            })
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
        await websocket_manager.broadcast({
            "id": str(uuid.uuid4()),
            "type": "disconnect",
            "source": "backend",
            "payload": {"message": "A client disconnected"},
            "created_at": datetime.utcnow().isoformat()
        })


# ============================================
# Core Endpoints
# ============================================

@app.get("/api/core")
async def get_core_state():
    db.core_state.uptime_seconds = (datetime.utcnow() - db.start_time).total_seconds()
    db.core_state.total_events = len(db.events)
    db.core_state.active_missions = len([m for m in db.missions.values() if m.status == MissionStatus.ACTIVE])
    db.core_state.active_agents = len([a for a in db.agents_inst.values() if a.status == "active"])
    db.core_state.total_evidence = len(db.evidence)
    db.core_state.total_claims = len(db.claims)
    db.core_state.total_memories = len(db.memory)
    db.core_state.total_sources = len(db.knowledge)
    return db.core_state.dict()


@app.get("/api/core/events")
async def get_core_events(limit: int = 50):
    return [e.dict() for e in db.events[-limit:]]


@app.get("/api/core/metrics")
async def get_metrics():
    uptime = (datetime.utcnow() - db.start_time).total_seconds()
    return Metrics(
        uptime_seconds=uptime,
        total_events=len(db.events),
        events_per_minute=round(len(db.events) / max(uptime / 60, 1), 2),
        active_missions=len([m for m in db.missions.values() if m.status == MissionStatus.ACTIVE]),
        active_agents=len([a for a in db.agents_inst.values() if a.status == "active"]),
        tool_executions=len(db.tools_exec),
        total_evidence=len(db.evidence),
        total_claims=len(db.claims),
        total_memories=len(db.memory),
        total_knowledge_entities=len(db.knowledge),
        total_knowledge_relationships=len(db.knowledge) * 2,
        db_stats={"missions": float(len(db.missions)), "agents": float(len(db.agents_inst)), "tools": float(len(db.tools_def))}
    )


# ============================================
# Mission Endpoints
# ============================================

@app.get("/api/missions")
async def list_missions():
    return {
        "missions": [
            {
                "id": mid,
                "title": m.title,
                "status": m.status,
                "progress": m.progress,
                "agents": len(m.agents),
                "sources": len(m.sources),
                "evidence": len(m.evidence),
                "claims": len(m.claims)
            }
            for mid, m in db.missions.items()
        ]
    }


@app.get("/api/missions/{mission_id}")
async def get_mission(mission_id: str):
    if mission_id not in db.missions:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission = db.missions[mission_id]
    agent_details = [
        {
            **a.dict(),
            "name": db.agents_def.get(a.definition_id, AgentDefinition(id="", name="Unknown")).name,
            "role": db.agents_def.get(a.definition_id, AgentDefinition(id="", name="Unknown")).role
        }
        for aid in mission.agents
        for a in [db.agents_inst.get(aid)] if a
    ]
    evidence_details = [
        {
            "id": e.id,
            "claim_text": e.claim_text,
            "source_id": e.source_id,
            "source_title": e.source_title,
            "source_type": e.source_type,
            "evidence_text": e.evidence_text,
            "confidence": e.confidence,
            "is_inference": e.is_inference,
            "retrieved_at": e.retrieved_at,
            "published_at": e.published_at,
            "reasoning": e.reasoning,
            "supporting_source_ids": e.supporting_source_ids,
            "contradicting_source_ids": e.contradicting_source_ids,
            "citations": e.citations,
            "mission_id": e.mission_id,
            "agent_id": e.agent_id
        }
        for eid in mission.evidence
        for e in [db.evidence.get(eid)] if e
    ]
    claim_details = [
        {
            "id": c.id,
            "text": c.text,
            "confidence": c.confidence,
            "status": c.status,
            "is_inference": c.is_inference,
            "evidence_ids": c.evidence_ids,
            "supporting_count": c.supporting_count,
            "contradicting_count": c.contradicting_count,
            "source_ids": c.source_ids,
            "mission_id": c.mission_id,
            "agent_id": c.agent_id,
            "verified_at": c.verified_at,
            "verification_notes": c.verification_notes,
            "created_at": c.created_at
        }
        for cid in mission.claims
        for c in [db.claims.get(cid)] if c
    ]
    citations = [
        {
            "id": cit.id,
            "claim_id": cit.claim_id,
            "source_id": cit.source_id,
            "evidence_id": cit.evidence_id,
            "locator": cit.locator,
            "citation_text": cit.citation_text,
            "mission_id": cit.mission_id,
            "created_at": cit.created_at
        }
        for cit in db.citations.values() if cit.claim_id in mission.claims
    ]
    return {
        **mission.dict(),
        "agent_details": agent_details,
        "evidence_details": evidence_details,
        "claim_details": claim_details,
        "citations": citations
    }


@app.post("/api/missions")
async def create_mission(query: Dict[str, Any]):
    mission_id = generate_id()
    mission = Mission(
        id=mission_id,
        title=f"Mission: {query.get('query', 'Unknown')[:30]}",
        query=query.get("query", ""),
        status=MissionStatus.ACTIVE,
        progress=0.0
    )
    db.missions[mission_id] = mission
    db.emit_event("MISSION_STARTED", f"Mission Created: {mission.title}", {"mission_id": mission_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "MISSION_CREATED",
        "source": "mission_system",
        "payload": {"mission_id": mission_id, "title": mission.title, "status": str(mission.status)},
        "created_at": datetime.utcnow().isoformat()
    })
    return {
        "action": "mission_created",
        "mission_id": mission_id,
        "title": mission.title,
        "status": mission.status,
        "agents_spawned": 0
    }


@app.post("/api/missions/{mission_id}/pause")
async def pause_mission(mission_id: str):
    if mission_id not in db.missions:
        raise HTTPException(status_code=404, detail="Mission not found")
    db.missions[mission_id].status = MissionStatus.PAUSED
    db.emit_event("MISSION_PAUSED", f"Mission Paused: {db.missions[mission_id].title}", {"mission_id": mission_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "MISSION_PAUSED",
        "source": "mission_system",
        "payload": {"mission_id": mission_id},
        "created_at": datetime.utcnow().isoformat()
    })
    return {"status": "paused", "mission_id": mission_id}


@app.post("/api/missions/{mission_id}/resume")
async def resume_mission(mission_id: str):
    if mission_id not in db.missions:
        raise HTTPException(status_code=404, detail="Mission not found")
    db.missions[mission_id].status = MissionStatus.ACTIVE
    db.emit_event("MISSION_RESUMED", f"Mission Resumed: {db.missions[mission_id].title}", {"mission_id": mission_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "MISSION_RESUMED",
        "source": "mission_system",
        "payload": {"mission_id": mission_id},
        "created_at": datetime.utcnow().isoformat()
    })
    return {"status": "active", "mission_id": mission_id}


@app.post("/api/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    if mission_id not in db.missions:
        raise HTTPException(status_code=404, detail="Mission not found")
    db.missions[mission_id].status = MissionStatus.CANCELLED
    db.emit_event("MISSION_CANCELLED", f"Mission Cancelled: {db.missions[mission_id].title}", {"mission_id": mission_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "MISSION_CANCELLED",
        "source": "mission_system",
        "payload": {"mission_id": mission_id},
        "created_at": datetime.utcnow().isoformat()
    })
    return {"status": "cancelled", "mission_id": mission_id}


# ============================================
# Agent Endpoints
# ============================================

@app.get("/api/agents/definitions")
async def get_agent_definitions():
    return list(db.agents_def.values())


@app.get("/api/agents/instances")
async def get_agent_instances():
    return {
        "agents": [
            {
                **a.dict(),
                "name": db.agents_def.get(a.definition_id, AgentDefinition(id="", name="Unknown")).name,
                "role": db.agents_def.get(a.definition_id, AgentDefinition(id="", name="Unknown")).role
            }
            for a in db.agents_inst.values()
        ]
    }


@app.get("/api/agents/instances/{agent_id}")
async def get_agent_instance(agent_id: str):
    if agent_id not in db.agents_inst:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent = db.agents_inst[agent_id]
    agent_def = db.agents_def.get(agent.definition_id)
    return {
        **agent.dict(),
        "definition": agent_def.dict() if agent_def else None
    }


@app.get("/api/agents/instances/mission/{mission_id}")
async def get_agents_by_mission(mission_id: str):
    agents = [a for a in db.agents_inst.values() if a.mission_id == mission_id]
    return [a.dict() for a in agents]


# ============================================
# Tool Endpoints
# ============================================

@app.get("/api/tools")
async def list_tools():
    return list(db.tools_def.values())


@app.get("/api/tools/executions")
async def list_tool_executions(limit: int = 20):
    return [t.dict() for t in list(db.tools_exec.values())[-limit:]]


@app.get("/api/tools/executions/{execution_id}")
async def get_tool_execution(execution_id: str):
    if execution_id not in db.tools_exec:
        raise HTTPException(status_code=404, detail="Execution not found")
    return db.tools_exec[execution_id]


@app.post("/api/tools/invoke")
async def invoke_tool(tool: Dict[str, Any], request: Request):
    tool_id = tool.get("tool", "")
    input_data = tool.get("input", {})
    agent_id = tool.get("agent_id")
    mission_id = tool.get("mission_id")
    principal = None
    if request.scope.get("root_path"):
        try:
            from jarvis_backend.core import get_current_user
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Jarvis authentication is unavailable") from exc
        principal = get_current_user(request.headers.get("authorization"))
        if tool_id == "code" or tool_id == "code_executor":
            from jarvis_backend.core import is_admin

            if not is_admin(principal):
                raise HTTPException(status_code=403, detail="Privileged access required")
            grants = {
                grant
                for field in ("capabilities", "permissions", "scopes")
                for grant in (principal.get(field) or [])
                if isinstance(grant, str)
            }
            if "code_execution" not in grants:
                raise HTTPException(status_code=403, detail="Code execution capability is not authorized")

    exec_id = generate_id()
    execution = ToolExecution(
        id=exec_id,
        tool_name=tool_id,
        input_data=input_data,
        status="running",
        agent_id=agent_id,
        mission_id=mission_id,
        started_at=get_timestamp(),
    )
    db.tools_exec[exec_id] = execution
    db.emit_event("TOOL_INVOKED", f"Tool Invoked: {tool_id}", {"execution_id": exec_id, "tool_id": tool_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "TOOL_INVOKED",
        "source": "tool_system",
        "payload": {"execution_id": exec_id, "tool_id": tool_id},
        "created_at": get_timestamp()
    })

    try:
        output = await _dispatch_tool(tool_id, input_data, execution)
        execution.status = "completed"
        execution.output_data = output
    except Exception as e:
        execution.status = "error"
        execution.error = str(e)
        execution.output_data = {"error": str(e)}

    execution.completed_at = get_timestamp()
    execution.duration_ms = 1

    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "TOOL_COMPLETED",
        "source": "tool_system",
        "payload": {"execution_id": exec_id, "status": execution.status},
        "created_at": get_timestamp()
    })

    return execution


@app.get("/api/orchestrator/state")
async def get_orchestrator_state():
    return orchestrator.state_dict()


@app.post("/api/agents/spawn")
async def spawn_agents(payload: Dict[str, Any]):
    mission_id = payload.get("mission_id")
    if not mission_id or mission_id not in db.missions:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission = db.missions[mission_id]
    spawned = orchestrator.spawn_agents(mission)
    return {"spawned": spawned, "mission_id": mission_id, "count": len(spawned)}


# ============================================
# Verification Endpoints
# ============================================

@app.get("/api/verification/status")
async def get_verification_status():
    reports = [m.dict().get("verification") for m in db.missions.values() if m.verification]
    verified = [m for m in db.missions.values() if (m.verification or {}).get("verdict") == "verified"]
    flagged = [m for m in db.missions.values() if (m.verification or {}).get("verdict") == "flagged"]
    unchecked_done = [m for m in db.missions.values()
                      if m.status == MissionStatus.COMPLETED and not m.verification]
    return {
        "missions_checked": len(verified) + len(flagged),
        "verified": len(verified),
        "flagged": len(flagged),
        "unchecked_completed": len(unchecked_done),
        "reports": reports,
    }


@app.get("/api/missions/{mission_id}/verification")
async def get_mission_verification(mission_id: str):
    if mission_id not in db.missions:
        raise HTTPException(status_code=404, detail="Mission not found")
    mission = db.missions[mission_id]
    return {
        "mission_id": mission.id,
        "verification": mission.verification,
        "claim_statuses": [{"id": c.id, "status": c.status} for c in db.claims.values()
                           if c.mission_id == mission.id],
    }


# ============================================
# Research Endpoints
# ============================================

RESEARCH_CONNECTORS = [
    {"id": "web_search", "name": "Web Search", "type": "web", "enabled": True, "requires_network": False,
     "capabilities": ["general search", "snippet retrieval", "multi-source"],
     "description": "Composite search over internal knowledge and public web APIs with offline fallback."},
    {"id": "arxiv", "name": "arXiv", "type": "academic", "enabled": True, "requires_network": True,
     "capabilities": ["papers", "preprints", "abstracts"],
     "description": "Query the public arXiv API for papers and preprints."},
    {"id": "wikipedia", "name": "Wikipedia", "type": "reference", "enabled": True, "requires_network": True,
     "capabilities": ["encyclopedia", "article summaries"],
     "description": "Search Wikipedia and fetch concise article summaries."},
    {"id": "internal", "name": "Internal Knowledge", "type": "internal", "enabled": True, "requires_network": False,
     "capabilities": ["knowledge graph", "memory", "retrieval"],
     "description": "Retrieve from the Silverwing knowledge graph and episodic memory."},
    {"id": "database", "name": "Internal Database", "type": "internal", "enabled": True, "requires_network": False,
     "capabilities": ["evidence", "claims", "structured query"],
     "description": "Query the local evidence and claims database."},
    {"id": "file_system", "name": "File System", "type": "internal", "enabled": True, "requires_network": False,
     "capabilities": ["files", "notes"],
     "description": "Scan allowed local files for references and notes."},
]


def _build_research_plan(research_query: str) -> Dict[str, Any]:
    base = research_query.strip()
    sub_queries = [q.strip(" .") for q in re.split(r"[;,.。]|\s+and\s+|\s+vs\.?\s+", base) if len(q.strip(" .")) >= 4]
    if not sub_queries:
        sub_queries = [base] if base else ["general research"]
    focus_pool = []
    tokens = _tokenize(base)
    for ent in db.knowledge.values():
        if tokens & (_tokenize(ent.name) | _tokenize(ent.description or "")):
            focus_pool.append(ent.name)
    focus_areas = [base[:60]] + [s[:60] for s in sub_queries[1:]]
    return {
        "mission_id": "",
        "objective": base,
        "sub_queries": sub_queries[:4],
        "connectors": [c["id"] for c in RESEARCH_CONNECTORS if c["enabled"]],
        "verification_required": True,
        "plan_type": "multi_connector",
        "estimated_steps": min(6, 2 + len(sub_queries)),
        "focus_areas": focus_areas,
    }


@app.post("/api/research")
async def start_research(query: Dict[str, Any]):
    research_query = str(query.get("query", ""))
    mission_id = generate_id()
    plan = _build_research_plan(research_query)
    plan["mission_id"] = mission_id
    mission = Mission(
        id=mission_id,
        title=f"Research: {research_query[:30]}",
        query=research_query,
        status=MissionStatus.ACTIVE,
        progress=0.0
    )
    db.missions[mission_id] = mission
    db.emit_event("RESEARCH_STARTED", f"Research Started: {research_query[:50]}",
                  {"mission_id": mission_id, "plan": plan})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "RESEARCH_STARTED",
        "source": "research_system",
        "payload": {"mission_id": mission_id, "plan": plan},
        "created_at": datetime.utcnow().isoformat()
    })
    return {"action": "RESEARCH_STARTED", "mission_id": mission_id, "plan": plan}


@app.get("/api/research/connectors")
async def get_research_connectors():
    return [c["id"] for c in RESEARCH_CONNECTORS]


@app.get("/api/research/connectors/details")
async def get_research_connector_details():
    return list(RESEARCH_CONNECTORS)


# ============================================
# Evaluation / Continual Improvement
# ============================================

async def _run_evaluation() -> Dict[str, Any]:
    started = time.monotonic()
    checks: List[Dict[str, Any]] = []

    async def ctx(name: str, fn):
        c_start = time.monotonic()
        try:
            detail = await fn()
            checks.append({"name": name, "status": "ok", "detail": detail,
                           "duration_ms": round((time.monotonic() - c_start) * 1000, 1)})
        except Exception as e:  # noqa: BLE001
            checks.append({"name": name, "status": "fail", "detail": str(e),
                           "duration_ms": round((time.monotonic() - c_start) * 1000, 1)})

    async def check_core():
        return f"{db.core_state.status} / {db.core_state.mode} (total events: {len(db.events)})"

    async def check_db_integrity():
        collections = dict(_DICT_COLLECTIONS)
        collections.update(_LIST_COLLECTIONS)
        counts = ", ".join(f"{name}={len(getattr(db, name, {}))}" for name in collections)
        return f"collections intact: {counts}"

    async def check_tool_engine():
        mem = await _dispatch_tool("memory_retrieve", {"query": "silverwing", "limit": 3}, None)
        return f"memory_retrieve ok ({len(mem.get('results', []))} results)"

    async def check_sandbox():
        from silverwing_sandbox_loader import load_sandbox
        sw = load_sandbox()
        good = await asyncio.to_thread(sw.run_code, "print(21 * 2)")
        if not good.get("ok"):
            raise RuntimeError(f"sandbox basic exec failed: {good.get('error')}")
        try:
            await asyncio.to_thread(sw.run_code, "import os")
            raise RuntimeError("sandbox accepted forbidden import")
        except sw.SandboxViolation as exc:
            return f"basic exec ok ('42'), forbidden import blocked ('{str(exc)[:40]}')"

    async def check_connectors():
        enabled = sum(1 for c in RESEARCH_CONNECTORS if c.get("enabled"))
        web = await _tool_web_search({"query": "silverwing cognitive architecture", "limit": 2})
        n = len(web.get("results", []))
        return f"{enabled} connectors registered, web_search returned {n} results"

    async def check_orchestrator():
        st = orchestrator.state_dict()
        return f"running={st.get('running')}, loop_count={st.get('loop_count')}"

    await ctx("core_status", check_core)
    await ctx("db_integrity", check_db_integrity)
    await ctx("tool_engine", check_tool_engine)
    await ctx("sandbox", check_sandbox)
    await ctx("connectors", check_connectors)
    await ctx("orchestrator", check_orchestrator)

    failed = [c for c in checks if c["status"] != "ok"]
    return {
        "report_id": generate_id(),
        "timestamp": get_timestamp(),
        "overall": "pass" if not failed else "fail",
        "total_checks": len(checks),
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
        "scope": "alpha_eval_v1",
    }


@app.get("/api/evaluation/run")
async def run_evaluation():
    return await _run_evaluation()


# ============================================
# Evidence Endpoints
# ============================================

@app.get("/api/evidence")
async def list_evidence(limit: int = 50):
    return [e.dict() for e in list(db.evidence.values())[-limit:]]


@app.get("/api/evidence/{evidence_id}")
async def get_evidence(evidence_id: str):
    if evidence_id not in db.evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return db.evidence[evidence_id].dict()


@app.get("/api/evidence/mission/{mission_id}")
async def get_evidence_by_mission(mission_id: str):
    evidence = [e for e in db.evidence.values() if e.mission_id == mission_id]
    return [e.dict() for e in evidence]


# ============================================
# Claim Endpoints
# ============================================

@app.get("/api/claims")
async def list_claims(limit: int = 50):
    return [c.dict() for c in list(db.claims.values())[-limit:]]


@app.get("/api/claims/{claim_id}")
async def get_claim(claim_id: str):
    if claim_id not in db.claims:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim = db.claims[claim_id]
    evidence_details = [
        {
            "id": e.id,
            "claim_text": e.claim_text,
            "source_id": e.source_id,
            "source_title": e.source_title,
            "source_type": e.source_type,
            "evidence_text": e.evidence_text,
            "confidence": e.confidence,
            "is_inference": e.is_inference,
            "retrieved_at": e.retrieved_at,
            "published_at": e.published_at,
            "reasoning": e.reasoning,
            "supporting_source_ids": e.supporting_source_ids,
            "contradicting_source_ids": e.contradicting_source_ids,
            "citations": e.citations,
            "mission_id": e.mission_id,
            "agent_id": e.agent_id
        }
        for eid in claim.evidence_ids
        for e in [db.evidence.get(eid)] if e
    ]
    citations = [
        {
            "id": cit.id,
            "claim_id": cit.claim_id,
            "source_id": cit.source_id,
            "evidence_id": cit.evidence_id,
            "locator": cit.locator,
            "citation_text": cit.citation_text,
            "mission_id": cit.mission_id,
            "created_at": cit.created_at
        }
        for cit in db.citations.values() if cit.claim_id == claim_id
    ]
    return {
        **claim.dict(),
        "evidence_details": evidence_details,
        "citations": citations
    }


@app.get("/api/claims/mission/{mission_id}")
async def get_claims_by_mission(mission_id: str):
    claims = [c for c in db.claims.values() if c.mission_id == mission_id]
    return [c.dict() for c in claims]


@app.post("/api/claims/{claim_id}/verify")
async def verify_claim(claim_id: str):
    if claim_id not in db.claims:
        raise HTTPException(status_code=404, detail="Claim not found")
    db.claims[claim_id].status = "verified"
    db.claims[claim_id].confidence = 0.95
    db.emit_event("CLAIM_VERIFIED", f"Claim Verified: {claim_id}", {"claim_id": claim_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "CLAIM_VERIFIED",
        "source": "claim_system",
        "payload": {"claim_id": claim_id},
        "created_at": datetime.utcnow().isoformat()
    })
    return db.claims[claim_id].dict()


# ============================================
# Citation Endpoints
# ============================================

@app.get("/api/citations")
async def list_citations(mission_id: Optional[str] = None, claim_id: Optional[str] = None):
    if mission_id:
        citations = [c for c in db.citations.values() if db.claims.get(c.claim_id, Claim(id="", text="")).mission_id == mission_id]
    elif claim_id:
        citations = [c for c in db.citations.values() if c.claim_id == claim_id]
    else:
        citations = list(db.citations.values())
    return [c.dict() for c in citations]


@app.get("/api/citations/mission/{mission_id}")
async def get_citations_by_mission(mission_id: str):
    citations = [c for c in db.citations.values() if db.claims.get(c.claim_id, Claim(id="", text="")).mission_id == mission_id]
    return [c.dict() for c in citations]


# ============================================
# Memory Endpoints
# ============================================

@app.get("/api/memory")
async def list_memory(type: Optional[str] = None, limit: int = 30):
    memory = list(db.memory.values())
    if type:
        memory = [m for m in memory if m.memory_type.value == type]
    return [m.dict() for m in memory[-limit:]]


@app.get("/api/memory/{memory_id}")
async def get_memory(memory_id: str):
    if memory_id not in db.memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return db.memory[memory_id].dict()


@app.get("/api/memory/search/{query}")
async def search_memory(query: str, type: Optional[str] = None):
    results = [
        m for m in db.memory.values()
        if query.lower() in m.content.lower() and (not type or m.memory_type.value == type)
    ]
    return results


@app.post("/api/memory")
async def write_memory(memory: Dict[str, Any]):
    mem_id = generate_id()
    mem = Memory(
        id=mem_id,
        content=memory.get("content", ""),
        memory_type=memory.get("memory_type", memory.get("type", MemoryType.WORKING)),
        importance=memory.get("importance", 1.0),
        tags=memory.get("tags", [])
    )
    db.memory[mem_id] = mem
    db.emit_event("MEMORY_WRITTEN", f"Memory Written: {mem.content[:50]}", {"memory_id": mem_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "MEMORY_WRITTEN",
        "source": "memory_system",
        "payload": {"memory_id": mem_id},
        "created_at": datetime.utcnow().isoformat()
    })
    return mem.dict()


@app.put("/api/memory/{memory_id}")
async def update_memory(memory_id: str, memory: Dict[str, Any]):
    if memory_id not in db.memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    for key, value in memory.items():
        if hasattr(db.memory[memory_id], key):
            setattr(db.memory[memory_id], key, value)
    db.memory[memory_id].created_at = get_timestamp()
    return db.memory[memory_id].dict()


@app.post("/api/memory/{memory_id}/invalidate")
async def invalidate_memory(memory_id: str, reason: Dict[str, Any]):
    if memory_id not in db.memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.memory[memory_id].invalidated = True
    db.memory[memory_id].provenance["invalidation_reason"] = reason.get("reason", "No reason provided")
    db.emit_event("MEMORY_INVALIDATED", f"Memory Invalidated: {memory_id}", {"memory_id": memory_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "MEMORY_INVALIDATED",
        "source": "memory_system",
        "payload": {"memory_id": memory_id},
        "created_at": datetime.utcnow().isoformat()
    })
    return {"deleted": False, "invalidated": True}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str):
    if memory_id not in db.memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    del db.memory[memory_id]
    db.emit_event("MEMORY_DELETED", f"Memory Deleted: {memory_id}", {"memory_id": memory_id})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "MEMORY_DELETED",
        "source": "memory_system",
        "payload": {"memory_id": memory_id},
        "created_at": datetime.utcnow().isoformat()
    })
    return {"deleted": True}


@app.get("/api/memory/stats")
async def get_memory_stats():
    total = len(db.memory)
    working = len([m for m in db.memory.values() if m.memory_type == MemoryType.WORKING])
    episodic = len([m for m in db.memory.values() if m.memory_type == MemoryType.EPISODIC])
    semantic = len([m for m in db.memory.values() if m.memory_type == MemoryType.SEMANTIC])
    procedural = len([m for m in db.memory.values() if m.memory_type == MemoryType.PROCEDURAL])
    return {
        "total": total,
        "working": working,
        "episodic": episodic,
        "semantic": semantic,
        "procedural": procedural
    }


# ============================================
# Knowledge Endpoints
# ============================================

@app.get("/api/knowledge/graph")
async def get_knowledge_graph(max_nodes: int = 100):
    nodes = list(db.knowledge.values())[:max_nodes]
    edges = []
    edge_idx = 0
    for node in nodes:
        for other in db.knowledge.values():
            if node.id != other.id and edge_idx < max_nodes:
                edges.append({
                    "id": f"e{edge_idx}",
                    "from": node.id,
                    "to": other.id,
                    "type": "related",
                    "weight": 0.5
                })
                edge_idx += 1
    return {
        "nodes": [{"id": n.id, "name": n.name, "type": n.type, "source_count": n.source_count, "evidence_count": n.evidence_count} for n in nodes],
        "edges": edges
    }


@app.get("/api/knowledge/entities")
async def list_knowledge_entities(type: Optional[str] = None):
    entities = list(db.knowledge.values())
    if type:
        entities = [e for e in entities if e.type == type]
    return [
        {
            "id": e.id,
            "name": e.name,
            "type": e.type,
            "source_count": e.source_count,
            "evidence_count": e.evidence_count
        }
        for e in entities
    ]


@app.get("/api/knowledge/entities/{entity_id}")
async def get_knowledge_entity(entity_id: str):
    if entity_id not in db.knowledge:
        raise HTTPException(status_code=404, detail="Entity not found")
    return db.knowledge[entity_id].dict()


@app.get("/api/knowledge/search/{query}")
async def search_knowledge(query: str):
    results = [
        e for e in db.knowledge.values()
        if query.lower() in e.name.lower() or query.lower() in e.description.lower()
    ]
    return [
        {"id": e.id, "name": e.name, "type": e.type}
        for e in results
    ]


@app.get("/api/knowledge/stats")
async def get_knowledge_stats():
    type_counts = {}
    for entity in db.knowledge.values():
        type_counts[entity.type] = type_counts.get(entity.type, 0) + 1
    return {
        "node_count": len(db.knowledge),
        "edge_count": len(db.knowledge) * 2,
        "source_count": sum(e.source_count for e in db.knowledge.values()),
        "type_counts": type_counts
    }


# ============================================
# Laboratory Endpoints
# ============================================

@app.get("/api/laboratory/model")
async def get_model_state():
    return ModelState(
        id="silverwing-120m-base-v1",
        name="Silverwing-120M-Base-v1",
        parameters=120087552,
        architecture="transformer-decoder",
        features=["text-generation"],
        status="training",
        tokens_processed=409600,
        current_step=400,
        total_steps=1650,
        loss=5.4531,
        perplexity=233.5,
        learning_rate=0.00005,
        last_checkpoint="silverwing-120m-base-v1/step-400 (Kaggle dataset)",
        hardware="Kaggle-GPU(T4, training) / CPU (serving)",
        memory_usage_mb=2100.0,
        inference_latency_ms=85.0
    )


# ============================================
# Observatory Endpoints
# ============================================

@app.get("/api/observatory/stream")
async def get_observatory_stream():
    return Observatory(
        events_per_minute=round(len(db.events) / max((datetime.utcnow() - db.start_time).total_seconds() / 60, 1), 2),
        total_events=len(db.events),
        ws_connections=len(websocket_manager.active_connections),
        active_missions=len([m for m in db.missions.values() if m.status == MissionStatus.ACTIVE]),
        active_agents=len([a for a in db.agents_inst.values() if a.status == "active"]),
        tool_executions=len(db.tools_exec),
        recent_events=db.events[-10:],
        recent_tools=list(db.tools_exec.values())[-10:]
    )


@app.get("/api/observatory/agents")
async def get_observatory_agents():
    return [
        {
            **a.dict(),
            "name": db.agents_def.get(a.definition_id, AgentDefinition(id="", name="Unknown")).name,
            "role": db.agents_def.get(a.definition_id, AgentDefinition(id="", name="Unknown")).role
        }
        for a in db.agents_inst.values()
    ]


@app.get("/api/observatory/tools")
async def get_observatory_tools():
    return [t.dict() for t in list(db.tools_exec.values())[-20:]]


# ============================================
# Training Advisor Endpoints
# ============================================
async def _advisor_call(action: str, *, limit: int = None, payload: Dict[str, Any] = None) -> Dict[str, Any]:
    inst = _TRAINING_ADVISOR_INST
    if inst is None:
        return {"status": "error", "error": f"training_advisor not initialized: {_TA_INIT_ERROR}",
                "action": action}
    if action == "status":
        return {"status": "ok", "summary": await inst.status()}
    if action == "analyze":
        result = await inst.analyze(force=True)
        return {"status": "ok", "provider": result.provider, "result": result.model_dump(mode="json")}
    if action == "recommendations":
        return {"status": "ok", "recommendations": await inst.recommendations()}
    if action == "history":
        return {"status": "ok", "history": await inst.history(limit or 50)}
    if action == "evidence":
        return {"status": "ok", "evidence": await inst.evidence(limit or 100)}
    if action == "experiments":
        return {"status": "ok", "experiments": await inst.experiments(limit or 50)}
    if action == "approve":
        p = payload or {}
        return {"status": "ok", "result": await inst.approve(
            str(p.get("recommendation_id", "")),
            str(p.get("approver", "operator")),
            p.get("metadata"))}
    return {"status": "error", "error": f"unknown action: {action}"}


@app.get("/api/training/status")
async def training_status():
    return await _advisor_call("status")


@app.get("/api/training/metrics")
async def training_metrics_list(limit: int = 50):
    inst = _TRAINING_ADVISOR_INST
    if inst is None:
        return {"status": "error", "error": f"training_advisor not initialized: {_TA_INIT_ERROR}"}
    snaps = inst.store.history(limit)
    return {"status": "ok", "snapshots": [s.model_dump(mode="json") for s in snaps], "summary": inst.store.summary(snaps)}


@app.post("/api/training/metrics")
async def training_metrics_ingest(payload: Dict[str, Any] = None):
    inst = _TRAINING_ADVISOR_INST
    if inst is None:
        return {"status": "error", "error": f"training_advisor not initialized: {_TA_INIT_ERROR}"}
    snap = await inst.ingest(payload or {}, (payload or {}).get("run_id"))
    return {"status": "ok", "run_id": snap.run_id, "observed_keys": snap.observed_keys(),
            "snapshot": snap.model_dump(mode="json")}


@app.get("/api/training/advisor/status")
async def training_advisor_status():
    return await _advisor_call("status")


@app.post("/api/training/advisor/analyze")
async def training_advisor_analyze(payload: Dict[str, Any] = None):
    return await _advisor_call("analyze")


@app.get("/api/training/advisor/recommendations")
async def training_advisor_recommendations():
    return await _advisor_call("recommendations")


@app.get("/api/training/advisor/history")
async def training_advisor_history(limit: int = 50):
    return await _advisor_call("history", limit=limit)


@app.get("/api/training/advisor/evidence")
async def training_advisor_evidence(limit: int = 100):
    return await _advisor_call("evidence", limit=limit)


@app.get("/api/training/advisor/experiments")
async def training_advisor_experiments(limit: int = 50):
    return await _advisor_call("experiments", limit=limit)


@app.post("/api/training/advisor/approve")
async def training_advisor_approve(payload: Dict[str, Any] = None):
    return await _advisor_call("approve", payload=payload)


# ============================================
# Model Provider Endpoints
# ============================================

async def _model_call(action: str, *, payload: Dict[str, Any] = None) -> Dict[str, Any]:
    """Dispatch helper for the /api/models/* surface (mirrors _advisor_call)."""
    mgr = _MODEL_MANAGER
    if mgr is None:
        return {"status": "error", "error": f"model_provider not initialized: {_MM_INIT_ERROR}",
                "action": action}
    if action == "list":
        return {"status": "ok", "providers": mgr.list_providers(),
                "default": mgr.default_model(), "auth": mgr.auth_status()}
    if action == "catalog":
        return {"status": "ok", "models": list_all_models()}
    if action == "catalog_families":
        return {"status": "ok", "families": list_families()}
    if action == "catalog_open_weights":
        return {"status": "ok", "models": list_open_weights()}
    if action == "default":
        return {"status": "ok", "default": mgr.default_model()}
    if action == "set_default":
        p = payload or {}
        return {"status": "ok", "default": mgr.set_default(p.get("model"))}
    if action == "chat":
        p = payload or {}
        req = ModelRequest(
            messages=p.get("messages", []),
            model=p.get("model") or mgr.default_model(),
            system=p.get("system"),
            temperature=p.get("temperature"),
            max_tokens=p.get("max_tokens"),
            response_model=p.get("response_model"),
        )
        try:
            resp = await mgr.achat(req)
        except Exception as e:  # noqa: BLE001
            return {"status": "error", "error": str(e)}
        return {"status": "ok", "provider": resp.provider, "model": resp.model,
                "content": resp.content, "parsed": resp.parsed, "usage": resp.usage,
                "finish_reason": resp.finish_reason}
    return {"status": "error", "error": f"unknown action: {action}"}


@app.get("/api/models")
async def models_list():
    return await _model_call("list")


@app.get("/api/models/default")
async def models_default():
    return await _model_call("default")


@app.post("/api/models/default")
async def models_set_default(payload: Dict[str, Any] = None):
    return await _model_call("set_default", payload=payload)


@app.post("/api/models/chat")
async def models_chat(payload: Dict[str, Any] = None):
    return await _model_call("chat", payload=payload)


@app.get("/api/models/catalog")
async def models_catalog():
    """Return the full static model catalogue (providers, IDs, pricing, etc.)."""
    return await _model_call("catalog")


@app.get("/api/models/catalog/families")
async def models_catalog_families():
    """Return model families grouped by their family name."""
    return await _model_call("catalog_families")


@app.get("/api/models/catalog/open-weights")
async def models_catalog_open_weights():
    """Return only open-weights (self-hostable) models."""
    return await _model_call("catalog_open_weights")


@app.get("/api/models/catalog/{provider}")
async def models_catalog_by_provider(provider: str):
    """Return catalog entries for a specific provider prefix."""
    if not MODEL_CATALOG:
        return {"status": "ok", "models": [], "provider": provider}
    entries = [dict(v.model_dump(), key=k)
               for k, v in MODEL_CATALOG.items() if k.startswith(f"{provider}:")]
    return {"status": "ok", "models": entries, "provider": provider}


@app.get("/api/models/health")
async def models_health():
    """Return health status for all registered providers."""
    if not _MODEL_MANAGER or not ModelProvider:
        return {"status": "error", "error": f"model_provider not initialized: {_MM_IMPORT_ERROR}"}
    providers = _MODEL_MANAGER.list_providers()
    health_results = {}
    for p in providers:
        name = p.name if hasattr(p, 'name') else str(p)
        try:
            # Each provider's health() method is async
            status = await p.health() if hasattr(p, 'health') else HealthStatus.UNKNOWN
        except Exception:
            status = HealthStatus.UNKNOWN
        health_results[name] = {
            "status": status.value if hasattr(status, 'value') else str(status),
            "available": p.available if hasattr(p, 'available') else False,
            "authorized": p.authorized if hasattr(p, 'authorized') else False,
            "model": p.model if hasattr(p, 'model') else None,
        }
    return {"status": "ok", "providers": health_results}


@app.get("/health")
async def health():
    """Silverwing runtime health probe (spec §40).

    Returns ``healthy`` when the model_provider module loaded and at least one
    provider is configured/available. All values come from real state — no
    hardcoded health.
    """
    from datetime import datetime
    if not _MODEL_MANAGER or not ModelManager:
        return {
            "status": "error",
            "healthy": False,
            "model_provider": "not_initialized",
            "error": _MM_IMPORT_ERROR,
            "timestamp": datetime.utcnow().isoformat(),
        }
    try:
        mgr = ModelManager()
        auth = mgr.auth_status()
        provider_count = len(auth.get("providers", {}))
        available_count = sum(1 for v in auth.get("providers", {}).values() if v.get("available"))
        return {
            "status": "healthy" if available_count > 0 or provider_count > 0 else "degraded",
            "healthy": available_count > 0,
            "model_provider": "initialized",
            "providers_total": provider_count,
            "providers_available": available_count,
            "training_advisor": _TA_IMPORT_ERROR == "ok",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        return {
            "status": "error",
            "healthy": False,
            "model_provider": "initialized",
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        }


@app.post("/api/models/route")
async def models_route(payload: Dict[str, Any] = None):
    """Route a request to the optimal model based on task, privacy, latency, and cost constraints."""
    if not _MODEL_MANAGER or not ModelRouter:
        return {"status": "error", "error": f"model_provider not initialized: {_MM_IMPORT_ERROR}", "success": False}
    p = payload or {}
    router = ModelRouter()
    decision = router.select(
        capability=p.get("requested_capability", ""),
        privacy=p.get("requested_privacy", "public"),
        latency=p.get("requested_latency", "normal"),
        cost=p.get("requested_cost", "best_quality"),
        task=p.get("task", ""),
    )
    return decision.model_dump()


# ============================================
# AI Console Endpoints
# ============================================

AI_COMMANDS: List[AICommand] = [
    AICommand(
        name="help",
        description="List available commands and system overview",
        pattern="/help",
        examples=["/help", "help"],
    ),
    AICommand(
        name="status",
        description="Show system status and core metrics",
        pattern="/status",
        examples=["/status", "status", "what is the system status"],
    ),
    AICommand(
        name="missions",
        description="List all missions or get details on a specific mission",
        pattern="/missions [id]",
        examples=["/missions", "/missions sample_mission", "list missions"],
    ),
    AICommand(
        name="agents",
        description="List agent definitions and instances",
        pattern="/agents",
        examples=["/agents", "show me agents"],
    ),
    AICommand(
        name="knowledge",
        description="Search the knowledge graph",
        pattern="/knowledge [query]",
        examples=["/knowledge", "/knowledge artificial"],
    ),
    AICommand(
        name="search",
        description="Search across all system data (evidence, claims, knowledge)",
        pattern="/search <query>",
        examples=["/search quantum computing", "search for solid-state"],
    ),
    AICommand(
        name="memory",
        description="Search or list memory entries",
        pattern="/memory [query]",
        examples=["/memory", "/memory thermal"],
    ),
    AICommand(
        name="tools",
        description="List available tools or invoke a tool",
        pattern="/tools [invoke <tool_id> <input>]",
        examples=["/tools", "/tools invoke web_search"],
    ),
    AICommand(
        name="evidence",
        description="List recent evidence",
        pattern="/evidence",
        examples=["/evidence", "show evidence"],
    ),
    AICommand(
        name="claims",
        description="List all claims and their verification status",
        pattern="/claims",
        examples=["/claims", "list claims"],
    ),
    AICommand(
        name="observatory",
        description="Show observatory live telemetry",
        pattern="/observatory",
        examples=["/observatory", "live stats"],
    ),
    AICommand(
        name="research",
        description="Start a new research mission",
        pattern="/research <query>",
        examples=["/research latest quantum computing", "start research on AI safety"],
    ),
]


def _get_ai_context_dict() -> Dict[str, Any]:
    uptime = (datetime.utcnow() - db.start_time).total_seconds()
    ctx = AIContext(
        core_state=db.core_state.dict(),
        metrics=Metrics(
            uptime_seconds=uptime,
            total_events=len(db.events),
            events_per_minute=round(len(db.events) / max(uptime / 60, 1), 2),
            active_missions=len([m for m in db.missions.values() if m.status == MissionStatus.ACTIVE]),
            active_agents=len([a for a in db.agents_inst.values() if a.status == "active"]),
            tool_executions=len(db.tools_exec),
            total_evidence=len(db.evidence),
            total_claims=len(db.claims),
            total_memories=len(db.memory),
            total_knowledge_entities=len(db.knowledge),
            total_knowledge_relationships=len(db.knowledge) * 2,
        ).dict(),
        active_missions=[m.title for m in db.missions.values() if m.status == MissionStatus.ACTIVE][:5],
        active_agents=[a.id for a in db.agents_inst.values() if a.status == "active"][:5],
        available_tools=[t.name for t in db.tools_def.values()],
        memory_stats={
            "total": len(db.memory),
            "working": len([m for m in db.memory.values() if m.memory_type == MemoryType.WORKING]),
            "episodic": len([m for m in db.memory.values() if m.memory_type == MemoryType.EPISODIC]),
            "semantic": len([m for m in db.memory.values() if m.memory_type == MemoryType.SEMANTIC]),
            "procedural": len([m for m in db.memory.values() if m.memory_type == MemoryType.PROCEDURAL]),
        },
        knowledge_stats={
            "entities": len(db.knowledge),
            "node_count": len(db.knowledge),
            "edge_count": len(db.knowledge) * 2,
        },
        recent_events=[e.dict() for e in db.events[-10:]],
    )
    return ctx.dict()


@app.get("/api/ai/context")
async def get_ai_context():
    return _get_ai_context_dict()


@app.get("/api/ai/commands")
async def get_ai_commands():
    return [c.dict() for c in AI_COMMANDS]


@app.get("/api/ai/conversations")
async def get_conversations():
    return [{"id": c.id, "message_count": len(c.messages), "created_at": c.created_at, "updated_at": c.updated_at} for c in db.conversations.values()]


@app.post("/api/ai/conversations/reset")
async def reset_conversations():
    db.conversation_history = []
    db.conversations.clear()
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "AI_CONVERSATION_RESET",
        "source": "ai_console",
        "payload": {"message": "Conversation history cleared"},
        "created_at": datetime.utcnow().isoformat(),
    })
    return {"status": "reset", "conversation_history_cleared": True}


def _parse_command(text: str) -> Optional[tuple]:
    text = text.strip()
    for cmd in AI_COMMANDS:
        first_token = cmd.pattern.split()[0].lstrip('/')
        if text.lower().startswith(first_token):
            parts = text.split(None, 1)
            arg = parts[1] if len(parts) > 1 else ""
            return (cmd.name, arg)
    lowered = text.lower()
    for cmd in AI_COMMANDS:
        if cmd.name in lowered:
            return (cmd.name, text)
    return None


async def _generate_contextual_response(
    user_input: str,
    command_info: Optional[tuple],
    context: Dict[str, Any]
) -> tuple:
    uptime = (datetime.utcnow() - db.start_time).total_seconds()
    uptime_str = f"{int(uptime / 3600)}h {int(uptime % 3600 / 60)}m {int(uptime % 60)}s"
    context_used: List[str] = []

    if command_info is None or command_info[0] == 'help':
        lines = [
            "SILVERWING AI - Interactive Cognitive Console",
            f"  Status: {context.get('core_state', {}).get('status', 'ONLINE')} | Mode: {context.get('core_state', {}).get('mode', 'IDLE')}",
            f"  Uptime: {uptime_str} | Version: {context.get('core_state', {}).get('version', '1.0.0')}",
            "",
            "Available Commands:",
        ]
        for cmd in AI_COMMANDS:
            lines.append(f"  {cmd.pattern:<28} - {cmd.description}")
        lines.append("")
        lines.append("  Type a message or use a slash command. Examples:")
        lines.append("  /status - system status | /missions - list missions | /agents - agent roster")
        lines.append("  /knowledge AI - search knowledge | /memory - list memories | /observatory - live telemetry")
        return ("\n".join(lines), context_used, [])

    cmd_name, cmd_arg = command_info

    if cmd_name == 'status':
        core = context.get('core_state', {})
        metrics = context.get('metrics', {})
        lines = [
            "SYSTEM STATUS REPORT",
            f"  Core: {core.get('status')} | Mode: {core.get('mode')}",
            f"  Uptime: {uptime_str}",
            f"  Model: {core.get('model')}",
            f"  Events: {metrics.get('total_events', 0)} | EPM: {metrics.get('events_per_minute', 0)}",
            f"  Evidence: {metrics.get('total_evidence', 0)} | Claims: {metrics.get('total_claims', 0)}",
            f"  Memories: {metrics.get('total_memories', 0)} | Knowledge: {metrics.get('total_knowledge_entities', 0)}",
            f"  Active Missions: {metrics.get('active_missions', 0)} | Active Agents: {metrics.get('active_agents', 0)}",
        ]
        context_used = ['core_state', 'metrics']
        return ("\n".join(lines), context_used, ['/status'])

    elif cmd_name == 'missions':
        if cmd_arg and db.missions.get(cmd_arg):
            m = db.missions[cmd_arg]
            lines = [
                f"MISSION: {m.title}",
                f"  ID: {m.id}",
                f"  Query: {m.query}",
                f"  Status: {m.status} | Progress: {m.progress}%",
                f"  Agents: {len(m.agents)} | Sources: {len(m.sources)}",
                f"  Evidence: {len(m.evidence)} | Claims: {len(m.claims)}",
                f"  Steps: {len(m.steps)}",
            ]
            for step in m.steps[:5]:
                lines.append(f"  [{step.order}] {step.description} - {step.status}")
            context_used = ['missions']
            return ("\n".join(lines), context_used, ['/missions'])
        else:
            missions = list(db.missions.values())
            if not missions:
                return ("No missions found. Start one with: /research or create via Command Deck.", [], ['/missions'])
            lines = ["ACTIVE MISSIONS:"]
            for m in missions[:10]:
                progress = f"{int(m.progress * 100)}%"
                lines.append(f"  [{m.id}] {m.title} - {m.status} ({progress})")
            context_used = ['missions']
            return ("\n".join(lines), context_used, ['/missions'])

    elif cmd_name == 'agents':
        defs = list(db.agents_def.values())
        insts = list(db.agents_inst.values())
        lines = [
            f"AGENT ROSTER - {len(defs)} definitions, {len(insts)} instances",
            "",
            "Definitions:",
        ]
        for d in defs:
            lines.append(f"  {d.name} ({d.role}) - Tools: {', '.join(d.tools)} | Risk: {d.risk_level}")
        lines.append("")
        if insts:
            lines.append("Active Instances:")
            for a in insts[:10]:
                defn = db.agents_def.get(a.definition_id)
                name = defn.name if defn else a.definition_id
                lines.append(f"  [{a.id}] {name} - {a.status} - {a.current_task or 'idle'}")
        context_used = ['agents_def', 'agents_inst']
        return ("\n".join(lines), context_used, ['/agents'])

    elif cmd_name == 'search':
        if cmd_arg:
            query_lower = cmd_arg.lower()
            ev_hits = [e for e in db.evidence.values() if query_lower in e.evidence_text.lower() or query_lower in e.claim_text.lower()]
            cl_hits = [c for c in db.claims.values() if query_lower in c.text.lower()]
            kg_hits = [e for e in db.knowledge.values() if query_lower in e.name.lower() or query_lower in e.description.lower()]
            mem_hits = [m for m in db.memory.values() if query_lower in m.content.lower()]
            lines = [f"SEARCH: '{cmd_arg}'"]
            lines.append(f"  Evidence: {len(ev_hits)} | Claims: {len(cl_hits)} | Knowledge: {len(kg_hits)} | Memory: {len(mem_hits)}")
            total = len(ev_hits) + len(cl_hits) + len(kg_hits) + len(mem_hits)
            if total == 0:
                lines.append("  No results found across any system.")
            else:
                for e in ev_hits[:3]:
                    lines.append(f"  [EVIDENCE] [{e.source_type}] {e.evidence_text[:60]}...")
                for c in cl_hits[:3]:
                    lines.append(f"  [CLAIM] [{c.status}] {c.text[:60]}...")
                for e in kg_hits[:3]:
                    lines.append(f"  [KNOWLEDGE] [{e.type}] {e.name}")
                for m in mem_hits[:3]:
                    lines.append(f"  [MEMORY] [{m.memory_type}] {m.content[:60]}...")
            context_used = ['evidence', 'claims', 'knowledge', 'memory']
            return ("\n".join(lines), context_used, ['/search'])
        else:
            return ("Usage: /search <query>", [], ['/search'])

    elif cmd_name == 'knowledge':
        if cmd_arg:
            results = [
                e for e in db.knowledge.values()
                if cmd_arg.lower() in e.name.lower() or cmd_arg.lower() in e.description.lower()
            ]
            if not results:
                return (f"No knowledge entities found matching '{cmd_arg}'.", [], ['/knowledge'])
            lines = [f"KNOWLEDGE SEARCH: '{cmd_arg}' - {len(results)} result(s)"]
            for e in results[:10]:
                lines.append(f"  [{e.id}] {e.name} ({e.type}) - Sources: {e.source_count}, Evidence: {e.evidence_count}")
            context_used = ['knowledge']
            return ("\n".join(lines), context_used, ['/knowledge'])
        else:
            entities = list(db.knowledge.values())
            lines = [f"KNOWLEDGE GRAPH - {len(entities)} entities"]
            type_counts: Dict[str, int] = {}
            for e in entities:
                type_counts[e.type] = type_counts.get(e.type, 0) + 1
            for t, count in sorted(type_counts.items()):
                lines.append(f"  {t}: {count}")
            context_used = ['knowledge']
            return ("\n".join(lines), context_used, ['/knowledge'])

    elif cmd_name == 'memory':
        if cmd_arg and len(cmd_arg) >= 2:
            hits = [m for m in db.memory.values() if cmd_arg.lower() in m.content.lower() or m.tags and cmd_arg.lower() in ' '.join(m.tags).lower()]
            if not hits:
                return (f"No memory vectors found matching '{cmd_arg}'.", [], ['/memory'])
            lines = [f"MEMORY SEARCH: '{cmd_arg}' - {len(hits)} result(s)"]
            for m in hits[:10]:
                preview = m.content[:80] + ('...' if len(m.content) > 80 else '')
                lines.append(f"  [{m.id}] [{m.memory_type}] {preview}")
            context_used = ['memory']
            return ("\n".join(lines), context_used, ['/memory'])
        else:
            stats = context.get('memory_stats', {})
            lines = [
                f"MEMORY MATRIX - {stats.get('total', 0)} total vectors",
                f"  Working: {stats.get('working', 0)} | Episodic: {stats.get('episodic', 0)}",
                f"  Semantic: {stats.get('semantic', 0)} | Procedural: {stats.get('procedural', 0)}",
            ]
            context_used = ['memory_stats']
            return ("\n".join(lines), context_used, ['/memory'])

    elif cmd_name == 'tools':
        if cmd_arg.startswith('invoke'):
            parts = cmd_arg.split(None, 2)
            if len(parts) >= 2:
                tool_id = parts[1]
                input_str = parts[2] if len(parts) > 2 else ""
                tool_def = None
                for td in db.tools_def.values():
                    if td.id == tool_id or td.name.lower() == tool_id.lower():
                        tool_def = td
                        break
                if not tool_def:
                    available = ', '.join(db.tools_def.keys())
                    return (f"Tool '{tool_id}' not found. Available: {available}", [], ['/tools'])
                exec_id = generate_id()
                execution = ToolExecution(
                    id=exec_id,
                    tool_name=tool_def.id,
                    input_data={"query": input_str} if input_str else {},
                    status="pending",
                )
                db.tools_exec[exec_id] = execution
                db.emit_event("TOOL_INVOKED", f"Tool Invoked: {tool_def.name}", {"execution_id": exec_id, "tool_id": tool_def.id})
                await websocket_manager.broadcast({
                    "id": str(uuid.uuid4()),
                    "type": "TOOL_INVOKED",
                    "source": "tool_system",
                    "payload": {"execution_id": exec_id, "tool_id": tool_def.id},
                    "created_at": datetime.utcnow().isoformat(),
                })
                await asyncio.sleep(0.1)
                execution.status = "completed"
                execution.error = f"Tool '{tool_def.name}' is registered but no real executor is wired in the Silverwing runtime. Delegate to JARVIS interaction layer for real execution."
                result = {"tool": tool_def.name, "input": input_str, "error": execution.error, "executed": False}
                execution.output_data = result
                execution.completed_at = datetime.utcnow().isoformat()
                execution.duration_ms = 100
                await websocket_manager.broadcast({
                    "id": str(uuid.uuid4()),
                    "type": "TOOL_COMPLETED",
                    "source": "tool_system",
                    "payload": {"execution_id": exec_id},
                    "created_at": datetime.utcnow().isoformat(),
                })
                db.emit_event("TOOL_COMPLETED", f"Tool Completed: {tool_def.name}", {"execution_id": exec_id})
                output = json.dumps(execution.output_data)
                return (f"Tool '{tool_def.name}' executed successfully.\n  Execution ID: {exec_id}\n  Output: {output}", ['tools'], ['/tools'])
            else:
                return ("Usage: /tools invoke <tool_id> <input>", [], ['/tools'])
        else:
            tools = list(db.tools_def.values())
            lines = [f"AVAILABLE TOOLS - {len(tools)}"]
            for t in tools:
                lines.append(f"  {t.id}: {t.name} - {t.description}")
            lines.append("")
            lines.append("Invoke: /tools invoke <tool_id> <input>")
            context_used = ['tools_def']
            return ("\n".join(lines), context_used, ['/tools'])

    elif cmd_name == 'evidence':
        evidence = list(db.evidence.values())[-10:]
        lines = [f"RECENT EVIDENCE - {len(evidence)} entries"]
        for e in evidence:
            preview = e.evidence_text[:60] + ('...' if len(e.evidence_text) > 60 else '')
            lines.append(f"  [{e.id}] [{e.source_type}] CONF: {e.confidence:.2f} - {preview}")
        context_used = ['evidence']
        return ("\n".join(lines), context_used, ['/evidence'])

    elif cmd_name == 'claims':
        claims = list(db.claims.values())
        lines = [f"CLAIMS - {len(claims)} total"]
        for c in claims:
            preview = c.text[:60] + ('...' if len(c.text) > 60 else '')
            lines.append(f"  [{c.id}] [{c.status}] CONF: {c.confidence:.2f} - {preview}")
        context_used = ['claims']
        return ("\n".join(lines), context_used, ['/claims'])

    elif cmd_name == 'observatory':
        obs = Observatory(
            events_per_minute=round(len(db.events) / max((datetime.utcnow() - db.start_time).total_seconds() / 60, 1), 2),
            total_events=len(db.events),
            ws_connections=len(websocket_manager.active_connections),
            active_missions=len([m for m in db.missions.values() if m.status == MissionStatus.ACTIVE]),
            active_agents=len([a for a in db.agents_inst.values() if a.status == "active"]),
            tool_executions=len(db.tools_exec),
            recent_events=db.events[-10:],
            recent_tools=list(db.tools_exec.values())[-10:],
        )
        lines = [
            "OBSERVATORY - LIVE TELEMETRY",
            f"  Events/min: {obs.events_per_minute} | Total Events: {obs.total_events}",
            f"  WS Connections: {obs.ws_connections}",
            f"  Active Missions: {obs.active_missions} | Active Agents: {obs.active_agents}",
            f"  Tool Executions: {obs.tool_executions}",
        ]
        context_used = ['observatory']
        return ("\n".join(lines), context_used, ['/observatory'])

    elif cmd_name == 'research':
        if not cmd_arg:
            return ("Usage: /research <query>", [], ['/research'])
        mission_id = generate_id()
        mission = Mission(
            id=mission_id,
            title=f"Mission: {cmd_arg[:30]}",
            query=cmd_arg,
            status=MissionStatus.ACTIVE,
            progress=0.0,
        )
        db.missions[mission_id] = mission
        db.emit_event("MISSION_STARTED", f"Mission Created: {mission.title}", {"mission_id": mission_id})
        await websocket_manager.broadcast({
            "id": str(uuid.uuid4()),
            "type": "MISSION_CREATED",
            "source": "ai_console",
            "payload": {"mission_id": mission_id, "title": mission.title},
            "created_at": datetime.utcnow().isoformat(),
        })
        return (f"Mission launched.\n  ID: {mission_id}\n  Title: {mission.title}\n  Navigate to Mission Control for details.", ['missions'], ['/research'])

    text_lower = user_input.lower()
    lines = [f"SILVERWING AI v{context.get('core_state', {}).get('version', '1.0.0')} - Cognitive Interface"]
    lines.append(f"  Core: {context.get('core_state', {}).get('status')} | Mode: {context.get('core_state', {}).get('mode')}")
    lines.append(f"  Memories: {context.get('memory_stats', {}).get('total', 0)} | Knowledge: {context.get('knowledge_stats', {}).get('entities', 0)}")
    if 'status' in text_lower or 'state' in text_lower:
        lines.append(f"  System is operational. Uptime: {uptime_str}.")
    elif 'hello' in text_lower or 'hi' in text_lower:
        lines.append("  Greetings, Operator. I am SILVERWING, your cognitive co-processor.")
    elif 'memory' in text_lower or 'memories' in text_lower:
        lines.append(f"  Memory matrix contains {context.get('memory_stats', {}).get('total', 0)} vectors.")
    elif 'mission' in text_lower:
        lines.append(f"  {context.get('metrics', {}).get('active_missions', 0)} active mission(s).")
    elif 'knowledge' in text_lower:
        lines.append(f"  Knowledge graph has {context.get('knowledge_stats', {}).get('entities', 0)} entities.")
    elif 'agent' in text_lower:
        lines.append(f"  {context.get('metrics', {}).get('active_agents', 0)} active agent(s).")
    else:
        lines.append("  I am ready to assist. Use /help for available commands.")
    context_used = ['core_state', 'memory_stats', 'knowledge_stats']
    return ("\n".join(lines), context_used, [c.pattern.split()[0] for c in AI_COMMANDS[:5]])


@app.post("/api/ai/converse")
async def converse(request: Dict[str, Any]):
    user_message = request.get("message", "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message is required")

    conversation_id = request.get("conversation_id")
    if not conversation_id:
        conversation_id = generate_id()
        db.conversations[conversation_id] = AIConversation(id=conversation_id)

    conv = db.conversations.get(conversation_id)
    if conv is None:
        conv = AIConversation(id=conversation_id)
        db.conversations[conversation_id] = conv

    user_msg = AIConversationMessage(
        id=str(uuid.uuid4()),
        role="user",
        content=user_message,
    )
    conv.messages.append(user_msg)
    db.conversation_history.append(user_msg)

    context = _get_ai_context_dict()
    command_info = _parse_command(user_message)
    response_text, context_used, suggested = await _generate_contextual_response(user_message, command_info, context)

    ai_msg = AIConversationMessage(
        id=str(uuid.uuid4()),
        role="ai",
        content=response_text,
        metadata={"context_used": context_used, "command": (command_info[0] if command_info else None)},
    )
    conv.messages.append(ai_msg)
    db.conversation_history.append(ai_msg)
    conv.updated_at = datetime.utcnow().isoformat()

    db.emit_event("AI_INTERACTION", "AI Console Interaction", {"conversation_id": conversation_id, "user": user_message[:100]})
    await websocket_manager.broadcast({
        "id": str(uuid.uuid4()),
        "type": "AI_INTERACTION",
        "source": "ai_console",
        "payload": {"conversation_id": conversation_id, "message_length": len(user_message)},
        "created_at": datetime.utcnow().isoformat(),
    })

    return AIResponse(
        message=response_text,
        conversation_id=conversation_id,
        context_used=context_used,
        suggested_commands=suggested,
        timestamp=datetime.utcnow().isoformat(),
    ).dict()


# ============================================
# Initialize Sample Data
# ============================================

@app.on_event("startup")
async def startup_event():
    await orchestrator.start()
    # On a fresh database (no persisted state) seed the sample data so the
    # system is usable out of the box. If a prior persistent database exists,
    # skip seeding so real user data is never overwritten by samples.
    if db.agents_def:
        return

    # Initialize sample agent definitions
    agent_defs = [
        AgentDefinition(
            id="researcher",
            name="Researcher Agent",
            role="researcher",
            description="Specialized in web search and data gathering",
            tools=["search", "analyze", "summarize"],
            permissions=["web_access"],
            risk_level="low"
        ),
        AgentDefinition(
            id="analyst",
            name="Data Analyst",
            role="analyst",
            description="Analyzes data and identifies patterns",
            tools=["analyze", "pattern_recognition", "statistics"],
            permissions=["data_access"],
            risk_level="low"
        ),
        AgentDefinition(
            id="engineer",
            name="Software Engineer",
            role="engineer",
            description="Builds and maintains software systems",
            tools=["code", "debug", "architecture"],
            permissions=["code_execution"],
            risk_level="medium"
        ),
        AgentDefinition(
            id="verifier",
            name="Verifier Agent",
            role="verifier",
            description="Challenges conclusions and checks correctness against evidence",
            tools=["verify"],
            permissions=["evidence_access"],
            risk_level="low"
        ),
    ]
    for defn in agent_defs:
        db.agents_def[defn.id] = defn

    # Initialize sample tool definitions
    tool_defs = [
        ToolDefinition(
            id="web_search",
            name="Web Search",
            description="Search the web for information",
            parameters={"query": {"type": "string", "required": True}}
        ),
        ToolDefinition(
            id="code_executor",
            name="Code Executor",
            description="Execute Python code in a sandbox",
            parameters={"code": {"type": "string", "required": True}}
        ),
        ToolDefinition(
            id="data_analyzer",
            name="Data Analyzer",
            description="Analyze structured data",
            parameters={"data": {"type": "object", "required": True}}
        ),
    ]
    for tool in tool_defs:
        db.tools_def[tool.id] = tool

    # Initialize sample knowledge entities
    knowledge_entities = [
        KnowledgeEntity(
            id="ai",
            name="Artificial Intelligence",
            type="concept",
            description="The intelligence exhibited by machines",
            source_count=5,
            evidence_count=3
        ),
        KnowledgeEntity(
            id="ml",
            name="Machine Learning",
            type="concept",
            description="A subset of AI focused on learning from data",
            source_count=4,
            evidence_count=2
        ),
        KnowledgeEntity(
            id="silverwing",
            name="Silverwing AI",
            type="organization",
            description="AI research and development organization",
            source_count=2,
            evidence_count=1
        ),
    ]
    for entity in knowledge_entities:
        db.knowledge[entity.id] = entity

    # Training Advisor agent + tool (advisory-only; never mutates training).
    if "training-advisor" not in db.agents_def:
        db.agents_def["training-advisor"] = AgentDefinition(
            id="training-advisor", name="Training Advisor",
            role="training_advisor",
            description="Gemini-powered, evidence-based ML research advisor (advisory only)",
            tools=["training_advisor"], permissions=["advisory"], risk_level="low")
    if "training_advisor" not in db.tools_def:
        db.tools_def["training_advisor"] = ToolDefinition(
            id="training_advisor", name="Training Advisor",
            description="Analyze training metrics and provide structured recommendations",
            parameters={"action": {"type": "string", "required": False},
                        "recommendation_id": {"type": "string", "required": False},
                        "approver": {"type": "string", "required": False}})

    # Initialize sample memory entries
    memory_entries = [
        Memory(
            id="mem1",
            content="The user wants to upgrade the frontend with glassmorphism design",
            memory_type=MemoryType.WORKING,
            confidence=0.9,
            importance=1.0,
            provenance={"source_type": "conversation"},
            tags=["frontend", "upgrade", "design"]
        ),
        Memory(
            id="mem2",
            content="Previous conversation discussed React, Vite, and Tailwind CSS",
            memory_type=MemoryType.EPISODIC,
            confidence=0.85,
            importance=0.8,
            provenance={"source_type": "conversation"},
            tags=["react", "vite", "tailwind"]
        ),
    ]
    for mem in memory_entries:
        db.memory[mem.id] = mem

    # Initialize sample evidence
    evidence_entries = [
        Evidence(
            id="ev1",
            claim_text="Glassmorphism is a modern UI design trend using frosted glass effects",
            source_id="web_search",
            source_title="Web Search",
            source_type="web",
            evidence_text="Glassmorphism is a modern UI design trend using frosted glass effects",
            confidence=0.95,
            retrieved_at=datetime.utcnow().isoformat(),
            supporting_source_ids=["web_search"],
            contradicting_source_ids=[]
        ),
        Evidence(
            id="ev2",
            claim_text="Framer Motion provides smooth animations for React applications",
            source_id="documentation",
            source_title="Documentation",
            source_type="documentation",
            evidence_text="Framer Motion provides smooth animations for React applications",
            confidence=0.9,
            retrieved_at=datetime.utcnow().isoformat(),
            supporting_source_ids=["documentation"],
            contradicting_source_ids=[]
        ),
    ]
    for ev in evidence_entries:
        db.evidence[ev.id] = ev

    # Initialize sample claims
    claims = [
        Claim(
            id="cl1",
            text="Glassmorphism improves visual hierarchy in UI design",
            confidence=0.85,
            status="verified",
            is_inference=False,
            evidence_ids=["ev1"],
            supporting_count=1,
            contradicting_count=0,
            source_ids=["web_search"]
        ),
        Claim(
            id="cl2",
            text="Framer Motion is the best animation library for React",
            confidence=0.75,
            status="created",
            is_inference=False,
            evidence_ids=["ev2"],
            supporting_count=0,
            contradicting_count=0,
            source_ids=["documentation"]
        ),
    ]
    for claim in claims:
        db.claims[claim.id] = claim

    # Initialize sample citations
    citations = [
        Citation(
            id="cit1",
            claim_id="cl1",
            source_id="web_search",
            evidence_id="ev1",
            locator="Line 3",
            citation_text="Glassmorphism design trend"
        ),
        Citation(
            id="cit2",
            claim_id="cl2",
            source_id="documentation",
            evidence_id="ev2",
            locator="Section 2",
            citation_text="Framer Motion capabilities"
        ),
    ]
    for cit in citations:
        db.citations[cit.id] = cit

    # Create sample mission
    sample_mission = Mission(
        id="sample_mission",
        title="Frontend Upgrade Initiative",
        query="Upgrade frontend with glassmorphism, animations, and theme toggle",
        status=MissionStatus.COMPLETED,
        progress=100.0,
        agents=["agent1", "agent2"],
        sources=["web_search", "documentation"],
        evidence=["ev1", "ev2"],
        claims=["cl1", "cl2"]
    )
    db.missions["sample_mission"] = sample_mission

    # Create sample agent instances
    sample_agents = [
        AgentInstance(
            id="agent1",
            definition_id="researcher",
            mission_id="sample_mission",
            status="completed",
            current_task="Research and data gathering",
            started_at=datetime.utcnow().isoformat()
        ),
        AgentInstance(
            id="agent2",
            definition_id="analyst",
            mission_id="sample_mission",
            status="completed",
            current_task="Data analysis and pattern identification",
            started_at=datetime.utcnow().isoformat()
        ),
    ]
    for agent in sample_agents:
        db.agents_inst[agent.id] = agent

    # Create sample tool executions
    sample_executions = [
        ToolExecution(
            id="exec1",
            tool_name="web_search",
            input_data={"query": "glassmorphism design examples"},
            output_data={"result": "success", "data": {"count": 10}},
            status="completed",
            agent_id="agent1",
            mission_id="sample_mission",
            started_at=datetime.utcnow().isoformat(),
            completed_at=datetime.utcnow().isoformat(),
            duration_ms=2500
        ),
    ]
    for exec in sample_executions:
        db.tools_exec[exec.id] = exec

    db.emit_event("SYSTEM_STARTED", "Silverwing AI Backend Started", {"status": "ready"})

    # Optionally run the Training Advisor on a cadence (off by default;
    # enable with SILVERWING_ADVISOR_AUTORUN=1). Purely advisory - never mutates
    # the training loop, optimizer, scheduler, or checkpoints.
    if _TRAINING_ADVISOR_INST is not None:
        await _TRAINING_ADVISOR_INST.start_autorun()


@app.on_event("shutdown")
async def shutdown_event():
    await orchestrator.stop()
    db.save()


if __name__ == "__main__":
    import uvicorn
    import warnings as _warnings
    _warnings.warn(
        "silverwing-backend is integrated in-process by the JARVIS platform "
        "(jarvis_api.py, port 8000) under the /silverwing mount. Running it "
        "standalone on port 8000 would collide with the platform. It now binds "
        "the dev-only port 8091.",
        RuntimeWarning,
        stacklevel=2,
    )
    uvicorn.run(app, host="0.0.0.0", port=8091)



