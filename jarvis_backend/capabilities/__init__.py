"""
JARVIS Capabilities Package
===========================

All JARVIS capabilities live here. Each capability is an independent subsystem
that connects to the common orchestration/event/state architecture.

Capabilities:
- brain: Reasoning and decision-making
- conversation: Shared interaction state
- voice: Voice input/output (STT/TTS)
- vision: Image understanding and OCR
- image.generate: Image generation
- provider: Provider/model orchestration
- browser: Browser automation
- task: Task management and autonomous work
- memory: Independent memory subsystem
- knowledge: Knowledge retrieval and RAG
- tool: Tool/connector execution
- research.cortex: Internet-aware knowledge ingestion (RSS, arXiv, web crawling)
- science.engine: Symbolic & numerical mathematical reasoning (SymPy, NumPy, SciPy)
- bio.learner: Bio-growth learning framework (curriculum, SM-2, memory consolidation)
- tech.evolution: Technology evolution tracker (tech radar, frontier mapping, lifecycle)
"""

import asyncio
import sys
import os
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import (
    Capability,
    CapabilityStatus,
    ExecutionContext,
    ExecutionResult,
    CapabilityRegistry,
    Orchestrator,
    get_registry,
    get_orchestrator,
)
from jarvis_backend.event_fabric import EventBus, get_event_bus, Event
from jarvis_backend.persistence import initialize_persistence


def register_all_capabilities() -> CapabilityRegistry:
    """Register all JARVIS capabilities with the orchestrator."""
    registry = get_registry()
    orchestrator = get_orchestrator()

    # Initialize persistence tables
    initialize_persistence()

    # Register each capability
    capabilities = []

    # 1. Brain - reasoning core
    try:
        from jarvis_backend.capabilities.brain import BrainCapability
        brain = BrainCapability()
        registry.register(brain, {
            'version': brain.version,
            'category': brain.category,
            'description': 'Reasoning and decision-making subsystem',
        })
        brain.set_orchestrator(orchestrator)
        capabilities.append(brain)
    except Exception as e:
        print(f"Failed to register brain: {e}")

    # 2. Conversation - shared interaction state
    try:
        from jarvis_backend.capabilities.conversation import ConversationCapability
        conv = ConversationCapability()
        registry.register(conv, {
            'version': conv.version,
            'category': conv.category,
            'description': 'Shared interaction state across all modalities',
        })
        capabilities.append(conv)
    except Exception as e:
        print(f"Failed to register conversation: {e}")

    # 3. Voice - first-class capability
    try:
        from jarvis_backend.capabilities.voice import VoiceCapability
        voice = VoiceCapability()
        registry.register(voice, {
            'version': voice.version,
            'category': voice.category,
            'description': 'Voice input/output with STT/TTS pipeline',
        })
        capabilities.append(voice)
    except Exception as e:
        print(f"Failed to register voice: {e}")

    # 4. Vision - image understanding
    try:
        from jarvis_backend.capabilities.vision import VisionCapability
        vision = VisionCapability()
        registry.register(vision, {
            'version': vision.version,
            'category': vision.category,
            'description': 'Image understanding, OCR, and visual reasoning',
        })
        capabilities.append(vision)
    except Exception as e:
        print(f"Failed to register vision: {e}")

    # 5. Image Generation - first-class capability
    try:
        from jarvis_backend.capabilities.image_generation import ImageGenerationCapability
        img_gen = ImageGenerationCapability()
        registry.register(img_gen, {
            'version': img_gen.version,
            'category': img_gen.category,
            'description': 'Image generation with artifact storage',
        })
        capabilities.append(img_gen)
    except Exception as e:
        print(f"Failed to register image generation: {e}")

    # 6. Provider - model/provider orchestration
    try:
        from jarvis_backend.capabilities.provider import ProviderCapability
        provider = ProviderCapability()
        registry.register(provider, {
            'version': provider.version,
            'category': provider.category,
            'description': 'Provider/model routing with truthful status',
        })
        capabilities.append(provider)
    except Exception as e:
        print(f"Failed to register provider: {e}")

    # 7. Browser - browser automation
    try:
        from jarvis_backend.capabilities.browser import BrowserCapability
        browser = BrowserCapability()
        registry.register(browser, {
            'version': browser.version,
            'category': browser.category,
            'description': 'Browser automation with real HTTP engine',
        })
        capabilities.append(browser)
    except Exception as e:
        print(f"Failed to register browser: {e}")

    # 8. Task - task management
    try:
        from jarvis_backend.capabilities.task import TaskCapability
        task_cap = TaskCapability()
        registry.register(task_cap, {
            'version': task_cap.version,
            'category': task_cap.category,
            'description': 'Task management, scheduling, and autonomous work',
        })
        capabilities.append(task_cap)
    except Exception as e:
        print(f"Failed to register task: {e}")

    # 9. Memory - independent memory subsystem
    try:
        from jarvis_backend.capabilities.memory import MemoryCapability
        memory_cap = MemoryCapability()
        registry.register(memory_cap, {
            'version': memory_cap.version,
            'category': memory_cap.category,
            'description': 'Independent memory (working, episodic, semantic, RAG)',
        })
        capabilities.append(memory_cap)
    except Exception as e:
        print(f"Failed to register memory: {e}")

    # 10. Knowledge - search and RAG
    try:
        from jarvis_backend.capabilities.knowledge import KnowledgeCapability
        knowledge = KnowledgeCapability()
        registry.register(knowledge, {
            'version': knowledge.version,
            'category': knowledge.category,
            'description': 'Knowledge search and RAG retrieval',
        })
        capabilities.append(knowledge)
    except Exception as e:
        print(f"Failed to register knowledge: {e}")

    # 11. Tool - tool/connector execution
    try:
        from jarvis_backend.capabilities.tools import ToolCapability
        tools = ToolCapability()
        registry.register(tools, {
            'version': tools.version,
            'category': tools.category,
            'description': 'Tool and connector execution with security boundary',
        })
        capabilities.append(tools)
    except Exception as e:
        print(f"Failed to register tools: {e}")

    # 12. Research Cortex - internet-aware knowledge ingestion
    try:
        from jarvis_backend.capabilities.research_cortex import ResearchCortexCapability
        research = ResearchCortexCapability()
        registry.register(research, {
            'version': research.version,
            'category': research.category,
            'description': 'Autonomous research cortex: RSS, arXiv, web crawling, semantic analysis',
        })
        capabilities.append(research)
    except Exception as e:
        print(f"Failed to register research cortex: {e}")

    # 13. Science Engine - symbolic & numerical mathematical reasoning
    try:
        from jarvis_backend.capabilities.science import ScienceCapability
        science = ScienceCapability()
        registry.register(science, {
            'version': science.version,
            'category': science.category,
            'description': 'Scientific reasoning with SymPy, NumPy, SciPy',
        })
        capabilities.append(science)
    except Exception as e:
        print(f"Failed to register science: {e}")

    # 14. Bio-Learner - bio-growth learning framework
    try:
        from jarvis_backend.capabilities.bio_learner import BioLearnerCapability
        bio = BioLearnerCapability()
        registry.register(bio, {
            'version': bio.version,
            'category': bio.category,
            'description': 'Bio-growth learning: curriculum, SM-2 spaced repetition, memory consolidation',
        })
        capabilities.append(bio)
    except Exception as e:
        print(f"Failed to register bio-learner: {e}")

    # 15. Tech Evolution Tracker - technology radar & frontier mapping
    try:
        from jarvis_backend.capabilities.tech_tracker import TechEvolutionTrackerCapability
        tech = TechEvolutionTrackerCapability()
        registry.register(tech, {
            'version': tech.version,
            'category': tech.category,
            'description': 'Technology evolution tracker: tech radar, frontier mapping, lifecycle modeling',
        })
        capabilities.append(tech)
    except Exception as e:
        print(f"Failed to register tech tracker: {e}")

    return registry


def get_all_capabilities() -> Dict[str, Any]:
    """Get all registered capabilities and their status."""
    registry = get_registry()
    return {
        'capabilities': registry.get_status(),
        'registry': {
            name: {
                'name': cap.name,
                'version': cap.version,
                'category': cap.category,
                'status': cap.status.value,
                'error': cap.error,
            }
            for name, cap in registry._capabilities.items()
        },
    }


def run_health_checks() -> Dict[str, Any]:
    """Run health checks on all capabilities."""
    registry = get_registry()
    return asyncio.run(registry.health_all())


__all__ = [
    'register_all_capabilities',
    'get_all_capabilities',
    'run_health_checks',
    'Capability',
    'CapabilityStatus',
    'ExecutionContext',
    'ExecutionResult',
    'EventBus',
    'get_event_bus',
    'Event',
    'ResearchCortexCapability',
    'ScienceCapability',
    'BioLearnerCapability',
    'TechEvolutionTrackerCapability',
]
