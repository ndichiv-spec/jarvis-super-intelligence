"""AWS Bedrock provider adapter (spec §8).

Bedrock Runtime (Converse/Invoke), model discovery, knowledge services and future
AgentCore integrations. Credentials honor ``JARVIS_AWS_REGION`` +
``JARVIS_AWS_ACCESS_MODE`` (env/profile/sso/federated -> short-lived creds where
possible, never static keys by default). Testable via an injected clients object.
"""

from .capabilities import AWS_ADAPTER_CAPABILITIES
from .client import AwsBedrockAdapter
from .config import AwsConfig
from .health import aws_health_probe
from .models import AWS_MODELS

MODELS = AWS_MODELS
CAPABILITIES = AWS_ADAPTER_CAPABILITIES
ADAPTER = AwsBedrockAdapter

__all__ = [
    "ADAPTER",
    "CAPABILITIES",
    "MODELS",
    "AwsBedrockAdapter",
    "AwsConfig",
    "aws_health_probe",
]