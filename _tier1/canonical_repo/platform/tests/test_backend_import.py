from api.main import app as api_app
from api.main import create_application as api_factory
from core.api.main import app as core_api_app
from core.api.main import create_application as core_api_factory
from jarvis_backend.main import app as canonical_app


def test_legacy_imports_resolve_to_canonical_app():
    assert api_app is canonical_app
    assert core_api_app is canonical_app
    assert api_factory() is canonical_app
    assert core_api_factory() is canonical_app
