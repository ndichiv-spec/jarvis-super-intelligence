"""Token embeddings with weight tying support."""
import torch
from torch import nn


class TokenEmbeddings(nn.Module):
    """Input token embeddings.

    When weight tying is enabled (tie_word_embeddings=True), the LM head
    shares the same weight matrix as the embeddings.
    """

    def __init__(self, vocab_size: int, d_model: int, pad_token_id: int = 0):
        super().__init__()
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.pad_token_id = pad_token_id
        self.weight = nn.Parameter(torch.empty(vocab_size, d_model))
        self._init_weights()

    def _init_weights(self):
        torch.nn.init.normal_(self.weight, mean=0.0, std=0.02)
        if self.pad_token_id is not None:
            with torch.no_grad():
                self.weight[self.pad_token_id].zero_()

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        # input_ids: [batch, seq_len] -> [batch, seq_len, d_model]
        return self.weight[input_ids]


class LMHead(nn.Module):
    """Language-modeling head: d_model -> vocab_size.

    When tied to TokenEmbeddings, shares the same weight.
    """

    def __init__(self, d_model: int, vocab_size: int, pad_token_id: int = 0):
        super().__init__()
        self.d_model = d_model
        self.vocab_size = vocab_size
        self.pad_token_id = pad_token_id
        self.weight = nn.Parameter(torch.empty(vocab_size, d_model))
        self._init_weights()

    def _init_weights(self):
        torch.nn.init.normal_(self.weight, mean=0.0, std=0.02)
        if self.pad_token_id is not None:
            with torch.no_grad():
                self.weight[self.pad_token_id].zero_()

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        # hidden_states: [batch, seq_len, d_model] -> [batch, seq_len, vocab_size]
        return torch.nn.functional.linear(hidden_states, self.weight)
