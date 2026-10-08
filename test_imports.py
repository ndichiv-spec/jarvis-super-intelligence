import sys
sys.path.insert(0, r'F:\AI\Jarvis-super-intelligence-')
# Test imports
from jarvis_backend.routers.ai import ai_process, ai_status, _probe_silverwing_chat
print('OK: ai.py imports successfully')
from jarvis_backend.gateway import ProviderGateway, provider_gateway
print('OK: gateway.py imports successfully')
from jarvis_backend.chat_service import chat_service
print('OK: chat_service.py imports successfully')
print(f'ProviderGateway.timeout = {provider_gateway.timeout}')
# Check if stream_chat accepts messages parameter
import inspect
sig = inspect.signature(provider_gateway.stream_chat)
params = list(sig.parameters.keys())
print(f'stream_chat params: {params}')
print(f'Has messages param: {"messages" in params}')
