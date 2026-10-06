from jarvis_backend.main import app


def test_backend_imports_canonical_application():
    assert app.title == "JARVIS Unified System"
