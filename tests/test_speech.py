"""
Tests for Speech Module
========================
"""

import pytest
from unittest.mock import Mock, patch


class TestSpeechModule:
    """Test speech module imports and basic functionality."""

    def test_speech_unified_import(self):
        """Test unified speech module can be imported."""
        from core.speech_unified import speak, get_available_voices

        assert speak is not None
        assert get_available_voices is not None

    def test_speech_functions_exported(self):
        """Test speech functions are exported."""
        from core.speech import (
            speak,
            get_available_voices,
            list_voice_profiles,
            save_voice_profile,
            load_voice_profile,
            apply_voice_profile,
            listen_from_microphone,
            transcribe_file,
        )

        # All should be callable
        assert callable(speak)
        assert callable(get_available_voices)


class TestVoiceInterface:
    """Test voice interface module."""

    def test_voice_interface_import(self):
        """Test voice interface can be imported."""
        from core.voice_interface import VoiceInterface

        vi = VoiceInterface()
        assert vi is not None

    def test_voice_gateway_import(self):
        """Test voice gateway can be imported."""
        from core.voice_gateway import VoiceGateway

        vg = VoiceGateway()
        assert vg is not None


class TestSpeechAPI:
    """Test speech API endpoints."""

    @pytest.mark.asyncio
    async def test_voice_status(self, test_client):
        """Test voice status endpoint."""
        response = await test_client.get("/api/v1/voice/status")
        assert response.status_code in [200, 404]


class TestAudioEngine:
    """Test audio engine module."""

    def test_audio_engine_import(self):
        """Test audio engine can be imported."""
        from core.audio_engine import AudioEngine

        ae = AudioEngine()
        assert ae is not None
