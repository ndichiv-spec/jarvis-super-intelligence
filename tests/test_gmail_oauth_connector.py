"""Stage 1 — Gmail/Outlook connector action specs (static, no network).

Spec §23/§34/§40: ActionSpec carries risk_level + requires_confirmation. These
tests pin the Gmail/Outlook action matrix so a high-risk send can never be
demoted to LOW or stripped of its confirmation gate by accident.
"""
from __future__ import annotations

import os

os.environ.setdefault("JARVIS_SECRET_KEY", "stage1-test-secret-key-0123456789abcdef")
os.environ.setdefault("JARVIS_TEST_MODE", "1")

import pytest  # noqa: E402

from jarvis_backend.connectors.base import (  # noqa: E402
    CAP_DRAFT,
    CAP_READ,
    CAP_SEND,
    CAP_SUMMARIZE,
    ActionSpec,
)
from jarvis_backend.connectors.mail.gmail_oauth import GmailOAuthConnector  # noqa: E402
from jarvis_backend.connectors.mail.outlook_oauth import OutlookOAuthConnector  # noqa: E402


def _spec(connector, name):
    return connector({}).action_spec(name)


def test_gmail_action_matrix():
    assert _spec(GmailOAuthConnector, "gmail.search").risk_level == "LOW"
    assert _spec(GmailOAuthConnector, "gmail.read").risk_level == "LOW"
    assert _spec(GmailOAuthConnector, "gmail.summarize").risk_level == "LOW"
    assert _spec(GmailOAuthConnector, "gmail.draft").risk_level == "MEDIUM"
    assert _spec(GmailOAuthConnector, "gmail.draft").requires_confirmation is False
    send = _spec(GmailOAuthConnector, "gmail.send")
    assert send.risk_level == "HIGH"
    assert send.requires_confirmation is True
    assert send.capability == CAP_SEND
    reply = _spec(GmailOAuthConnector, "gmail.reply")
    assert reply.risk_level == "HIGH" and reply.requires_confirmation is True


def test_outlook_action_matrix():
    assert _spec(OutlookOAuthConnector, "outlook.search").risk_level == "LOW"
    assert _spec(OutlookOAuthConnector, "outlook.read").risk_level == "LOW"
    assert _spec(OutlookOAuthConnector, "outlook.summarize").risk_level == "LOW"
    assert _spec(OutlookOAuthConnector, "outlook.draft").risk_level == "MEDIUM"
    assert _spec(OutlookOAuthConnector, "outlook.draft").requires_confirmation is False
    send = _spec(OutlookOAuthConnector, "outlook.send")
    assert send.risk_level == "HIGH"
    assert send.requires_confirmation is True
    reply = _spec(OutlookOAuthConnector, "outlook.reply")
    assert reply.risk_level == "HIGH" and reply.requires_confirmation is True


def test_gmail_capabilities_registered():
    assert GmailOAuthConnector.possible_capabilities == [CAP_READ, CAP_SUMMARIZE, CAP_DRAFT, CAP_SEND]
    assert OutlookOAuthConnector.possible_capabilities == [CAP_READ, CAP_SUMMARIZE, CAP_DRAFT, CAP_SEND]


def test_gmail_unknown_action_returns_none():
    assert _spec(GmailOAuthConnector, "gmail.nope") is None


def test_action_spec_defaults_and_frozen():
    s = ActionSpec("x", "read", "does a thing")
    assert s.risk_level == "LOW"
    assert s.requires_confirmation is False
    # frozen dataclass: mutation must fail
    with pytest.raises(Exception):
        s.risk_level = "HIGH"  # type: ignore[misc]
