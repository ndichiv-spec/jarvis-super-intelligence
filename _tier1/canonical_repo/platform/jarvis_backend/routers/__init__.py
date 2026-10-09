"""JARVIS backend routers package.

This package contains all API route modules. Each module defines a FastAPI
router that handles a specific domain of functionality.

All routers are registered in main.py's setup_routers() function.
"""

# Import all router modules to expose them
from . import agents
from . import ai
from . import auth
from . import automation
from . import billing
from . import browser
from . import challenges
from . import codegen
from . import connectors
from . import control_plane
from . import curriculum
from . import developer
from . import endpoints
from . import experiments
from . import extensions
from . import global_knowledge
from . import geography
from . import health
from . import improvements
from . import knowledge
from . import legacy
from . import media
from . import memory
from . import misc
from . import models
from . import monitoring
from . import multimodal
from . import platform_identity
from . import provider_status
from . import rbac
from . import research
from . import sandbox
from . import search
from . import stark
from . import system
from . import verification
from . import voice

__all__ = [
    "agents",
    "ai",
    "auth",
    "automation",
    "billing",
    "browser",
    "challenges",
    "codegen",
    "connectors",
    "control_plane",
    "curriculum",
    "developer",
    "endpoints",
    "experiments",
    "extensions",
    "global_knowledge",
    "geography",
    "health",
    "improvements",
    "knowledge",
    "legacy",
    "media",
    "memory",
    "misc",
    "models",
    "monitoring",
    "multimodal",
    "platform_identity",
    "provider_status",
    "rbac",
    "research",
    "sandbox",
    "search",
    "stark",
    "system",
    "verification",
    "voice",
]