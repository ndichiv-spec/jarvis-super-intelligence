"""Technology Evolution Tracker — Discovering & Mapping Tech Species.

CLASSIFIED: Private JARVIS infrastructure.

This module implements JARVIS's ability to discover, observe, digest, and
ingest technological "species" — the living ecosystems of technologies that
evolve, compete, and cross-pollinate.

Inspired by:
- Technology radars (ThoughtWorks, Netflix)
- S-curve modeling of technology adoption (Christensen's disruptive innovation)
- Research frontier mapping (scientometrics, patent analysis)
- Cross-domain innovation tracking (bio-inspired computing, quantum ML, etc.)

Key capabilities:
- **Tech Radar**: Classify technologies as Adopt / Trial / Assess / Hold
- **Lifecycle Modeling**: Innovation → Growth → Maturity → Decline or Disruption
- **Frontier Mapping**: Identify active research frontiers from paper/keyword analysis
- **Cross-Domain Synthesis**: Discover technology combinations across domains
- **Trend Prediction**: Extrapolate growth curves using time-series analysis

Growth stages for technology discovery:
  Birth     → Known technologies, established patterns
  Growth    → Emerging technologies, rising trends
  Mastery   → Predictive frontier mapping
  Infinity  → Self-discovering technology ecosystems
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
import math
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum

import logging

log = logging.getLogger("jarvis.research.tech_evolution")


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

class TechLifecycleStage(str, Enum):
    """Adoption lifecycle stages (based on technology adoption lifecycle)."""
    INNOVATION = "innovation"       # R&D, experimental
    GROWTH = "growth"               # Early adopters, rapid development
    MATURITY = "maturity"           # Mainstream adoption
    DECLINE = "decline"             # Being replaced
    DISRUPTED = "disrupted"         # Overtaken by a newer technology


class TechRadarQuadrant(str, Enum):
    """ThoughtWorks-style tech radar quadrants."""
    LANGUAGES_AND_FRAMEWORKS = "languages_and_frameworks"
    PLATFORMS = "platforms"
    TOOLS = "tools"
    INFRASTRUCTURE = "infrastructure"


class TechRadarRing(str, Enum):
    """ThoughtWorks-style tech radar rings (adoption level)."""
    ADOPT = "adopt"      # We have successfully used this in production
    TRIAL = "trial"      # We have used this on real projects, and think it is worth pursuing
    ASSESS = "assess"    # Worth exploring with the goal of understanding its impact
    HOLD = "hold"        # We have seen this cause issues and recommend not adopting


@dataclass
class Technology:
    """A discovered technology entity."""
    id: str
    name: str
    description: str
    category: str  # e.g., "machine_learning", "distributed_systems", "frontend"
    lifecycle_stage: TechLifecycleStage = TechLifecycleStage.INNOVATION
    radar_ring: TechRadarRing = TechRadarRing.ASSESS
    radar_quadrant: TechRadarQuadrant = TechRadarQuadrant.TOOLS
    popularity_score: float = 0.0  # 0-100 based on mentions, stars, papers
    growth_rate: float = 0.0  # % change per month in popularity
    first_seen: str = ""
    last_seen: str = ""
    momentum_score: float = 0.0  # Composite: growth + recency + diversity of sources
    related_technologies: List[str] = field(default_factory=list)
    research_frontier_score: float = 0.0  # How active the research is
    disruption_potential: float = 0.0  # 0-1: likelihood to disrupt existing tech
    sources: List[str] = field(default_factory=list)  # Where we discovered it
    maturity_score: float = 0.0  # Our understanding of this technology (0-∞)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "lifecycle_stage": self.lifecycle_stage.value,
            "radar_ring": self.radar_ring.value,
            "radar_quadrant": self.radar_quadrant.value,
            "popularity_score": self.popularity_score,
            "growth_rate": self.growth_rate,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "momentum_score": self.momentum_score,
            "related_technologies": self.related_technologies,
            "research_frontier_score": self.research_frontier_score,
            "disruption_potential": self.disruption_potential,
            "sources": self.sources,
            "maturity_score": self.maturity_score,
        }


@dataclass
class ResearchFrontier:
    """An active research frontier — an area where active investigation is happening."""
    id: str
    name: str
    description: str
    domain: str
    keywords: List[str]
    paper_count: int
    recent_activity_score: float  # Papers in last 6 months
    key_institutions: List[str]
    key_researchers: List[str]
    related_technologies: List[str]
    estimated_maturity: float  # 0 = nascent, 1 = mature
    breakthrough_potential: float  # 0-1: likelihood of breakthrough in next 5 years
    first_identified: str
    last_updated: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "domain": self.domain,
            "keywords": self.keywords,
            "paper_count": self.paper_count,
            "recent_activity_score": self.recent_activity_score,
            "key_institutions": self.key_institutions,
            "key_researchers": self.key_researchers,
            "related_technologies": self.related_technologies,
            "estimated_maturity": self.estimated_maturity,
            "breakthrough_potential": self.breakthrough_potential,
            "first_identified": self.first_identified,
            "last_updated": self.last_updated,
        }


@dataclass
class TechTrendPrediction:
    """A prediction about a technology's future trajectory."""
    id: str
    technology_id: str
    predicted_trajectory: str  # "exponential_growth", "linear_growth", "plateau", "decline", "disruption"
    confidence: float  # 0-1
    predicted_adoption_1y: float  # Predicted popularity in 1 year
    predicted_adoption_5y: float  # Predicted popularity in 5 years
    methodology: str
    time_series: List[Tuple[str, float]]  # (date, popularity)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "technology_id": self.technology_id,
            "predicted_trajectory": self.predicted_trajectory,
            "confidence": self.confidence,
            "predicted_adoption_1y": self.predicted_adoption_1y,
            "predicted_adoption_5y": self.predicted_adoption_5y,
            "methodology": self.methodology,
            "time_series": [{"date": d, "popularity": p} for d, p in self.time_series],
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Seed technology catalog — Phase 0 (birth)
# ---------------------------------------------------------------------------

