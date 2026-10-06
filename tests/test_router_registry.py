"""
Tests for API Router Registration
=================================
"""

import pytest
from api.router_registry import get_all_routers, ROUTER_GROUPS, ROUTER_PREFIXES


class TestRouterRegistry:
    """Test router registry functionality."""

    def test_get_all_routers_returns_dict(self):
        """Test that get_all_routers returns a dictionary."""
        routers = get_all_routers()
        assert isinstance(routers, dict)
        assert len(routers) > 0

    def test_routers_have_required_endpoints(self):
        """Test that critical routers are registered."""
        routers = get_all_routers()

        # Core routers that should exist
        assert "health" in routers
        assert "system" in routers
        assert "ai" in routers
        assert "auth" in routers

    def test_router_prefixes_defined(self):
        """Test that router prefixes are defined."""
        assert "health" in ROUTER_PREFIXES
        assert "ai" in ROUTER_PREFIXES
        assert "auth" in ROUTER_PREFIXES

    def test_router_groups_defined(self):
        """Test that router groups are defined."""
        assert "core" in ROUTER_GROUPS
        assert "ai" in ROUTER_GROUPS
        assert "agents" in ROUTER_GROUPS
        assert "tiers" in ROUTER_GROUPS

    def test_router_prefixes_are_strings(self):
        """Test that all router prefixes are strings."""
        for name, prefix in ROUTER_PREFIXES.items():
            assert isinstance(prefix, str)

    def test_tier_routers_registered(self):
        """Test that tier routers are registered."""
        routers = get_all_routers()

        assert "tier1" in routers
        assert "tier2" in routers
        assert "tier3" in routers
        assert "tier4" in routers
        assert "tier5" in routers
