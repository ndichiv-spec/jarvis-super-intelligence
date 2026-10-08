"""Silverwing — decoder-only causal transformer.

Architecture: Token Embeddings → RoPE → Transformer Blocks → RMSNorm → LM Head

Level 1 (Silverwing-102M):
    Layers:       12
    d_model:      768
    Q heads:      12
    KV heads:      4  (GQA, 3:1 ratio)
    MLP:          2560 (SwiGLU, multiple of 64)
    Position:      RoPE
    Norm:          RMSNorm
    Vocabulary:    16384
    Context:       2048
    Weight tying:  enabled
"""
from __future__ import annotations

import math
import torch
from torch import nn

from silverwing.model.config import ModelConfig, estimate_parameters
from silverwing.model.embeddings import TokenEmbeddings, LMHead
from silverwing.model.transformer_block import TransformerBlock
from silverwing.model.normalization import RMSNorm


class SilverwingModel(nn.Module):
    """Full Silverwing decoder-only language model."""

    def __init__(self, config: ModelConfig, use_cache: bool = True):
        super().__init__()
        self.config = config
        self.use_cache = use_cache

        # Token embeddings
        self.embed_tokens = TokenEmbeddings(
            config.vocab_size, config.d_model, config.pad_token_id
        )

        # Transformer blocks
        self.layers = nn.ModuleList([
            TransformerBlock(config) for _ in range(config.n_layers)
        ])

        # Final RMSNorm
        self.norm_f = RMSNorm(config.d_model, config.norm_eps)

        # LM Head (optionally tied to embeddings)
        if config.tie_word_embeddings:
            self.lm_head = LMHead(config.d_model, config.vocab_size, config.pad_token_id)
            # Tie weights — share the same parameter
            self.lm_head.weight = self.embed_tokens.weight
        else:
            self.lm_head = LMHead(config.d_model, config.vocab_size, config.pad_token_id)

        # Initialize
        self._init_weights()

    def _init_weights(self):
        for name, param in self.named_parameters():
            if param.dim() > 1:
                torch.nn.init.normal_(param, mean=0.0, std=0.02)
                # Scale embeddings by 1/sqrt(d_model) — handled in forward

    def _make_causal_mask(self, seq_len: int, device: str) -> torch.Tensor:
        """Create a causal mask [1, 1, seq_len, seq_len]."""
        mask = torch.tril(torch.ones(seq_len, seq_len, device=device, dtype=torch.bool))
        return mask.unsqueeze(0).unsqueeze(0)

    def forward(self,
                input_ids: torch.Tensor,
                labels: torch.Tensor | None = None,
                attention_mask: torch.Tensor | None = None) -> torch.Tensor:
        """Forward pass.

        Args:
            input_ids: [batch, seq_len] token IDs
            labels:    [batch, seq_len] target token IDs (shifted by 1 internally)
            attention_mask: [batch, seq_len] — 1 for real tokens, 0 for padding

        Returns:
            logits: [batch, seq_len, vocab_size]
        """
        B, T = input_ids.shape
        device = input_ids.device

        # Causal mask
        causal_mask = self._make_causal_mask(T, device)

        # Token embeddings scaled by sqrt(d_model)
        x = self.embed_tokens(input_ids) * math.sqrt(self.config.d_model)

        # Transformer blocks
        for layer in self.layers:
            x = layer(x, mask=causal_mask)

        # Final norm + LM head
        x = self.norm_f(x)
        logits = self.lm_head(x)  # [B, T, vocab_size]

        # Compute loss if labels provided
        if labels is not None:
            # Shift for next-token prediction
            shift_logits = logits[:, :-1, :].contiguous()
            shift_labels = labels[:, 1:].contiguous()
            loss = torch.nn.functional.cross_entropy(
                shift_logits.view(-1, self.config.vocab_size),
                shift_labels.view(-1),
                ignore_index=self.config.pad_token_id,
            )
            return {"loss": loss, "logits": logits}

        return {"logits": logits}

    def num_parameters(self) -> int:
        """Count trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    @torch.no_grad()
    def generate(self, input_ids: torch.Tensor, max_new_tokens: int = 100,
                 temperature: float = 0.8, top_p: float = 0.9,
                 do_sample: bool = True) -> torch.Tensor:
        """Simple autoregressive generation."""
        self.eval()
        for _ in range(max_new_tokens):
            # Only use the last token for efficiency
            logits = self(input_ids)["logits"][:, -1, :]
            # Apply temperature
            logits = logits / max(temperature, 1e-8)
            # Top-p filtering
            if top_p < 1.0:
                sorted_logits, sorted_idx = torch.sort(logits, descending=True)
                cum_probs = torch.cumsum(torch.softmax(sorted_logits, dim=-1), dim=-1)
                cutoff = cum_probs > top_p
                cutoff[..., 1:] = cutoff[..., :-1].clone()
                cutoff[..., 0] = 0
                sorted_logits[cutoff] = float("-inf")
                logits = torch.empty_like(logits).scatter_(1, sorted_idx, sorted_logits)
            # Sample
            if do_sample:
                next_token = torch.multinomial(torch.softmax(logits, dim=-1), num_samples=1)
            else:
                next_token = torch.argmax(logits, dim=-1, keepdim=True)
            input_ids = torch.cat([input_ids, next_token], dim=1)
            if next_token.item() == self.config.eos_token_id:
                break
        return input_ids
