def test_silverwing_runtime_is_not_defaulted_to_core_loopback():
    from jarvis_runtime import _FALLBACK_DEFAULTS

    assert "SILVERWING_ENDPOINT" not in _FALLBACK_DEFAULTS
