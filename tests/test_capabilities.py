"""
Tests for Core Capabilities
===========================
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock


class TestCapabilities:
    """Test capabilities module."""

    def test_get_capabilities_single_tier(self):
        """Test getting single tier capabilities."""
        from core.capabilities import get_capabilities

        tier1 = get_capabilities(tier=1)
        assert tier1 is not None

    def test_get_capabilities_invalid_tier(self):
        """Test invalid tier raises error."""
        from core.capabilities import get_capabilities

        with pytest.raises(ValueError):
            get_capabilities(tier=6)

    def test_get_capabilities_all_tiers(self):
        """Test getting all tier capabilities."""
        from core.capabilities import get_capabilities

        all_caps = get_capabilities()
        assert isinstance(all_caps, dict)
        assert len(all_caps) == 4  # Tiers 1-4 available

    def test_tier1_initialization(self):
        """Test Tier1Capabilities can be instantiated."""
        from core.tier1_integration import Tier1Capabilities

        tier1 = Tier1Capabilities()
        assert tier1 is not None
        assert tier1.vision_engine is None

    def test_tier2_initialization(self):
        """Test Tier2Capabilities can be instantiated."""
        from core.tier2_integration import Tier2Capabilities

        tier2 = Tier2Capabilities()
        assert tier2 is not None
        assert tier2.initialized == False


class TestArchitecture:
    """Test architecture module."""

    def test_jarvis_architecture_init(self):
        """Test JarvisArchitecture initialization."""
        from core.architecture import JarvisArchitecture

        arch = JarvisArchitecture()
        assert arch is not None
        assert len(arch.domains) > 0

    def test_domain_config(self):
        """Test domain configuration."""
        from core.architecture import DomainConfig

        config = DomainConfig(enabled=True)
        assert config.enabled == True

    def test_get_domain(self):
        """Test getting domain config."""
        from core.architecture import get_architecture

        arch = get_architecture()
        ai_domain = arch.get_domain("ai")
        assert ai_domain is not None
        assert ai_domain.enabled == True

    def test_enable_disable_domain(self):
        """Test enabling/disabling domains."""
        from core.architecture import get_architecture

        arch = get_architecture()
        arch.disable_domain("speech")
        assert arch.get_domain("speech").enabled == False

        arch.enable_domain("speech")
        assert arch.get_domain("speech").enabled == True

    def test_get_status(self):
        """Test getting architecture status."""
        from core.architecture import get_architecture

        arch = get_architecture()
        status = arch.get_status()
        assert isinstance(status, dict)
        assert "ai" in status
        assert "search" in status


class TestDomainMapper:
    """Test domain mapper module."""

    def test_tier_to_domain_mapping(self):
        """Test tier to domain mapping."""
        from core.domain_mapper import TIER_TO_DOMAIN, get_tier_domains

        assert 1 in TIER_TO_DOMAIN
        assert 2 in TIER_TO_DOMAIN

        domains = get_tier_domains(1)
        assert isinstance(domains, list)
        assert "ai" in domains

    def test_get_capabilities_for_domain(self):
        """Test getting capabilities for domain."""
        from core.domain_mapper import get_capabilities_for_domain

        caps = get_capabilities_for_domain("ai")
        assert caps is not None

    def test_invalid_domain(self):
        """Test invalid domain returns None."""
        from core.domain_mapper import get_capabilities_for_domain

        caps = get_capabilities_for_domain("invalid_domain")
        assert caps is None
