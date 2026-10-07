"""Platform Model Gateway (Layer 3 -> Layer 2 boundary).

The AI platform talks to Silverwing ONLY through the gateway.  Components in
the platform (rooms, agents, tools) never call the model runtime or Transformer
directly:

    Room
      -> AI Platform
        -> Model Gateway   (authentication, routing, telemetry, fallback)
          -> Silverwing Runtime (/v1/chat/completions)
"""

from .brain_client import BrainClient
from .client import SilverwingClient
from .health import GatewayHealth, HealthLevel
from .models import GatewayError, GatewayModel, GatewayResponse

__all__ = [
    "BrainClient",
    "GatewayError",
    "GatewayHealth",
    "GatewayModel",
    "GatewayResponse",
    "HealthLevel",
    "SilverwingClient",
]
