import inspect, os, sys
os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_ENV", "dev")
ROOT = r"F:\AI\Jarvis-super-intelligence-"
sys.path.insert(0, ROOT); os.chdir(ROOT)
from jarvis_backend.chat_service import ChatService
src = inspect.getsource(ChatService.stream_message)
print("=== ChatService.stream_message (", len(src.splitlines()), "lines) ===")
for i, l in enumerate(src.splitlines(), 1):
    print(f"{i:4d}| {l}")
