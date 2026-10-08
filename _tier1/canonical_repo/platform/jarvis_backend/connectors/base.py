"""Connector base types and capability constants.

A connector is a credentialed integration (e.g. an IMAP+SMTP mailbox).  It
exposes two things to the rest of the system:

* ``capabilities``  — the consent set.  The AI may only ever perform actions
                      matching a capability that is enabled for the connector.
* ``actions``       — concrete operations supporting an LLM tool interface.

Both are registries (static declarations), enforced at dispatch time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Capabilities available on the mail connector (consent toggles in the UI).
CAP_READ = "read"          # list folders, search, read messages
CAP_SUMMARIZE = "summarize"  # structured digest/preview of mailbox
CAP_DRAFT = "draft"        # compose a draft (no send)
CAP_SEND = "send"          # send / reply (rate-limited, audited)

EMAIL_CAPABILITIES: List[str] = [CAP_READ, CAP_SUMMARIZE, CAP_DRAFT, CAP_SEND]
# Developer wants full autonomy by default -> everything on.  Flip any off.
DEFAULT_EMAIL_CAPABILITIES: List[str] = list(EMAIL_CAPABILITIES)


@dataclass(frozen=True)
class ActionSpec:
    """Static description of one connector action.

    ``risk_level`` and ``requires_confirmation`` drive the human-in-the-loop
    boundary (spec §23/§34/§40): HIGH/CRITICAL actions, or any action flagged
    ``requires_confirmation``, must be confirmed by the developer before the
    Connector executes them — the AI may propose the call but may never bypass
    the gate.
    """

    name: str
    capability: str
    summary: str
    params: Dict[str, List[str]] = field(default_factory=dict)
    risk_level: str = "LOW"  # LOW / MEDIUM / HIGH / CRITICAL
    requires_confirmation: bool = False


class ConnectorError(Exception):
    """Raised when a connector action fails with a user-facing message."""


class CapabilityDenied(Exception):
    """Raised when an action is not permitted by the connector's consent set."""


class Connector:
    """Base class for a single configurable integration."""

    kind: str = "base"
    label: str = "Base connector"

    #: capabilities statically possible; enforced against config.capabilities
    possible_capabilities: List[str] = []

    actions: List[ActionSpec] = []

    def __init__(self, config: dict) -> None:
        self.config = config or {}

    def capabilities(self) -> List[str]:
        return [c for c in (self.config.get("capabilities") or []) if c in self.possible_capabilities]

    def allows(self, capability: str) -> bool:
        return capability in self.capabilities()

    # ---- test -------------------------------------------------------------
    def test(self) -> Dict[str, Any]:
        """Live connectivity probe.  Returns ``{"ok": bool, "message": ...}``."""
        raise NotImplementedError

    # ---- action lookup ----------------------------------------------------
    def action_spec(self, name: str) -> Optional[ActionSpec]:
        for a in self.actions:
            if a.name == name:
                return a
        return None

    async def run_action(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError