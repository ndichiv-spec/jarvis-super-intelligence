import py_compile, sys, time
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')
sys.path.insert(0, 'F:/AI')

f = "F:/AI/Jarvis-super-intelligence-/jarvis_backend/routers/system.py"
try:
    py_compile.compile(f, doraise=True)
    print("PY_COMPILE OK: system.py")
except py_compile.PyCompileError as e:
    print("PY_COMPILE FAIL:", e)
    sys.exit(1)

from jarvis_backend.routers.system import (
    router, _provider_settings_response, _PROVIDER_META, _BACKEND_START,
    _MODEL_CATALOG, _PROVIDER_KEYS, ProviderSettingsIn,
)
print("IMPORT OK | _MODEL_CATALOG=", len(_MODEL_CATALOG),
      "| _PROVIDER_KEYS=", len(_PROVIDER_KEYS),
      "| _PROVIDER_META=", len(_PROVIDER_META),
      "| ProviderSettingsIn fields=", len(ProviderSettingsIn.model_fields))

r = _provider_settings_response({'ollama_model': 'llama3', 'openai_api_key': 'secret-x', 'aws_region': 'us-east-1'})
assert set(r.keys()) == {"success", "settings", "providers", "env_file_exists", "env_path"}, r.keys()
assert r["success"] is True
assert set(r["settings"].keys()) == set(ProviderSettingsIn.model_fields.keys())
assert r["settings"]["openai_api_key"] is None
assert r["settings"]["ollama_model"] == "llama3"
assert r["settings"]["aws_region"] == "us-east-1"
assert r["providers"]["openai"]["configured"] is True
assert r["providers"]["google"]["configured"] is False
assert isinstance(r["env_file_exists"], bool)
print("ENVELOPE OK | openai masked=None, ollama_model=llama3 kept, configured flags real")
print("uptime baseline set:", round(time.time() - _BACKEND_START, 3), "ago")
print("ALL VERIFY CHECKS PASSED")
