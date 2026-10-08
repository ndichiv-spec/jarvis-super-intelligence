"""Silverwing Runtime - the dedicated model inference runtime.

LAYER 2 of the Silverwing architecture:

    LAYER 1  Neural Core      silverwing/            (training, tokenizer)
    LAYER 2  Model Runtime    silverwing-runtime/    (inference, serving)
    LAYER 3  AI Platform      jarvis_backend + backend/model_gateway/

The runtime is the ONLY component allowed to download and cache model
weights.  It loads weights from durable external storage, verifies hashes,
and serves an OpenAI-compatible inference API.

The core package is framework-independent: torch/transformers are optional
and only used by the configurable :class:`silverwing_runtime.inference.TorchBackend`.
"""

__version__ = "0.1.0"
