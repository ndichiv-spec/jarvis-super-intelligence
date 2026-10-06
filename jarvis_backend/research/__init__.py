"""JARVIS Research package — bio-growth intelligence layers.

Contains four interlocking systems that extend JARVIS beyond the enterprise
backend into autonomous scientific and technological growth:

- AutonomousResearchCortex: internet-aware ingestion (RSS, arXiv, web crawling)
- ScienceEngine: symbolic & numerical reasoning (SymPy, NumPy/SciPy)
- BioLearner: curriculum learning, memory consolidation, maturity scoring
- TechEvolutionTracker: technology radar, frontier mapping, cross-domain synthesis
"""
from __future__ import annotations

from .autonomous_research import AutonomousResearchCortex
from .science_engine import ScienceEngine
from .bio_learner import BioLearner
from .tech_evolution import TechEvolutionTracker

__all__ = [
    "AutonomousResearchCortex",
    "ScienceEngine",
    "BioLearner",
    "TechEvolutionTracker",
]