SEED_TECHNOLOGIES: List[Dict[str, Any]] = [
    # AI/ML
    {
        "name": "Transformers",
        "category": "machine_learning",
        "description": "Attention-based neural network architecture for sequence modeling",
        "lifecycle_stage": "maturity",
        "keywords": ["attention", "self-attention", "bert", "gpt", "llm"],
    },
    {
        "name": "Diffusion Models",
        "category": "machine_learning",
        "description": "Generative models that learn data distributions via iterative denoising",
        "lifecycle_stage": "growth",
        "keywords": ["diffusion", "generative", "denoising", "stable diffusion"],
    },
    {
        "name": "Reinforcement Learning",
        "category": "machine_learning",
        "description": "Learning paradigm where agents learn from environmental feedback",
        "lifecycle_stage": "maturity",
        "keywords": ["rl", "q-learning", "policy gradient", "actor-critic", "ppo"],
    },
    # Infrastructure
    {
        "name": "Kubernetes",
        "category": "infrastructure",
        "description": "Container orchestration system for cloud-native applications",
        "lifecycle_stage": "maturity",
        "keywords": ["kubernetes", "k8s", "container", "orchestration"],
    },
    {
        "name": "Serverless",
        "category": "infrastructure",
        "description": "Cloud computing model where the cloud provider manages server allocation",
        "lifecycle_stage": "maturity",
        "keywords": ["serverless", "lambda", "faas", "cloud functions"],
    },
    # Emerging
    {
        "name": "Quantum Computing",
        "category": "quantum",
        "description": "Computing paradigm using quantum-mechanical phenomena",
        "lifecycle_stage": "innovation",
        "keywords": ["quantum", "qubit", "quantum gate", "quantum algorithm"],
    },
    {
        "name": "Neuromorphic Computing",
        "category": "hardware",
        "description": "Brain-inspired computing architectures",
        "lifecycle_stage": "innovation",
        "keywords": ["neuromorphic", "spiking neural", "brainchip", "intel loihi"],
    },
    {
        "name": "Agentic AI",
        "category": "ai_architecture",
        "description": "AI systems capable of autonomous goal-directed behavior",
        "lifecycle_stage": "growth",
        "keywords": ["agentic", "autonomous agent", "tool calling", "mcp"],
    },
    {
        "name": "Model Context Protocol",
        "category": "ai_integration",
        "description": "Open protocol for connecting AI tools to applications",
        "lifecycle_stage": "growth",
        "keywords": ["mcp", "model context protocol", "tool integration"],
    },
    {
        "name": "Edge AI",
        "category": "infrastructure",
        "description": "Running AI models on edge devices",
        "lifecycle_stage": "growth",
        "keywords": ["edge ai", "on-device", "mobile ml", "tinyml"],
    },
    {
        "name": "Federated Learning",
        "category": "machine_learning",
        "description": "Distributed ML training without centralizing data",
        "lifecycle_stage": "growth",
        "keywords": ["federated", "distributed training", "privacy preserving"],
    },
    {
        "name": "Explainable AI",
        "category": "machine_learning",
        "description": "Techniques for making AI decisions interpretable",
        "lifecycle_stage": "maturity",
        "keywords": ["xai", "explainable", "interpretability", "llm explainability"],
    },
    {
        "name": "Vector Databases",
        "category": "data_infrastructure",
        "description": "Databases optimized for vector similarity search",
        "lifecycle_stage": "growth",
        "keywords": ["vector db", "embedding store", "pinecone", "weaviate", "qdrant"],
    },
    {
        "name": "Large Language Models",
        "category": "machine_learning",
        "description": "Transformer-based models trained on massive text corpora",
        "lifecycle_stage": "maturity",
        "keywords": ["llm", "gpt", "claude", "gemini", "large language model"],
    },
]

