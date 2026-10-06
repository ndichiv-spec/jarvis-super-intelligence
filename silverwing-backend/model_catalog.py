"""Comprehensive catalogue of modern foundation models available to Silverwing.

This module is the single source of truth for *every* model the system can
route to.  It is split into two parts:

1. ``MODEL_CATALOG`` – a flat, fully-keyed dictionary of :class:`ModelInfo`
   entries keyed by ``"provider:model_id"``.  Each entry carries enough
   metadata (context window, capabilities, pricing, open-weights flag,
   canonical serving endpoints) for the model-manager to make routing
   decisions and for the frontend / Observatory to display provider status.

2. ``PROVIDER_PROFILES`` – static configuration snippets for each provider
   (endpoint, auth env-var, lazy-import module) so that
   :mod:`model_provider` and :mod:`main` can stay in sync without
   duplicating the information.

The catalog is deliberately *static* (a Python data table, not scraped at
runtime).  It is refreshed alongside each Silverwing release after a quick
sweep of the provider docs.  See the header of ``MODEL_CATALOG`` below for
the last-researched date.

All model IDs here use the *canonical* names from each vendor's API, so
they can be passed straight to the relevant SDK.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class PricingInfo(BaseModel):
    """Pricing for a model (per 1 M tokens), when published."""
    input_per_1m: Optional[float] = None   # USD per 1 M input tokens
    output_per_1m: Optional[float] = None  # USD per 1 M output tokens
    currency: str = "USD"
    free_tier: bool = False  # has a free / generous free tier
    note: Optional[str] = None  # e.g. "pay-per-use" / "contact sales"


class ModelInfo(BaseModel):
    """Metadata for a single foundation model."""
    provider: str
    model_id: str
    family: str
    name: str
    description: str = ""
    context_length: Optional[int] = None        # tokens
    max_output_tokens: Optional[int] = None     # tokens
    capabilities: List[str] = Field(default_factory=list)
    # Tags from {reasoning, coding, vision, tool-use, multilingual, audio,
    #            embeddings, image-gen, multilingual}
    pricing: Optional[PricingInfo] = None
    open_weights: bool = False     # can be self-hosted (HF / llama.cpp / etc.)
    free_tier: bool = False
    status: str = "stable"          # stable | preview | deprecated
    knowledge_cutoff: Optional[str] = None
    release_date: Optional[str] = None
    # Canonical serving endpoints that carry this model:
    #   {"openai": "gpt-5.6-sol", "bedrock": "...", "groq": "...", ...}
    serving: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider profiles
# ---------------------------------------------------------------------------
# Maps a Silverwing provider name to its static configuration.
# Used by ``model_provider.ModelConfig`` and ``backend/main.py`` to know which
# SDK module to lazily import and which env var holds the credential.

class ProviderProfile(BaseModel):
    name: str
    sdk_module: str           # lazily-imported module name (used by _sdk_available)
    sdk_package: str          # pip package name for requirements
    auth_env: str             # environment variable holding the API key / config
    auth_desc: str
    base_url_env: Optional[str] = None  # override if the provider uses a custom host
    default_model: str


PROVIDER_PROFILES: Dict[str, ProviderProfile] = {
    "openai": ProviderProfile(
        name="openai",
        sdk_module="openai",
        sdk_package="openai>=1.13.0",
        auth_env="OPENAI_API_KEY",
        auth_desc="OpenAI API key",
        default_model="gpt-5.6-sol",
    ),
    "anthropic": ProviderProfile(
        name="anthropic",
        sdk_module="anthropic",
        sdk_package="anthropic>=0.40.0",
        auth_env="ANTHROPIC_API_KEY",
        auth_desc="Anthropic API key",
        default_model="claude-opus-5",
    ),
    "google": ProviderProfile(
        name="google",
        sdk_module="google.genai",
        sdk_package="google-genai>=2.22.0",
        auth_env="GEMINI_API_KEY",
        auth_desc="Google API key (or GOOGLE_API_KEY)",
        default_model="gemini-2.5-pro",
    ),
    "deepseek": ProviderProfile(
        name="deepseek",
        sdk_module="openai",  # DeepSeek uses the OpenAI-compatible SDK
        sdk_package="openai>=1.13.0",  # same SDK, different base_url
        auth_env="DEEPSEEK_API_KEY",
        auth_desc="DeepSeek API key",
        base_url_env="DEEPSEEK_API_BASE",
        default_model="deepseek-chat",
    ),
    "groq": ProviderProfile(
        name="groq",
        sdk_module="groq",
        sdk_package="groq>=0.6.0",
        auth_env="GROQ_API_KEY",
        auth_desc="Groq API key",
        default_model="llama-3.3-70b-versatile",
    ),
    "ollama": ProviderProfile(
        name="ollama",
        sdk_module="ollama",
        sdk_package="ollama>=0.2.0",
        auth_env="OLLAMA_HOST",
        auth_desc="Ollama server URL (no auth needed)",
        base_url_env="OLLAMA_HOST",
        default_model="llama3.3:70b",
    ),
    "llamacpp": ProviderProfile(
        name="llamacpp",
        sdk_module="openai",  # llama.cpp server is OpenAI-compatible
        sdk_package="llama-cpp-python>=0.2.0",
        auth_env="LLAMACPP_API_BASE",
        auth_desc="llama.cpp server URL (e.g. http://127.0.0.1:8080)",
        base_url_env="LLAMACPP_API_BASE",
        default_model="Qwen3-32B-Instruct-Q4_K_M.gguf",
    ),
    "bedrock": ProviderProfile(
        name="bedrock",
        sdk_module="boto3",
        sdk_package="boto3>=1.34.0",
        auth_env="AWS_PROFILE",
        auth_desc="AWS credentials (profile / env vars)",
        default_model="anthropic.claude-opus-5",
    ),
    "vertex": ProviderProfile(
        name="vertex",
        sdk_module="google.cloud.aiplatform",
        sdk_package="google-cloud-aiplatform>=1.71.0",
        auth_env="GOOGLE_APPLICATION_CREDENTIALS",
        auth_desc="GCP service-account key path or ADC",
        default_model="publishers/google/models/gemini-2.5-pro",
    ),
    "local": ProviderProfile(
        name="local",
        sdk_module="",
        sdk_package="",
        auth_env="",
        auth_desc="Deterministic local echo (no credentials)",
        default_model="local-rule",
    ),
    "silverwing": ProviderProfile(
        name="silverwing",
        sdk_module="",
        sdk_package="",
        auth_env="SILVERWING_SERVER_URL",
        auth_desc="Silverwing native inference server (optional)",
        default_model="silverwing-120m-base-v1",
    ),
    "vllm": ProviderProfile(
        name="vllm",
        sdk_module="openai",  # vLLM serves OpenAI-compatible API
        sdk_package="vllm",
        auth_env="VLLM_API_BASE",
        auth_desc="vLLM OpenAI-compatible server URL",
        base_url_env="VLLM_API_BASE",
        default_model="default",
    ),
}


# ---------------------------------------------------------------------------
# Master model catalogue
# ---------------------------------------------------------------------------
# Keyed by "provider:model_id".  Values are ModelInfo records.
# Last researched: 2026-09 (sources: openai.com/platform, anthropic.com,
# ai.google.dev, console.groq.com/docs, docs.aws.amazon.com/bedrock,
# huggingface.co/meta-llama + qwen + deepseek-ai).

MODEL_CATALOG: Dict[str, ModelInfo] = {
    # =================================================================
    # OpenAI
    # =================================================================
    "openai:gpt-5.6-sol": ModelInfo(
        provider="openai", model_id="gpt-5.6-sol", family="GPT-5.6", name="GPT-5.6 Sol",
        description="Frontier reasoning model — highest quality across coding, math, and complex agentic tasks.",
        context_length=2_000_000, max_output_tokens=32_768,
        capabilities=["reasoning", "coding", "vision", "tool-use", "multilingual"],
        pricing=PricingInfo(input_per_1m=15.0, output_per_1m=60.0,
                             note="pay-per-use"),
        status="stable", knowledge_cutoff="Jun 2026", release_date="2026-04",
        serving={"openai": "gpt-5.6-sol", "bedrock": "gpt-5.6-sol",
                 "vertex": "publishers/openai/models/gpt-5.6-sol"},
    ),
    "openai:gpt-5.6-terra": ModelInfo(
        provider="openai", model_id="gpt-5.6-terra", family="GPT-5.6", name="GPT-5.6 Terra",
        description="Cost-optimised reasoning model — trades peak reasoning for lower latency and cost.",
        context_length=2_000_000, max_output_tokens=32_768,
        capabilities=["reasoning", "coding", "tool-use", "multilingual"],
        pricing=PricingInfo(input_per_1m=3.0, output_per_1m=12.0),
        status="stable", knowledge_cutoff="Jun 2026", release_date="2026-04",
        serving={"openai": "gpt-5.6-terra", "bedrock": "gpt-5.6-terra"},
    ),
    "openai:gpt-5.6-luna": ModelInfo(
        provider="openai", model_id="gpt-5.6-luna", family="GPT-5.6", name="GPT-5.6 Luna",
        description="Multilingual-specialised variant with improved non-English reasoning.",
        context_length=2_000_000, max_output_tokens=16_384,
        capabilities=["reasoning", "multilingual"],
        pricing=PricingInfo(input_per_1m=4.0, output_per_1m=16.0),
        status="stable", knowledge_cutoff="Jun 2026", release_date="2026-04",
        serving={"openai": "gpt-5.6-luna"},
    ),
    "openai:gpt-5.5": ModelInfo(
        provider="openai", model_id="gpt-5.5", family="GPT-5.5", name="GPT-5.5",
        description="Previous-generation flagship — solid all-rounder with high throughput.",
        context_length=1_000_000, max_output_tokens=16_384,
        capabilities=["reasoning", "coding", "vision", "tool-use"],
        pricing=PricingInfo(input_per_1m=6.0, output_per_1m=24.0),
        status="stable", knowledge_cutoff="Feb 2026",
        serving={"openai": "gpt-5.5", "bedrock": "gpt-5.5"},
    ),
    "openai:gpt-5.4": ModelInfo(
        provider="openai", model_id="gpt-5.4", family="GPT-5.4", name="GPT-5.4",
        description="Efficient mid-tier model for high-throughput applications.",
        context_length=1_000_000, max_output_tokens=16_384,
        capabilities=["coding", "tool-use"],
        pricing=PricingInfo(input_per_1m=2.5, output_per_1m=10.0),
        status="stable", knowledge_cutoff="Dec 2025",
        serving={"openai": "gpt-5.4", "bedrock": "gpt-5.4"},
    ),
    "openai:gpt-oss-120b": ModelInfo(
        provider="openai", model_id="gpt-oss-120b", family="GPT-OSS", name="GPT-OSS 120B",
        description="Open-weight reasoning model (120 B params) — freely downloadable and self-hostable.",
        context_length=131_072, max_output_tokens=16_384,
        capabilities=["reasoning", "coding", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.15, output_per_1m=0.60,
                             note="also free to self-host via HuggingFace"),
        open_weights=True, free_tier=True,
        status="stable", knowledge_cutoff="Jul 2025",
        serving={"openai": "gpt-oss-120b", "bedrock": "gpt-oss-120b",
                 "groq": "openai/gpt-oss-120b",
                 "huggingface": "openai/gpt-oss-120b"},
    ),
    "openai:gpt-oss-20b": ModelInfo(
        provider="openai", model_id="gpt-oss-20b", family="GPT-OSS", name="GPT-OSS 20B",
        description="Lightweight open-weight model (20 B params) for fast, cheap reasoning.",
        context_length=131_072, max_output_tokens=16_384,
        capabilities=["coding", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.075, output_per_1m=0.30),
        open_weights=True, free_tier=True,
        status="stable", knowledge_cutoff="Jul 2025",
        serving={"openai": "gpt-oss-20b", "bedrock": "gpt-oss-20b",
                 "groq": "openai/gpt-oss-20b",
                 "huggingface": "openai/gpt-oss-20b"},
    ),
    "openai:gpt-4.1-mini": ModelInfo(
        provider="openai", model_id="gpt-4.1-mini", family="GPT-4.1", name="GPT-4.1 Mini",
        description="Balanced cost/performance predecessor to GPT-5; reliable workhorse.",
        context_length=1_000_000, max_output_tokens=16_384,
        capabilities=["coding", "tool-use", "vision"],
        pricing=PricingInfo(input_per_1m=0.40, output_per_1m=1.60, free_tier=True),
        status="stable", knowledge_cutoff="Oct 2024",
        serving={"openai": "gpt-4.1-mini"},
    ),

    # =================================================================
    # Anthropic Claude
    # =================================================================
    "anthropic:claude-fable-5-1": ModelInfo(
        provider="anthropic", model_id="claude-fable-5-1", family="Claude 5", name="Claude Fable 5.1",
        description="Anthropic's most capable model for demanding reasoning and long-horizon agentic work.",
        context_length=1_000_000, max_output_tokens=128_000,
        capabilities=["reasoning", "coding", "vision", "tool-use", "multilingual"],
        pricing=PricingInfo(input_per_1m=10.0, output_per_1m=50.0),
        status="stable", knowledge_cutoff="Jun 2026", release_date="2026-04",
        serving={"anthropic": "claude-fable-5-1", "bedrock": "claude-fable-5-1"},
    ),
    "anthropic:claude-opus-5": ModelInfo(
        provider="anthropic", model_id="claude-opus-5", family="Claude 5", name="Claude Opus 5",
        description="High-end reasoning model for complex agentic coding and enterprise work.",
        context_length=1_000_000, max_output_tokens=128_000,
        capabilities=["reasoning", "coding", "vision", "tool-use", "multilingual"],
        pricing=PricingInfo(input_per_1m=5.0, output_per_1m=25.0),
        status="stable", knowledge_cutoff="May 2026",
        serving={"anthropic": "claude-opus-5", "bedrock": "claude-opus-5"},
    ),
    "anthropic:claude-sonnet-5": ModelInfo(
        provider="anthropic", model_id="claude-sonnet-5", family="Claude 5", name="Claude Sonnet 5",
        description="Best speed-and-intelligence balance for most workloads.",
        context_length=1_000_000, max_output_tokens=128_000,
        capabilities=["coding", "tool-use", "vision", "multilingual"],
        pricing=PricingInfo(input_per_1m=2.0, output_per_1m=10.0),
        status="stable", knowledge_cutoff="Jan 2026",
        serving={"anthropic": "claude-sonnet-5", "bedrock": "claude-sonnet-5"},
    ),
    "anthropic:claude-haiku-4-5": ModelInfo(
        provider="anthropic", model_id="claude-haiku-4-5", family="Claude 4", name="Claude Haiku 4.5",
        description="Fastest, most cost-effective Claude with near-frontier intelligence.",
        context_length=200_000, max_output_tokens=64_000,
        capabilities=["tool-use", "coding"],
        pricing=PricingInfo(input_per_1m=1.0, output_per_1m=5.0),
        status="stable", knowledge_cutoff="Feb 2025",
        serving={"anthropic": "claude-haiku-4-5", "bedrock": "claude-haiku-4-5"},
    ),
    "anthropic:claude-3-5-sonnet-20241022": ModelInfo(
        provider="anthropic", model_id="claude-3-5-sonnet-20241022", family="Claude 3", name="Claude 3.5 Sonnet (legacy)",
        description="Legacy high-throughput model, useful when cost is the primary constraint.",
        context_length=200_000, max_output_tokens=8_192,
        capabilities=["coding", "tool-use", "vision"],
        pricing=PricingInfo(input_per_1m=0.30, output_per_1m=1.50),
        status="deprecated", knowledge_cutoff="Apr 2024",
        serving={"anthropic": "claude-3-5-sonnet-20241022", "bedrock": "claude-3-5-sonnet-20241022"},
    ),

    # =================================================================
    # Google Gemini
    # =================================================================
    "google:gemini-2.5-pro": ModelInfo(
        provider="google", model_id="gemini-2.5-pro", family="Gemini 2.5", name="Gemini 2.5 Pro",
        description="Most advanced Gemini model for complex reasoning, coding, and multimodal tasks.",
        context_length=1_000_000, max_output_tokens=64_000,
        capabilities=["reasoning", "coding", "vision", "tool-use", "multilingual"],
        pricing=PricingInfo(input_per_1m=1.75, output_per_1m=7.00, free_tier=True),
        status="stable", knowledge_cutoff="May 2026",
        serving={"google": "gemini-2.5-pro", "bedrock": "gemini-2.5-pro",
                 "vertex": "publishers/google/models/gemini-2.5-pro"},
    ),
    "google:gemini-2.5-flash": ModelInfo(
        provider="google", model_id="gemini-2.5-flash", family="Gemini 2.5", name="Gemini 2.5 Flash",
        description="Best price/performance for low-latency, high-volume reasoning tasks.",
        context_length=1_000_000, max_output_tokens=64_000,
        capabilities=["reasoning", "coding", "vision", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.60, output_per_1m=2.40, free_tier=True),
        status="stable", knowledge_cutoff="May 2026",
        serving={"google": "gemini-2.5-flash", "bedrock": "gemini-2.5-flash",
                 "vertex": "publishers/google/models/gemini-2.5-flash"},
    ),
    "google:gemini-2.5-flash-lite": ModelInfo(
        provider="google", model_id="gemini-2.5-flash-lite", family="Gemini 2.5", name="Gemini 2.5 Flash-Lite",
        description="Fastest, most budget-friendly multimodal model in the 2.5 family.",
        context_length=1_000_000, max_output_tokens=8_192,
        capabilities=["vision", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.20, output_per_1m=0.80, free_tier=True),
        status="stable", knowledge_cutoff="May 2026",
        serving={"google": "gemini-2.5-flash-lite", "bedrock": "gemini-2.5-flash-lite"},
    ),
    "google:gemini-3.8-flash": ModelInfo(
        provider="google", model_id="gemini-3.8-flash", family="Gemini 3", name="Gemini 3.8 Flash",
        description="Latest-generation Flash model for long-horizon software engineering and autonomous agents.",
        context_length=2_000_000, max_output_tokens=64_000,
        capabilities=["coding", "vision", "tool-use", "multilingual"],
        pricing=PricingInfo(input_per_1m=1.00, output_per_1m=4.00),
        status="stable", knowledge_cutoff="Jun 2026", release_date="2026-09",
        serving={"google": "gemini-3.8-flash", "bedrock": "gemini-3.8-flash"},
    ),
    "google:gemini-3.7-flash": ModelInfo(
        provider="google", model_id="gemini-3.7-flash", family="Gemini 3", name="Gemini 3.7 Flash",
        description="Previous-generation Flash model for complex coding and agentic workflows.",
        context_length=1_000_000, max_output_tokens=64_000,
        capabilities=["coding", "tool-use", "vision"],
        pricing=PricingInfo(input_per_1m=0.75, output_per_1m=3.00),
        status="stable", knowledge_cutoff="Apr 2026",
        serving={"google": "gemini-3.7-flash", "bedrock": "gemini-3.7-flash"},
    ),
    "google:gemma-4-27b": ModelInfo(
        provider="google", model_id="gemma-4-27b", family="Gemma 4", name="Gemma 4 27B",
        description="Open lightweight multimodal model from Google; fully open-weights, self-hostable.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["vision", "multilingual"],
        pricing=PricingInfo(free_tier=True),
        open_weights=True, free_tier=True, status="stable",
        serving={"google": "gemma-4-27b", "bedrock": "gemma-4-27b",
                 "huggingface": "google/gemma-4-27b"},
    ),

    # =================================================================
    # DeepSeek
    # =================================================================
    "deepseek:deepseek-v4-pro": ModelInfo(
        provider="deepseek", model_id="deepseek-v4-pro", family="DeepSeek-V4", name="DeepSeek V4 Pro",
        description="DeepSeek's latest agent-focused model with Responses-API and Codex-style tool use.",
        context_length=64_000, max_output_tokens=8_192,
        capabilities=["reasoning", "coding", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.14, output_per_1m=0.28, free_tier=True),
        status="stable", knowledge_cutoff="Jul 2025", release_date="2026-09",
        serving={"deepseek": "deepseek-v4-pro", "bedrock": "deepseek-v4-pro",
                 "groq": "deepseek/deepseek-v4-pro"},
    ),
    "deepseek:deepseek-chat": ModelInfo(
        provider="deepseek", model_id="deepseek-chat", family="DeepSeek-V3", name="DeepSeek V3 Chat",
        description="General-purpose chat and reasoning model; free tier with generous limits.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["reasoning", "coding", "multilingual"],
        pricing=PricingInfo(input_per_1m=0.14, output_per_1m=0.28, free_tier=True),
        status="stable", knowledge_cutoff="Jul 2025",
        serving={"deepseek": "deepseek-chat", "bedrock": "deepseek-v3"},
    ),
    "deepseek:deepseek-reasoner": ModelInfo(
        provider="deepseek", model_id="deepseek-reasoner", family="DeepSeek-R1", name="DeepSeek R1",
        description="Reasoning-specialised model; strong at math and logic.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["reasoning", "coding", "multilingual"],
        pricing=PricingInfo(input_per_1m=0.28, output_per_1m=2.10, free_tier=True),
        open_weights=True, free_tier=True, status="stable",
        serving={"deepseek": "deepseek-reasoner",
                 "huggingface": "deepseek-ai/DeepSeek-R1"},
    ),
    "deepseek:deepseek-coder": ModelInfo(
        provider="deepseek", model_id="deepseek-coder", family="DeepSeek", name="DeepSeek Coder",
        description="Code-specialised variant of DeepSeek V3.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["coding", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.14, output_per_1m=0.28),
        status="stable", knowledge_cutoff="Jul 2025",
        serving={"deepseek": "deepseek-coder"},
    ),

    # =================================================================
    # Meta Llama 4
    # =================================================================
    "ollama:llama4-scout": ModelInfo(
        provider="ollama", model_id="llama4-scout", family="Llama 4", name="Llama 4 Scout",
        description="109 B param MoE model (16 experts) — efficient reasoning and coding.",
        context_length=512_000, max_output_tokens=16_384,
        capabilities=["coding", "multilingual", "tool-use"],
        pricing=PricingInfo(free_tier=True),
        open_weights=True, free_tier=True, status="stable", release_date="2025-04",
        serving={"ollama": "llama4:scout", "llamacpp": "llama-4-scout",
                 "huggingface": "meta-llama/Llama-4-Scout",
                 "bedrock": "llama4-scout"},
    ),
    "ollama:llama4-maverick": ModelInfo(
        provider="ollama", model_id="llama4-maverick", family="Llama 4", name="Llama 4 Maverick",
        description="402 B param MoE model (128 experts) — highest Llama-4 quality, agentic coding.",
        context_length=1_000_000, max_output_tokens=16_384,
        capabilities=["reasoning", "coding", "vision", "multilingual"],
        pricing=PricingInfo(free_tier=True),
        open_weights=True, free_tier=True, status="stable", release_date="2025-07",
        serving={"ollama": "llama4:maverick", "llamacpp": "llama-4-maverick",
                 "huggingface": "meta-llama/Llama-4-Maverick",
                 "bedrock": "llama4-maverick"},
    ),
    "bedrock:anthropic.claude-opus-5": ModelInfo(
        provider="bedrock", model_id="anthropic.claude-opus-5-v1:0", family="Claude 5", name="Claude Opus 5 (Bedrock)",
        description="Anthropic's Claude 5 Opus high-end reasoning model served via AWS Bedrock Converse API.",
        context_length=1_000_000, max_output_tokens=128_000,
        capabilities=["reasoning", "coding", "vision", "tool-use", "multilingual"],
        pricing=PricingInfo(note="Bedrock pricing; see aws.amazon.com/bedrock/pricing"),
        status="stable", knowledge_cutoff="May 2026",
        serving={"bedrock": "anthropic.claude-opus-5-v1:0"},
    ),
    "bedrock:anthropic.claude-fable-5-1": ModelInfo(
        provider="bedrock", model_id="anthropic.claude-fable-5-1-v1:0", family="Claude 5", name="Claude Fable 5.1 (Bedrock)",
        description="Anthropic's most capable model via AWS Bedrock.",
        context_length=1_000_000, max_output_tokens=128_000,
        capabilities=["reasoning", "coding", "vision", "tool-use"],
        pricing=PricingInfo(note="Bedrock pricing; see aws.amazon.com/bedrock/pricing"),
        status="stable", knowledge_cutoff="Jun 2026",
        serving={"bedrock": "anthropic.claude-fable-5-1-v1:0"},
    ),
    "bedrock:anthropic.claude-sonnet-5": ModelInfo(
        provider="bedrock", model_id="anthropic.claude-sonnet-5-v1:0", family="Claude 5", name="Claude Sonnet 5 (Bedrock)",
        description="Cost-efficient Claude 5 via AWS Bedrock.",
        context_length=1_000_000, max_output_tokens=128_000,
        capabilities=["coding", "tool-use", "vision"],
        pricing=PricingInfo(note="Bedrock pricing; see aws.amazon.com/bedrock/pricing"),
        status="stable", knowledge_cutoff="Jan 2026",
        serving={"bedrock": "anthropic.claude-sonnet-5-v1:0"},
    ),
    "bedrock:meta.llama-v4-scout": ModelInfo(
        provider="bedrock", model_id="meta.llama-v4-scout-17b-instruct", family="Llama 4", name="Llama 4 Scout (Bedrock)",
        description="Llama 4 Scout via Bedrock Inference Profiles.",
        context_length=512_000, max_output_tokens=16_384,
        capabilities=["coding", "multilingual"],
        pricing=PricingInfo(input_per_1m=0.30, output_per_1m=0.60, note="Bedrock pricing"),
        status="stable",
        serving={"bedrock": "meta.llama-v4-scout-17b-instruct"},
    ),
    "bedrock:meta.llama-v4-maverick": ModelInfo(
        provider="bedrock", model_id="meta.llama-v4-maverick-402b-instruct", family="Llama 4", name="Llama 4 Maverick (Bedrock)",
        description="Llama 4 Maverick 402 B via Bedrock Inference Profiles.",
        context_length=1_000_000, max_output_tokens=16_384,
        capabilities=["reasoning", "coding", "vision", "multilingual"],
        pricing=PricingInfo(input_per_1m=2.19, output_per_1m=4.40, note="Bedrock pricing"),
        status="stable",
        serving={"bedrock": "meta.llama-v4-maverick-402b-instruct"},
    ),

    # =================================================================
    # Qwen
    # =================================================================
    "groq:qwen-qwen3.8-27b": ModelInfo(
        provider="groq", model_id="qwen/qwen3.8-27b", family="Qwen 3.8", name="Qwen3.8 27B",
        description="Latest Qwen multimodal model with 2.4 T params; strong coding and vision.",
        context_length=131_072, max_output_tokens=16_384,
        capabilities=["coding", "vision", "multilingual", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.80, output_per_1m=4.00),
        status="stable",
        serving={"groq": "qwen/qwen3.8-27b", "bedrock": "qwen3.8-27b",
                 "huggingface": "Qwen/Qwen3.8-27B"},
    ),
    "groq:qwen-qwen3.6-27b": ModelInfo(
        provider="groq", model_id="qwen/qwen3.6-27b", family="Qwen 3.6", name="Qwen3.6 27B",
        description="Previous-generation Qwen multimodal model.",
        context_length=131_072, max_output_tokens=16_384,
        capabilities=["vision", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.60, output_per_1m=3.00),
        status="stable",
        serving={"groq": "qwen/qwen3.6-27b"},
    ),
    "bedrock:qwen3-235b-a22b": ModelInfo(
        provider="bedrock", model_id="qwen3-235b-a22b-2507", family="Qwen 3", name="Qwen3 235B A22B",
        description="Qwen's largest sparse-mixture model via Bedrock; excellent reasoning and coding.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["reasoning", "coding", "multilingual"],
        pricing=PricingInfo(input_per_1m=1.20, output_per_1m=4.80, note="Bedrock pricing"),
        status="stable",
        serving={"bedrock": "qwen3-235b-a22b-2507", "huggingface": "Qwen/Qwen3-235B-A22B-2507"},
    ),
    "bedrock:qwen3-coder-480b": ModelInfo(
        provider="bedrock", model_id="qwen3-coder-480b-a35b-instruct", family="Qwen 3", name="Qwen3 Coder 480B",
        description="Qwen's code-specialised Mixture-of-Experts model, available on Bedrock.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["coding", "tool-use"],
        pricing=PricingInfo(free_tier=True, note="preview / free tier"),
        open_weights=True, free_tier=True,
        status="preview",
        serving={"bedrock": "qwen3-coder-480b-a35b-instruct", "huggingface": "Qwen/Qwen3-Coder-480B-A35B-Instruct"},
    ),

    # =================================================================
    # Groq production models
    # =================================================================
    "groq:llama-3.3-70b-versatile": ModelInfo(
        provider="groq", model_id="llama-3.3-70b-versatile", family="Llama 3.3", name="Llama 3.3 70B",
        description="Meta Llama 3.3 70 B — strong all-rounder via Groq's fast inference.",
        context_length=131_072, max_output_tokens=32_768,
        capabilities=["coding", "multilingual", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.05, output_per_1m=0.10, free_tier=True),
        open_weights=True, free_tier=True, status="stable",
        serving={"groq": "llama-3.3-70b-versatile", "bedrock": "meta.llama3-3-70b"},
    ),
    "groq:llama-3.1-8b-instant": ModelInfo(
        provider="groq", model_id="llama-3.1-8b-instant", family="Llama 3.1", name="Llama 3.1 8B Instant",
        description="Fast, low-latency Llama 3.1 8 B for cost-sensitive workloads.",
        context_length=131_072, max_output_tokens=16_384,
        capabilities=["coding", "multilingual"],
        pricing=PricingInfo(input_per_1m=0.03, output_per_1m=0.06, free_tier=True),
        open_weights=True, free_tier=True, status="stable",
        serving={"groq": "llama-3.1-8b-instant", "bedrock": "meta.llama3-1-8b"},
    ),
    "groq:gpt-oss-120b": ModelInfo(
        provider="groq", model_id="openai/gpt-oss-120b", family="GPT-OSS", name="GPT-OSS 120B (Groq)",
        description="Open-weight 120 B reasoning model served by Groq at extreme speed.",
        context_length=131_072, max_output_tokens=16_384,
        capabilities=["reasoning", "coding"],
        pricing=PricingInfo(input_per_1m=0.15, output_per_1m=0.60, free_tier=True),
        open_weights=True, free_tier=True, status="stable",
        serving={"groq": "openai/gpt-oss-120b", "bedrock": "gpt-oss-120b"},
    ),

    # =================================================================
    # Ollama (local / self-hosted pull targets)
    # =================================================================
    "ollama:deepseek-v3": ModelInfo(
        provider="ollama", model_id="deepseek-v3", family="DeepSeek-V3", name="DeepSeek V3 (Ollama)",
        description="Self-hosted DeepSeek V3 via Ollama.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["reasoning", "coding"],
        pricing=PricingInfo(free_tier=True), open_weights=True, free_tier=True,
        status="stable",
        serving={"ollama": "deepseek-v3", "huggingface": "deepseekai/deepseek-v3"},
    ),
    "ollama:qwen3-32b": ModelInfo(
        provider="ollama", model_id="qwen3-32b", family="Qwen 3", name="Qwen3 32B (Ollama)",
        description="Self-hosted Qwen3 32B via Ollama.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["coding", "multilingual", "tool-use"],
        pricing=PricingInfo(free_tier=True), open_weights=True, free_tier=True,
        status="stable",
        serving={"ollama": "qwen3-32b", "huggingface": "Qwen/Qwen3-32B"},
    ),
    "ollama:gemma3-27b": ModelInfo(
        provider="ollama", model_id="gemma3-27b", family="Gemma 3", name="Gemma 3 27B (Ollama)",
        description="Open model from Google via Ollama.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["vision", "multilingual"],
        pricing=PricingInfo(free_tier=True), open_weights=True, free_tier=True,
        status="stable",
        serving={"ollama": "gemma3:27b", "huggingface": "google/gemma-3-27b"},
    ),
    "ollama:mistral-small3": ModelInfo(
        provider="ollama", model_id="mistral-small3", family="Mistral", name="Mistral Small 3 (Ollama)",
        description="Open-weight French model; fast and lightweight.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["coding", "multilingual"],
        pricing=PricingInfo(free_tier=True), open_weights=True, free_tier=True,
        status="stable",
        serving={"ollama": "mistral-small3", "huggingface": "mistralai/Mistral-Small-3"},
    ),

    # =================================================================
    # Llama.cpp (local GGUF servers)
    # =================================================================
    "llamacpp:llama-4-scout-q4": ModelInfo(
        provider="llamacpp", model_id="Llama-4-Scout-Q4_K_M.gguf", family="Llama 4", name="Llama 4 Scout Q4 (llama.cpp)",
        description="Quantised Llama 4 Scout running via the llama.cpp server (OpenAI-compatible REST API).",
        context_length=512_000, max_output_tokens=16_384,
        capabilities=["coding", "multilingual"],
        pricing=PricingInfo(free_tier=True), open_weights=True, free_tier=True,
        status="stable",
        serving={"llamacpp": "Llama-4-Scout-Q4_K_M.gguf", "huggingface": "meta-llama/Llama-4-Scout"},
    ),
    "llamacpp:qwen3-32b-q4": ModelInfo(
        provider="llamacpp", model_id="Qwen3-32B-Q4_K_M.gguf", family="Qwen 3", name="Qwen3 32B Q4 (llama.cpp)",
        description="Quantised Qwen3 32B running via the llama.cpp server.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["coding", "multilingual", "tool-use"],
        pricing=PricingInfo(free_tier=True), open_weights=True, free_tier=True,
        status="stable",
        serving={"llamacpp": "Qwen3-32B-Q4_K_M.gguf"},
    ),

    # =================================================================
    # Amazon Bedrock — first-party (Nova, Titan)
    # =================================================================
    "bedrock:amazon.nova-pro-v1": ModelInfo(
        provider="bedrock", model_id="amazon.nova-pro-v1:0", family="Nova", name="Amazon Nova Pro",
        description="Amazon's flagship multimodal model for complex tasks.",
        context_length=300_000, max_output_tokens=8_192,
        capabilities=["reasoning", "coding", "vision", "tool-use"],
        pricing=PricingInfo(input_per_1m=0.085, output_per_1m=0.085, note="Bedrock pricing"),
        status="stable",
        serving={"bedrock": "amazon.nova-pro-v1:0"},
    ),
    "bedrock:amazon.nova-micro-v1": ModelInfo(
        provider="bedrock", model_id="amazon.nova-micro-v1:0", family="Nova", name="Amazon Nova Micro",
        description="Lightweight, low-cost text-only model.",
        context_length=300_000, max_output_tokens=8_192,
        capabilities=["multilingual"],
        pricing=PricingInfo(input_per_1m=0.035, output_per_1m=0.035),
        status="stable",
        serving={"bedrock": "amazon.nova-micro-v1:0"},
    ),

    # =================================================================
    # Vertex AI — Google Cloud hosted
    # =================================================================
    "vertex:gemini-2.5-pro": ModelInfo(
        provider="vertex", model_id="publishers/google/models/gemini-2.5-pro", family="Gemini 2.5", name="Gemini 2.5 Pro (Vertex)",
        description="Gemini 2.5 Pro hosted on Vertex AI with Google Cloud IAM and private networking.",
        context_length=1_000_000, max_output_tokens=64_000,
        capabilities=["reasoning", "coding", "vision", "tool-use"],
        pricing=PricingInfo(note="Vertex pricing; see cloud.google.com/vertex-ai/pricing"),
        status="stable", knowledge_cutoff="May 2026",
        serving={"vertex": "publishers/google/models/gemini-2.5-pro"},
    ),
    "vertex:gemini-2.5-flash": ModelInfo(
        provider="vertex", model_id="publishers/google/models/gemini-2.5-flash", family="Gemini 2.5", name="Gemini 2.5 Flash (Vertex)",
        description="Gemini 2.5 Flash on Vertex AI — cost-efficient production endpoint.",
        context_length=1_000_000, max_output_tokens=64_000,
        capabilities=["coding", "tool-use", "vision"],
        pricing=PricingInfo(note="Vertex pricing; see cloud.google.com/vertex-ai/pricing"),
        status="stable", knowledge_cutoff="May 2026",
        serving={"vertex": "publishers/google/models/gemini-2.5-flash"},
    ),
    "vertex:llama-4-maverick": ModelInfo(
        provider="vertex", model_id="publishers/meta/models/llama-4-maverick", family="Llama 4", name="Llama 4 Maverick (Vertex)",
        description="Llama 4 Maverick (open weights) hosted on Vertex AI Model Garden.",
        context_length=1_000_000, max_output_tokens=16_384,
        capabilities=["reasoning", "coding", "vision"],
        open_weights=True,
        pricing=PricingInfo(note="Vertex Model Garden pricing"),
        status="preview",
        serving={"vertex": "publishers/meta/models/llama-4-maverick"},
    ),
    "vertex:llama-4-scout": ModelInfo(
        provider="vertex", model_id="publishers/meta/models/llama-4-scout", family="Llama 4", name="Llama 4 Scout (Vertex)",
        description="Llama 4 Scout (109 B, open weights) hosted on Vertex AI Model Garden.",
        context_length=512_000, max_output_tokens=16_384,
        capabilities=["coding", "multilingual"],
        open_weights=True,
        pricing=PricingInfo(note="Vertex Model Garden pricing"),
        status="preview",
        serving={"vertex": "publishers/meta/models/llama-4-scout"},
    ),
    "vertex:qwen3-235b": ModelInfo(
        provider="vertex", model_id="publishers/qwen/models/qwen3-235b-a22b", family="Qwen 3", name="Qwen3 235B A22B (Vertex)",
        description="Qwen3 235 B A22B MoE model hosted on Vertex AI Model Garden.",
        context_length=128_000, max_output_tokens=8_192,
        capabilities=["reasoning", "coding", "multilingual"],
        pricing=PricingInfo(note="Vertex Model Garden pricing"),
        status="preview",
        serving={"vertex": "publishers/qwen/models/qwen3-235b-a22b"},
    ),

    # =================================================================
    # Local (Silverwing's own trained model)
    # =================================================================
    "local:local-rule": ModelInfo(
        provider="local", model_id="local-rule", family="Silverwing", name="Silverwing-Decoder-V2 (local-rule)",
        description="Silverwing's own decoder-only transformer; when no credentials are present, a deterministic local-rule fallback is used.",
        context_length=None, max_output_tokens=None,
        capabilities=["reasoning", "tool-use", "memory-retrieval"],
        pricing=PricingInfo(free_tier=True), free_tier=True,
        status="stable",
        serving={"local": "local-rule"},
    ),
    "silverwing:silverwing-decoder-v2": ModelInfo(
        provider="silverwing", model_id="silverwing-decoder-v2", family="Silverwing", name="Silverwing Decoder V2",
        description="Legacy alias; no trained weights exist under this id. Resolves to silverwing-120m-base-v1 when served. Retained only so old references do not break.",
        context_length=2048, max_output_tokens=2048,
        capabilities=["text-generation"],
        pricing=PricingInfo(free_tier=True), free_tier=True, open_weights=True,
        status="deprecated",
        serving={"silverwing": "silverwing-120m-base-v1"},
    ),
    "silverwing:silverwing-embed-v1": ModelInfo(
        provider="silverwing", model_id="silverwing-embed-v1", family="Silverwing", name="Silverwing Embed V1",
        description="Silverwing's native embedding model for local semantic search and retrieval.",
        context_length=8192, max_output_tokens=None,
        capabilities=["embeddings", "memory-retrieval"],
        pricing=PricingInfo(free_tier=True), free_tier=True, open_weights=True,
        status="stable",
        serving={"silverwing": "silverwing-embed-v1"},
    ),
    "silverwing:silverwing-120m-base-v1": ModelInfo(
        provider="silverwing", model_id="silverwing-120m-base-v1", family="Silverwing",
        name="Silverwing-120M-Base-v1",
        description=(
            "Silverwing's 120M base model (120,087,552 params, GPU-trained). "
            "Served through the Silverwing runtime / model gateway. "
            "Capabilities are limited to text-generation until validated."
        ),
        context_length=2048, max_output_tokens=2048,
        capabilities=["text-generation"],
        pricing=PricingInfo(free_tier=True), free_tier=True, open_weights=True,
        status="experimental",
        serving={"silverwing": "silverwing-120m-base-v1"},
    ),
    "silverwing:silverwing-12m-r2000": ModelInfo(
        provider="silverwing", model_id="silverwing-12m-r2000", family="Silverwing",
        name="Silverwing-12M-r2000 Baseline",
        description=(
            "Archived engineering/scaling baseline (12,440,448 params). "
            "Retained for comparison; not served in production."
        ),
        context_length=1024, max_output_tokens=1024,
        capabilities=["text-generation"],
        pricing=PricingInfo(free_tier=True), free_tier=True, open_weights=True,
        status="archived",
        serving={"silverwing": "silverwing-12m-r2000"},
    ),
    # =================================================================
    # JARVIS Brain (Qwen3-4B) — remote GPU inference via Kaggle / HF
    # =================================================================
    "jarvis:jarvis-brain-qwen3-4b-v1": ModelInfo(
        provider="jarvis", model_id="jarvis-brain-qwen3-4b-v1", family="Qwen3",
        name="JARVIS Brain (Qwen3-4B)",
        description=(
            "JARVIS BRAIN v1 candidate: Qwen/Qwen3-4B (Apache-2.0, "
            "1cfa9a7208912126459214e8b04321603b3df60c). 4.0B params, 36 layers, "
            "GQA, 40k context. Served on remote Kaggle GPU via an OpenAI-compatible "
            "endpoint (JARVIS_BRAIN_ENDPOINT); weights are never stored in the "
            "JARVIS repository. Baseline/untuned — candidate for SFT."
        ),
        context_length=40_960, max_output_tokens=8192,
        capabilities=["text-generation", "chat", "reasoning", "coding", "math", "long-context", "tool-use"],
        pricing=PricingInfo(free_tier=True, note="self-hosted on Kaggle GPU / HF storage"),
        open_weights=True, free_tier=True,
        status="experimental", knowledge_cutoff="2025-07",
        serving={"huggingface": "Qwen/Qwen3-4B"},
    ),
    "jarvis:jarvis-brain-qwen3-4b-sft-v1": ModelInfo(
        provider="jarvis", model_id="jarvis-brain-qwen3-4b-sft-v1", family="Qwen3",
        name="JARVIS Brain SFT (Qwen3-4B)",
        description=(
            "JARVIS Brain SFT candidate (adapter over Qwen3-4B) — created only "
            "after the Qwen3-4B baseline eval passes. Not yet trained; placeholder "
            "so the registry supersedes cleanly. Base frozen; LoRA adapter only."
        ),
        context_length=40_960, max_output_tokens=8192,
        capabilities=["text-generation", "chat", "reasoning", "coding", "math", "long-context", "tool-use"],
        pricing=PricingInfo(free_tier=True, note="self-hosted on Kaggle GPU / HF storage"),
        open_weights=True, free_tier=True,
        status="experimental", knowledge_cutoff="2025-07",
        serving={"huggingface": "videlisndichi/jarvis-brain-qwen3-4b-sft-v1"},
    ),
}


# ---------------------------------------------------------------------------
# Convenience lookups
# ---------------------------------------------------------------------------

# Sorted list of all catalog keys — handy for API responses / validation.
MODEL_CATALOG_BY_KEY: List[str] = sorted(MODEL_CATALOG.keys())


def _catalog_keys() -> List[str]:
    return sorted(MODEL_CATALOG.keys())


def get_model_info(ref: str) -> Optional[ModelInfo]:
    """Look up a model by ``"provider:model"`` or bare ``model_id``."""
    if ref in MODEL_CATALOG:
        return MODEL_CATALOG[ref]
    # Try matching by model_id suffix
    for key, info in MODEL_CATALOG.items():
        if info.model_id == ref:
            return info
    return None


def list_by_provider(provider: str) -> List[ModelInfo]:
    """All catalog entries for a given provider name."""
    return [m for m in MODEL_CATALOG.values() if m.provider == provider]


def list_all_models() -> List[Dict[str, Any]]:
    """Serialised catalog for API responses (includes the catalog key)."""
    return [dict(info.model_dump(), key=k) for k, info in MODEL_CATALOG.items()]


def list_families() -> Dict[str, List[str]]:
    """Map family name -> list of ``"provider:model_id"`` keys."""
    families: Dict[str, List[str]] = {}
    for key, info in MODEL_CATALOG.items():
        families.setdefault(info.family, []).append(key)
    return families


def list_open_weights() -> List[Dict[str, Any]]:
    """All open-weights (self-hostable) models (includes catalog key)."""
    return [dict(info.model_dump(), key=k)
            for k, info in MODEL_CATALOG.items() if info.open_weights]


__all__ = [
    "ModelInfo", "PricingInfo", "ProviderProfile",
    "PROVIDER_PROFILES", "MODEL_CATALOG", "MODEL_CATALOG_BY_KEY",
    "get_model_info", "list_by_provider", "list_all_models",
    "list_families", "list_open_weights",
]
