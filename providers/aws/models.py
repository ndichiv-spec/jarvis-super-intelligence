"""AWS Bedrock model catalog (baseline declarative entries).

Ids reference real Bedrock foundation model ids. Live discovery
(``list_foundation_models``) is the runtime truth.
"""

from __future__ import annotations

from ..models import models_from_declared

AWS_MODELS = models_from_declared(
    "aws",
    [
        {
            "model": "anthropic.claude-sonnet-4-5",
            "name": "AWS Bedrock Claude Sonnet 4.5",
            "context_length": 1000000,
            "capabilities": "chat streaming tool_calling vision reasoning structured_output",
            "cost_class": "medium",
            "latency_class": "medium",
        },
        {
            "model": "anthropic.claude-opus-4-5",
            "name": "AWS Bedrock Claude Opus 4.5",
            "context_length": 1000000,
            "capabilities": "chat streaming tool_calling vision reasoning structured_output",
            "cost_class": "high",
            "latency_class": "medium",
        },
        {
            "model": "amazon.nova-pro-v1:0",
            "name": "Amazon Nova Pro",
            "context_length": 300000,
            "capabilities": "chat streaming tool_calling vision reasoning structured_output",
            "cost_class": "medium",
            "latency_class": "medium",
        },
        {
            "model": "amazon.nova-lite-v1:0",
            "name": "Amazon Nova Lite",
            "context_length": 300000,
            "capabilities": "chat streaming tool_calling vision structured_output",
            "cost_class": "low",
            "latency_class": "low",
        },
        {
            "model": "meta.llama3-3-70b-instruct-v1:0",
            "name": "Meta Llama 3.3 70B",
            "context_length": 131072,
            "capabilities": "chat streaming tool_calling structured_output",
            "cost_class": "medium",
            "latency_class": "medium",
        },
        {
            "model": "amazon.titan-embed-text-v2:0",
            "name": "Amazon Titan Text Embeddings v2",
            "context_length": 8192,
            "capabilities": "embeddings",
            "cost_class": "low",
            "latency_class": "low",
        },
    ],
)