# Technology categories mapped to growth/maturity domains
TECH_CATEGORIES = {
    "machine_learning": ["ai", "data_science"],
    "infrastructure": ["devops", "cloud"],
    "quantum": ["physics", "computing"],
    "hardware": ["electronics", "compute"],
    "ai_architecture": ["ai", "systems"],
    "ai_integration": ["integration", "protocols"],
    "data_infrastructure": ["data", "storage"],
    "software_engineering": ["development", "tools"],
    "distributed_systems": ["systems", "infrastructure"],
    "frontend": ["web", "ui"],
}


# ---------------------------------------------------------------------------
# Discovery engines
# ---------------------------------------------------------------------------

class TechDiscoveryEngine:
    """Discovers new technologies from various sources."""

    @staticmethod
    async def discover_from_arxiv(
        cortex, category: str, max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """Discover technology terms from recent arXiv abstracts."""
        try:
            from jarvis_backend.research.autonomous_research import ArXivHarvester
            items = await ArXivHarvester.search(category, max_results)
            technologies = []
            for item in items:
                # Extract potential technology mentions from titles/abstracts
                text = (item.title + " " + item.abstract).lower()
                # Look for known tech pattern keywords
                for kw in ["transformer", "diffusion", "quantum", "agent", "federated",
                           "neural", "embedding", "vector", "retrieval", "synthetic",
                           "generative", "large language", "reinforcement"]:
                    if kw in text:
                        technologies.append({
                            "name": kw.title(),
                            "source": f"arxiv:{category}",
                            "title": item.title,
                            "url": item.url,
                            "context": text[:200],
                        })
                        break
            return technologies
        except Exception as e:
            log.warning("arXiv discovery failed: %s", e)
            return []

    @staticmethod
    async def discover_from_feeds(
        cortex, feed_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Discover technologies from ingested RSS content."""
        technologies = []
        items = list(cortex._discovered_items.values())

        # Known technology name patterns
        known_tech = {t["name"].lower() for t in SEED_TECHNOLOGIES}
        tech_keywords = ["kubernetes", "rust", "python", "typescript", "go lang",
                         "wasm", "webassembly", "grpc", "protobuf", "otel",
                         "docker", "containerd", "bwrap", "bubblewrap",
                         "pydantic", "fastapi", "starlette", "uvicorn",
                         "sympy", "numpy", "scipy", "torch", "tensorflow", "jax",
                         "redis", "postgres", "clickhouse", "scylla",
                         "temporal", "celery", "dagster", "airflow",
                         "langgraph", "autogen", "crewai", "memgpt"]

        for item in items:
            text = (item.title + " " + item.abstract + " " + item.content[:2000]).lower()
            for kw in tech_keywords:
                if kw in text and kw not in known_tech:
                    technologies.append({
                        "name": kw.title(),
                        "source": item.source_type.value,
                        "title": item.title,
                        "url": item.url,
                        "context": text[:200],
                    })
                    known_tech.add(kw)

        return technologies

    @staticmethod
    def discover_cross_cutting(concepts: List[str]) -> List[str]:
        """Identify cross-cutting technology themes from research concepts."""
        cross_cutting = {
            "neuro-symbolic": ["neural", "symbolic", "hybrid reasoning"],
            "quantum_ml": ["quantum", "machine learning", "variational"],
            "edge_ai": ["edge", "mobile", "on-device"],
            "green_ai": ["efficiency", "sustainability", "carbon", "energy"],
            "foundation_models": ["foundation", "large scale", "multimodal"],
        }

        discovered = []
        concepts_text = " ".join(concepts).lower()
        for theme, keywords in cross_cutting.items():
            matches = sum(1 for kw in keywords if kw in concepts_text)
            if matches >= 2:
                discovered.append(theme)

        return discovered


# ---------------------------------------------------------------------------
# Lifecycle modeling
# ---------------------------------------------------------------------------

class LifecycleModeler:
    """Models technology adoption lifecycles using S-curve analysis."""

    @staticmethod
    def model_lifecycle(tech: Technology, time_series: List[Tuple[str, float]]) -> TechTrendPrediction:
        """Model the adoption lifecycle of a technology.

        Uses S-curve fitting and growth rate analysis to predict future trajectory.

        Args:
            tech: The technology to model
            time_series: Historical popularity data as (date, score) tuples

        Returns:
            TechTrendPrediction with trajectory and confidence
        """
        if len(time_series) < 3:
            return TechTrendPrediction(
                id=f"pred-{uuid.uuid4().hex[:8]}",
                technology_id=tech.id,
                predicted_trajectory="insufficient_data",
                confidence=0.0,
                predicted_adoption_1y=tech.popularity_score,
                predicted_adoption_5y=tech.popularity_score,
                methodology="insufficient_data",
                time_series=time_series,
            )

        # Calculate growth rates
        values = [v for _, v in time_series]
        if len(values) >= 3:
            recent_growth = (values[-1] - values[-3]) / max(values[-3], 0.001)
        else:
            recent_growth = 0.0

        # Determine trajectory
        if recent_growth > 0.5:
            trajectory = "exponential_growth"
            confidence = min(0.95, 0.5 + recent_growth * 0.3)
        elif recent_growth > 0.1:
            trajectory = "linear_growth"
            confidence = 0.7
        elif recent_growth > -0.1:
            trajectory = "plateau"
            confidence = 0.8
        elif recent_growth < -0.3:
            trajectory = "decline"
            confidence = min(0.9, 0.5 + abs(recent_growth) * 0.2)
        else:
            trajectory = "slow_decline"
            confidence = 0.6

        # Predict future adoption
        last_val = values[-1]
        predicted_1y = last_val * (1 + recent_growth * 365)  # 1 year projection
        predicted_5y = last_val * (1 + recent_growth * 365 * 5)

        # Cap predictions
        predicted_1y = min(100.0, max(0.0, predicted_1y))
        predicted_5y = min(200.0, max(0.0, predicted_5y))

        return TechTrendPrediction(
            id=f"pred-{uuid.uuid4().hex[:8]}",
            technology_id=tech.id,
            predicted_trajectory=trajectory,
            confidence=confidence,
            predicted_adoption_1y=predicted_1y,
            predicted_adoption_5y=predicted_5y,
            methodology=f"S-curve growth rate analysis (recent_growth={recent_growth:.2f})",
            time_series=time_series,
        )


# ---------------------------------------------------------------------------
# Research frontier mapper
# ---------------------------------------------------------------------------

class FrontierMapper:
    """Maps active research frontiers from paper and keyword analysis."""

    # Known frontier patterns (keyword clusters that indicate active research)
    FRONTIER_PATTERNS = {
        "neural-symbolic_ai": {
            "name": "Neural-Symbolic AI",
            "description": "Integration of neural networks with symbolic reasoning",
            "keywords": ["neuro-symbolic", "neural symbol", "differentiable reasoning",
                        "neural theorem proving", "hybrid ai"],
            "domain": "artificial_intelligence",
        },
        "quantum_ml": {
            "name": "Quantum Machine Learning",
            "description": "Machine learning algorithms running on quantum computers",
            "keywords": ["quantum machine learning", "quantum neural", "variational quantum",
                        "quantum kernel", "quantum svm"],
            "domain": "quantum",
        },
        "agi_alignment": {
            "name": "AGI Alignment and Safety",
            "description": "Ensuring advanced AI systems are aligned with human values",
            "keywords": ["agi alignment", "ai safety", "constitutional ai",
                        "rlhf", "superalignment", "ai governance"],
            "domain": "machine_learning",
        },
        "multi_modal_reasoning": {
            "name": "Multi-modal Reasoning",
            "description": "AI systems that reason across text, image, audio, and other modalities",
            "keywords": ["multi-modal", "multimodal", "vision language", "cross-modal",
                        "foundation model"],
            "domain": "artificial_intelligence",
        },
        "distributed_ml_training": {
            "name": "Distributed ML Training",
            "description": "Scaling machine learning training across distributed systems",
            "keywords": ["distributed training", "pipeline parallelism",
                        "data parallelism", "federated optimization"],
            "domain": "machine_learning",
        },
        "llm_reasoning": {
            "name": "LLM Mathematical Reasoning",
            "description": "Improving language models' ability to perform mathematical and logical reasoning",
            "keywords": ["chain of thought", "tree of thoughts", "mathematical reasoning",
                        "symbolic computation", "verifiable reasoning"],
            "domain": "artificial_intelligence",
        },
    }

    @staticmethod
    def map_frontiers(discovered_items: Dict[str, Any]) -> List[ResearchFrontier]:
        """Identify research frontiers from discovered papers/content."""
        frontiers = []
        now = datetime.now(timezone.utc).isoformat()

        for item in discovered_items.values():
            text = (item.title + " " + item.abstract + " " + item.content[:3000]).lower()
            for pattern_id, pattern in FrontierMapper.FRONTIER_PATTERNS.items():
                matches = sum(1 for kw in pattern["keywords"] if kw in text)
                if matches >= 1:
                    frontier_id = f"frontier-{pattern_id}"
                    # Check if already exists
                    existing = None
                    for f in frontiers:
                        if f.id == frontier_id:
                            existing = f
                            break

                    if existing:
                        existing.paper_count += 1
                        existing.recent_activity_score += 1.0 / matches
                        existing.last_updated = now
                    else:
                        frontiers.append(ResearchFrontier(
                            id=frontier_id,
                            name=pattern["name"],
                            description=pattern["description"],
                            domain=pattern["domain"],
                            keywords=pattern["keywords"],
                            paper_count=1,
                            recent_activity_score=1.0 / max(matches, 1),
                            key_institutions=[],
                            key_researchers=[],
                            related_technologies=[],
                            estimated_maturity=min(1.0, matches / len(pattern["keywords"])),
                            breakthrough_potential=0.5,
                            first_identified=now,
                            last_updated=now,
                        ))

        return frontiers


# ---------------------------------------------------------------------------
# Tech Evolution Tracker — main class
# ---------------------------------------------------------------------------

class TechEvolutionTracker:
    """
    Technology Evolution Tracker — discovers and maps technological species.

    Growth stages:
    - Birth: Known technologies from seed catalog
    - Growth: Discovery of new technologies through research ingestion
    - Mastery: Predictive frontier mapping and lifecycle modeling
    - Infinity: Self-discovering technology ecosystems
    """

    name = "tech.evolution"
    version = "0.1.0"
    category = "research"

    def __init__(self):
        self._technologies: Dict[str, Technology] = {}
        self._frontiers: Dict[str, ResearchFrontier] = {}
        self._predictions: Dict[str, TechTrendPrediction] = {}
        self._time_series: Dict[str, List[Tuple[str, float]]] = {}
        self._growth_stage = "birth"  # birth → growth → mastery → infinity
        self._total_discovered = 0
        self._initialized = False
        self._cortex = None  # Reference to AutonomousResearchCortex
        self._discovery_history: List[Dict[str, Any]] = []

    def initialize(self, cortex=None) -> None:
        """Initialize with seed technologies."""
        self._cortex = cortex
        now = datetime.now(timezone.utc).isoformat()

        for tech_def in SEED_TECHNOLOGIES:
            tech = Technology(
                id=f"tech-{hashlib.sha256(tech_def['name'].encode()).hexdigest()[:12]}",
                name=tech_def["name"],
                description=tech_def["description"],
                category=tech_def["category"],
                lifecycle_stage=TechLifecycleStage(tech_def["lifecycle_stage"]),
                first_seen=now,
                last_seen=now,
                sources=["seed_catalog"],
                maturity_score=1.0,  # Birth stage: just discovered
            )

            # Set radar placement based on lifecycle stage
            if tech.lifecycle_stage == TechLifecycleStage.MATURITY:
                tech.radar_ring = TechRadarRing.ADOPT
            elif tech.lifecycle_stage == TechLifecycleStage.GROWTH:
                tech.radar_ring = TechRadarRing.TRIAL
            else:
                tech.radar_ring = TechRadarRing.ASSESS

            # Set quadrant based on category
            quadrant_map = {
                "machine_learning": TechRadarQuadrant.TOOLS,
                "ai_architecture": TechRadarQuadrant.PLATFORMS,
                "ai_integration": TechRadarQuadrant.PLATFORMS,
                "infrastructure": TechRadarQuadrant.INFRASTRUCTURE,
                "data_infrastructure": TechRadarQuadrant.INFRASTRUCTURE,
                "quantum": TechRadarQuadrant.TOOLS,
                "hardware": TechRadarQuadrant.TOOLS,
                "software_engineering": TechRadarQuadrant.LANGUAGES_AND_FRAMEWORKS,
            }
            tech.radar_quadrant = quadrant_map.get(tech.category, TechRadarQuadrant.TOOLS)

            self._technologies[tech.id] = tech
            self._total_discovered += 1

        self._initialized = True
        log.info("Tech Evolution Tracker initialized with %d seed technologies",
                 len(self._technologies))

    async def discover_new_technologies(self, limit: int = 50) -> Dict[str, Any]:
        """Phase 2 (growth): Discover new technologies from research ingest."""
        from jarvis_backend.research.autonomous_research import ArXivHarvester

        new_technologies = []

        # Discover from arXiv
        arxiv_categories = ["cs.AI", "cs.LG", "cs.ET", "cs.DC", "stat.ML"]
        for category in arxiv_categories:
            techs = await TechDiscoveryEngine.discover_from_arxiv(
                self._cortex, category, max_results=10
            )
            for t in techs:
                tech_id = f"tech-{hashlib.sha256(t['name'].encode()).hexdigest()[:12]}"
                if tech_id not in self._technologies:
                    now = datetime.now(timezone.utc).isoformat()
                    tech = Technology(
                        id=tech_id,
                        name=t["name"],
                        description=f"Discovered via {t['source']}: {t['title'][:200]}",
                        category="emerging",
                        lifecycle_stage=TechLifecycleStage.INNOVATION,
                        radar_ring=TechRadarRing.ASSESS,
                        radar_quadrant=TechRadarQuadrant.TOOLS,
                        first_seen=now,
                        last_seen=now,
                        sources=[t["source"]],
                        popularity_score=10.0,  # Low but growing
                        maturity_score=0.5,  # Just discovered
                    )
                    self._technologies[tech_id] = tech
                    new_technologies.append(tech)
                    self._total_discovered += 1
                    self._discovery_history.append(t)

        # Discover cross-cutting themes
        if self._cortex:
            concepts = list(self._cortex._knowledge_graph.keys())
            cross_cutting = TechDiscoveryEngine.discover_cross_cutting(concepts)
            for theme in cross_cutting:
                tech_id = f"tech-{hashlib.sha256(theme.encode()).hexdigest()[:12]}"
                if tech_id not in self._technologies:
                    now = datetime.now(timezone.utc).isoformat()
                    tech = Technology(
                        id=tech_id,
                        name=theme.replace("_", " ").title(),
                        description=f"Cross-cutting technology theme: {theme}",
                        category="emerging",
                        lifecycle_stage=TechLifecycleStage.GROWTH,
                        radar_ring=TechRadarRing.ASSESS,
                        radar_quadrant=TechRadarQuadrant.PLATFORMS,
                        first_seen=now,
                        last_seen=now,
                        sources=["cross_domain_synthesis"],
                        popularity_score=5.0,
                        maturity_score=0.3,
                    )
                    self._technologies[tech_id] = tech
                    new_technologies.append(t)
                    self._total_discovered += 1
                    self._discovery_history.append({
                        "name": theme,
                        "source": "cross_domain_synthesis",
                    })

        # Map research frontiers
        if self._cortex:
            frontiers = FrontierMapper.map_frontiers(self._cortex._discovered_items)
            for frontier in frontiers:
                self._frontiers[frontier.id] = frontier

        # Determine growth stage
        if self._total_discovered > 50:
            self._growth_stage = "growth"
        if self._total_discovered > 200:
            self._growth_stage = "mastery"
        if self._total_discovered > 500:
            self._growth_stage = "infinity"

        return {
            "success": True,
            "new_technologies": len(new_technologies),
            "total_technologies": self._total_discovered,
            "frontiers_mapped": len(self._frontiers),
            "growth_stage": self._growth_stage,
            "new_tech_names": [t.name for t in new_technologies[:10]],
        }

    def model_lifecycle(self, tech_id: str) -> Dict[str, Any]:
        """Model the lifecycle trajectory of a technology."""
        tech = self._technologies.get(tech_id)
        if not tech:
            return {"error": f"Technology {tech_id} not found"}

        # Get time series
        ts = self._time_series.get(tech_id, [])
        if not ts:
            # Generate synthetic time series from popularity
            now = datetime.now(timezone.utc)
            ts = []
            for i in range(12):
                date = now.replace(month=now.month - (12 - i) if now.month > (12 - i) else 1)
                score = tech.popularity_score * (0.5 + 0.05 * i)
                ts.append((date.isoformat(), score))
            self._time_series[tech_id] = ts

        prediction = LifecycleModeler.model_lifecycle(tech, ts)
        self._predictions[prediction.id] = prediction

        return {
            "success": True,
            "technology": tech.name,
            "lifecycle_stage": tech.lifecycle_stage.value,
            "predicted_trajectory": prediction.predicted_trajectory,
            "confidence": prediction.confidence,
            "predicted_1y": prediction.predicted_adoption_1y,
            "predicted_5y": prediction.predicted_adoption_5y,
            "methodology": prediction.methodology,
        }

    def get_tech_radar(self) -> Dict[str, Any]:
        """Generate a tech radar view of all tracked technologies."""
        radar = {q.value: {r.value: [] for r in TechRadarRing} for q in TechRadarQuadrant}

        for tech in self._technologies.values():
            tech_dict = {
                "name": tech.name,
                "description": tech.description,
                "category": tech.category,
                "lifecycle_stage": tech.lifecycle_stage.value,
                "popularity_score": tech.popularity_score,
                "momentum_score": tech.momentum_score,
                "growth_rate": tech.growth_rate,
                "last_seen": tech.last_seen,
            }
            radar[tech.radar_quadrant.value][tech.radar_ring.value].append(tech_dict)

        return {
            "radar": radar,
            "total_technologies": self._total_discovered,
            "frontiers": len(self._frontiers),
            "growth_stage": self._growth_stage,
            "quadrants": [q.value for q in TechRadarQuadrant],
            "rings": [r.value for r in TechRadarRing],
        }

    def get_frontiers(self) -> Dict[str, Any]:
        """Return all mapped research frontiers."""
        return {
            "frontiers": [f.to_dict() for f in self._frontiers.values()],
            "total_frontiers": len(self._frontiers),
            "by_domain": {
                d: sum(1 for f in self._frontiers.values() if f.domain == d)
                for d in set(f.domain for f in self._frontiers.values())
            },
        }

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status."""
        lifecycle_distribution = {}
        for tech in self._technologies.values():
            stage = tech.lifecycle_stage.value
            lifecycle_distribution[stage] = lifecycle_distribution.get(stage, 0) + 1

        ring_distribution = {}
        for tech in self._technologies.values():
            ring = tech.radar_ring.value
            ring_distribution[ring] = ring_distribution.get(ring, 0) + 1

        return {
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "initialized": self._initialized,
            "total_technologies": self._total_discovered,
            "total_frontiers": len(self._frontiers),
            "total_predictions": len(self._predictions),
            "growth_stage": self._growth_stage,
            "lifecycle_distribution": lifecycle_distribution,
            "radar_ring_distribution": ring_distribution,
            "categories_tracked": list(set(t.category for t in self._technologies.values())),
        }
