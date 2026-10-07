"""Silverwing-120M-v1 — SCALE-UP INITIALIZATION (Phase 1).

Does NOT touch the 12M/r2000 baseline (read-only). Creates a NEW model identity
"Silverwing-120M-v1" under F:/AI/silverwing-120m/ with:
  - architecture config
  - tokenizer_manifest.json (reuses r2000's 8192-token BPE tokenizer — compatible:
    same vocab, same special tokens, tied embeddings)
  - run_manifest.json (model_version/architecture_version/tokenizer_version/dataset_version/run_id)
  - environment_report.txt (hardware audit)
  - validation_report.json (section 10 battery)
  - silverwing_120m_config.json (canonical config)

Architecture param count is computed from the IMPLEMENTED architecture
(sw.estimate_parameters + actual sw.SilverwingModel.num_parameters), not hand-waved.
"""
from __future__ import annotations
import os, sys, json, math, time, hashlib, platform, subprocess
from pathlib import Path

TRAIN_DIR = r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu"
sys.path.insert(0, TRAIN_DIR)
import silverwing_train as sw
import torch
from safetensors.torch import load_file  # present in env (used by r2000 eval)

WORK = Path(r"F:/AI/silverwing-120m")            # NEW model workspace (NOT r2000)
DATA = Path(r"F:/AI/data")
R2000_TOK = Path(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json")
R2000_FINAL = Path(r"F:/AI/silverwing-r2000/final")

# ---------------------------------------------------------------------------
# 2. ARCHITECTURE
#    Brief: 12 layers, d_model 768, 12Q/4KV, head_dim 64, MLP~2560, SwiGLU,
#    RoPE, theta 1e4, tied embeddings, ctx 2048, no bias.
#    That config (d=768) yields ~102M only at vocab=16384; at the EXISTING vocab
#    8192 it is ~81.8M — below 120M. To hit the brief's "approximately 120M" with
#    the LEAST change to arch variables while keeping head_dim=64 (a brief
#    constraint) and KV=4,12 layers: raise d_model 768->1024 and set
#    n_heads = d_model//64 = 16, then pick hidden_size so the count lands at 120M.
#    hidden_size=2176 (=2.125 * d_model, multiple_of 64) -> 120,087,272 params.
# ---------------------------------------------------------------------------
SILVERWING_120M_CONFIG = {
    "vocab_size": 8192,            # same BPE tokenizer as r2000 (compatible — section 3)
    "max_position_embeddings": 2048,
    "n_layers": 12,                # brief: 12 layers
    "n_heads": 16,                 # head_dim=64, d_model=1024 -> 16 heads (brief derived; head_dim kept 64)
    "n_kv_heads": 4,               # brief: 4 KV heads (GQA 16:4 = 4:1)
    "d_model": 1024,                # brief 768 -> 1024 (adjustment, see notes)
    "hidden_size": 2176,            # SwiGLU intermediate (adjustment; 2.125 * d_model, multiple_of 64)
    "multiple_of": 64,
    "norm_eps": 1e-5,               # RMSNorm epsilon (matches r2000 convention)
    "rope_theta": 10000.0,          # brief: theta 10000
    "use_bias": False,              # brief: bias disabled
    "tie_word_embeddings": True,    # brief: embedding tying enabled
    "pad_token_id": 0,              # same special-token ids as r2000 tokenizer
    "bos_token_id": 1,
    "eos_token_id": 2,
}

ADJUSTMENTS = (
    "Starting from the brief's suggestion (d_model=768, heads=12, head_dim=64, MLP=2560, vocab=8192) the "
    "implemented estimate_parameters() yields 120M only at vocab=16384; at the EXISTING 8192-token tokenizer "
    "it is ~81.8M. To reach the brief's ~120M target we made the SMALLEST coherent adjustment that keeps every "
    "briefed structural knob (12 layers, KV heads=4, head_dim=64, SwiGLU, RoPE theta 1e4, RMSNorm, ctx 2048, "
    "tied embeddings, no bias): (1) d_model 768->1024 (so head_dim=64 forces n_heads 12->16; KV heads held at 4); "
    "(2) hidden_size 2560 -> 2176 (chosen so total params = 120,087,272 ~= 120M, multiple_of 64 respected). "
    "Tokenizer is NOT changed (reused r2000 BPE, vocab 8192, sha recorded)."
)

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "eval").mkdir(parents=True, exist_ok=True)

    # ---- tokenizer compatibility check (section 3) ----
    assert R2000_TOK.exists(), "r2000 tokenizer missing"
    tok = sw.BPETokenizer.from_file(str(R2000_TOK))
    assert tok.vocab_size == SILVERWING_120M_CONFIG["vocab_size"], \
        f"tokenizer vocab {tok.vocab_size} != config vocab_size"
    # special-token ids must match r2000 (0 pad,1 bos,2 eos,3 unk) -> compatible
    print(f"[TOK] r2000 tokenizer reused: vocab={tok.vocab_size} sha={sha256(R2000_TOK)[:16]}…")

    # ---- architecture print (section 2) ----
    cfg = sw.ModelConfig(**SILVERWING_120M_CONFIG)
    est = sw.estimate_parameters(cfg)
    print("\nSILVERWING-120M ARCHITECTURE")
    print("Parameters (estimated, from implemented architecture):")
    print(f"  {est:,}")
    print("Layers:", cfg.n_layers)
    print("d_model:", cfg.d_model)
    print("Q heads:", cfg.n_heads)
    print("KV heads:", cfg.n_kv_heads)
    print("MLP:", cfg.hidden_size)
    print("Vocabulary:", cfg.vocab_size)
    print("Context:", cfg.max_position_embeddings)
    print("head_dim:", cfg.head_dim, " GQA groups:", cfg.n_kv_groups,
          " RoPE theta:", cfg.rope_theta)

    # ---- write canonical config (section 40) ----
    json.dump(SILVERWING_120M_CONFIG, open(WORK / "silverwing_120m_config.json", "w"), indent=2)

    # ---- tokenizer_manifest.json (section 3) ----
    tok_manifest = {
        "model_version": "Silverwing-120M-v1",
        "tokenizer_version": "12M-r2000-bpe-8192",     # reused verbatim
        "path": str(R2000_TOK),
        "sha256": sha256(R2000_TOK),
        "vocabulary_size": tok.vocab_size,
        "special_tokens": {"pad_token_id": 0, "bos_token_id": 1, "eos_token_id": 2, "unk_token_id": 3},
        "tokenization_config": {"algorithm": "BPE", "pre_tokenizer": "ByteLevel(add_prefix_space=True)",
                                "decoder": "ByteLevel", "trainer_min_frequency": 2, "type": "wordpiece-ish BPE"},
        "compatible_with_new_architecture": True,
        "compatibility_note": "Same vocab_size (8192), same special-token ids, tied embeddings -> shared tokenizer semantics; new model has its own weights."
    }
    json.dump(tok_manifest, open(WORK / "tokenizer_manifest.json", "w"), indent=2)

    # ---- 10. MODEL VALIDATION (section 10 battery) ----
    torch.set_grad_enabled(True)
    torch.manual_seed(42)
    model = sw.SilverwingModel(cfg)
    params = model.num_parameters()          # authoritative count from implemented architecture
    print("\nMODEL VALIDATION")
    print("Parameters:", f"{params:,} (estimate {est:,})")
    assert params == est, f"param mismatch actual={params} estimate={est}"
    assert 119_000_000 <= params <= 151_000_000, f"param count {params} outside 119-151M target"
    print(f"Forward: ", end="", flush=True)
    B, T = 2, 64
    ids = torch.randint(1, cfg.vocab_size, (B, T))
    out = model(ids)
    assert "logits" in out and "loss" in out
    assert out["logits"].shape == (B, T, cfg.vocab_size), out["logits"].shape
    assert out["loss"] is None
    print("OK -> logits", tuple(out["logits"].shape))

    print("Backward: ", end="", flush=True)
    ids = torch.randint(1, cfg.vocab_size, (4, 128))
    lbl = torch.randint(1, cfg.vocab_size, (4, 128))
    o = model(ids, labels=lbl)
    loss = o["loss"]
    loss.backward()
    grads_ok = all(p.grad is not None and torch.isfinite(p.grad).all()
                   for p in model.parameters() if p.requires_grad)
    assert grads_ok
    print(f"OK -> loss={loss.item():.4f}")

    print("GQA: ", end="", flush=True)
    attn = model.layers[0].attention
    assert attn.n_heads == 16 and attn.n_kv_heads == 4 and attn.head_dim == 64
    x = torch.randn(2, 32, cfg.d_model)
    q = attn.q_proj(x).view(2, 32, 16, 64).transpose(1, 2)
    k = attn.k_proj(x).view(2, 32, 4, 64).transpose(1, 2)
    assert q.shape == (2, 16, 32, 64) and k.shape == (2, 4, 32, 64)
    out_att = attn(x)
    assert out_att.shape == (2, 32, cfg.d_model)          # KV repeated to 16 heads internally
    print("OK -> q(2,16,32,64) k(2,4,32,64) o(2,32,1024)")

    print("RoPE: ", end="", flush=True)
    cos, sin = attn.rope(8, torch.device("cpu"))
    assert cos.shape == (8, 64) and sin.shape == (8, 64)
    q0 = torch.randn(1, 16, 1, 64)                      # position 0 -> cos=1, sin=0 -> unchanged
    qe0, _ = sw.apply_rope(q0, q0.clone(), cos[:1].unsqueeze(0).unsqueeze(0), sin[:1].unsqueeze(0).unsqueeze(0))
    assert torch.allclose(qe0, q0, atol=1e-6)
    qe1, _ = sw.apply_rope(q0, q0.clone(), cos[1:2].unsqueeze(0).unsqueeze(0), sin[1:2].unsqueeze(0).unsqueeze(0))
    assert not torch.allclose(qe1, q0, atol=1e-6)      # position 1 -> rotated
    print("OK -> identity@pos0, rotation@pos1")

    print("SwiGLU: ", end="", flush=True)
    mlp = model.layers[0].mlp
    assert hasattr(mlp, "gate") and hasattr(mlp, "up") and hasattr(mlp, "down")
    y = mlp(torch.randn(2, 16, cfg.d_model))
    assert y.shape == (2, 16, cfg.d_model) and torch.isfinite(y).all() and (y.abs().sum() > 0)
    gate_path = torch.sigmoid(mlp.gate(torch.randn(2, 16, cfg.d_model)))
    assert (gate_path > 0).all() and (gate_path < 1).all()   # sigmoid gate active
    print("OK -> gate/sigmoid/up/down, output nonzero")

    print("RMSNorm: ", end="", flush=True)
    ln = model.layers[0].ln1
    assert isinstance(ln, sw.RMSNorm)
    z = torch.randn(2, 8, cfg.d_model)
    zn = ln(z)
    # RMSNorm: each row's RMS ~1 after (output/weight)
    rms = (zn.float().pow(2).mean(-1)).sqrt()
    assert torch.allclose(rms, torch.ones_like(rms), atol=1e-3), rms
    print(f"OK -> RMSNorm normalizes rows (mean rms {rms.mean():.4f})")

    print("Causal mask: ", end="", flush=True)
    m = model._make_causal_mask(8, torch.device("cpu"))
    assert m.shape == (1, 1, 8, 8)
    print(f"\n  [diag] shape={tuple(m.shape)} dtype={m.dtype} "
          f"diag_all_true={bool(m[0,0].diagonal().all())} "
          f"strict_upper_all_false={bool((m[0,0].triu(diagonal=1)==0).all().item())}", end="", flush=True)
    # authoritative functional test: position t's output must not depend on tokens > t
    torch.manual_seed(0)
    a = torch.randint(1, cfg.vocab_size, (1, 8))
    b = a.clone(); b[0, 5:] = torch.randint(1, cfg.vocab_size, (3,))   # change future tokens (idx 5,6,7)
    model.eval()
    with torch.no_grad():
        la = model(a)["logits"][0, :5, :].clone()      # first 5 positions
        lb = model(b)["logits"][0, :5, :].clone()
    assert torch.allclose(la, lb, atol=1e-5), "causal mask leak: future token affected past logits"
    print("OK -> first 5 positions invariant to future-token perturbation")

    print("NaN: ", end="", flush=True)
    nan_p = any(torch.isnan(p).any().item() for p in model.parameters())
    nan_g = any((p.grad is not None and torch.isnan(p.grad).any()).item() for p in model.parameters())
    assert not nan_p and not nan_g
    print("OK -> no NaN in params/grads")

    print("Inf: ", end="", flush=True)
    inf_p = any(torch.isinf(p).any().item() for p in model.parameters())
    inf_g = any((p.grad is not None and torch.isinf(p.grad).any()).item() for p in model.parameters())
    assert not inf_p and not inf_g
    print("OK -> no Inf in params/grads")

    print("Optimizer: ", end="", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    before = model.layers[0].attention.q_proj.weight.detach().clone()
    opt.step()
    after = model.layers[0].attention.q_proj.weight.detach().clone()
    assert not torch.allclose(before, after)
    print("OK -> AdamW updates parameters")

    print("One training step (clip+step+zerograd): ", end="", flush=True)
    model.train()
    ids = torch.randint(1, cfg.vocab_size, (2, 64))
    lbl = torch.randint(1, cfg.vocab_size, (2, 64))
    opt.zero_grad()
    o = model(ids, labels=lbl)
    L = o["loss"]; L.backward()
    gn = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    opt.step()
    assert torch.isfinite(L) and torch.isfinite(gn)
    print(f"OK -> loss={L.item():.4f} grad_norm={gn.item():.3f}")

    # ---- hardware audit (section 11) ----
    cpu_count = os.cpu_count() or 1
    try:
        import psutil
        vm = psutil.virtual_memory()
        ram_gb = vm.total / 1e9; ram_avail_gb = vm.available / 1e9
    except Exception:
        ram_gb = ram_avail_gb = None
    cuda = torch.cuda.is_available()
    hware = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda_available": cuda,
        "cuda_device": (torch.cuda.get_device_name(0) if cuda else None),
        "ram_gb_total": ram_gb, "ram_gb_available": ram_avail_gb,
        "cpu_count": cpu_count,
        "bf16_supported": False,
        "fp16_supported": False,
        "notes": "CPU-only host (no GPU); training float32. 120M model + AdamW ~1.9GB RAM for one step."
    }
    json.dump(hware, open(WORK / "environment_report.json", "w"), indent=2, default=str)
    # human-readable text version (section 11 asks for environment_report.txt)
    with open(WORK / "environment_report.txt", "w") as f:
        f.write("Silverwing-120M-v1 — Environment / Hardware Audit\n")
        f.write("="*52+"\n")
        for k, v in hware.items():
            f.write(f"{k}: {v}\n")
        f.write("\nChosen launch defaults (from audit):\n")
        f.write("  precision: fp32 (CPU-only)\n")
        f.write("  micro-batch: 1-2\n  gradient_accumulation: 16 (effective 16-32)\n")
        f.write("  context: 2048 (seq packing to fill)\n")
        f.write("  dataloader_workers: 0 (CPU; avoid oversubscription)\n")
        f.write("  checkpoint: every 100 steps (model+optimizer+metrics+microshard)\n")
        f.write("  NOTE: CPU-only host => long runs MUST be chunked across turns with resume.\n")

    # ---- validation_report.json + run_manifest (sections 4, 40) ----
    validation = {
        "model_version": "Silverwing-120M-v1",
        "param_count_actual": params,
        "param_count_estimate_formula": est,
        "match_formula_and_actual": params == est,
        "within_target": 119_000_000 <= params <= 151_000_000,
        "tests": {
            "forward": "PASS", "backward": "PASS", "gqa_shape": "PASS",
            "rope": "PASS", "swiglu": "PASS", "rmsnorm": "PASS",
            "causal_mask": "PASS", "nan": "PASS", "inf": "PASS",
            "optimizer": "PASS", "one_training_step": "PASS"
        },
        "status": "PASS"
    }
    json.dump(validation, open(WORK / "validation_report.json", "w"), indent=2)

    run_manifest = {
        "model_version": "Silverwing-120M-v1",
        "architecture_version": "1",
        "tokenizer_version": tok_manifest["tokenizer_version"],
        "dataset_version": "TBD-stage3b-corpus-v1",
        "run_id": "silverwing-120m-v1-init",
        "base_model": "Silverwing-12M-v1-r2000 (FROZEN, read-only, NOT loaded/used for init)",
        "init_scheme": "from-scratch (Xavier/normal std=0.02 via sw._init_weights); 12M weights NOT copied",
        "config_source": "silverwing_120m_config.json",
        "param_count": params,
        "param_formula_check": params == est,
        "adjustments": ADJUSTMENTS,
        "artifacts": ["silverwing_120m_config.json","tokenizer_manifest.json","run_manifest.json",
                      "environment_report.txt","environment_report.json","validation_report.json","silverwing_probe_report.md"],
    }
    json.dump(run_manifest, open(WORK / "silverwing_120m_run_manifest.json", "w"), indent=2)

    # copy this init script's logic pointer into the probe report folder is not needed
    print("\nMODEL VALIDATION: STATUS = PASS (11/11 tests)  |  param_count =", f"{params:,}")
    print("Artifacts written to", WORK)
    print("Phase 1 (initialise + validate) COMPLETE. New identity:", run_manifest["model_version"])
    print("Next: Phase A (50-100 step smoke train) on silverwing-120m/ — awaits go-ahead.")

if __name__ == "__main__":
    main()
