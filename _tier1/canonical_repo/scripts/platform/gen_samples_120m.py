"""Generate sample_generations.txt from the saved Silverwing-120M-v1 final/ checkpoint."""
import sys, torch
sys.path.insert(0, r"F:/AI/Jarvis-super-intelligence-/silverwing/kaggle/train_kernel_cpu")
import silverwing_train as sw
from safetensors.torch import load_file

W = r"F:/AI/silverwing-120m"
cfg = sw.ModelConfig(**__import__("json").load(open(W + "/silverwing_120m_config.json")))
model = sw.SilverwingModel(cfg)
model.load_state_dict(load_file(W + "/final/model.safetensors"), strict=False)
model.eval()
tok = sw.BPETokenizer.from_file(r"F:/AI/silverwing-r2000/tokenizer/tokenizer.json")
prompts = ["The story began", "Science is", "Mathematics is", "Explain gravity.",
           "What is 17 × 24?", "Explain Newton's second law.",
           "Write a Python function that adds two numbers.", "What is a centrifugal pump?",
           "Why is preventive maintenance important?", "Explain photosynthesis."]
with open(W + "/sample_generations.txt", "w", encoding="utf-8") as f:
    f.write("Silverwing-120M-v1 — sample generations (Phase A smoke, 50 steps, LR 2e-4, seq 256, CPU)\n"
            + "=" * 72 + "\n")
    for p in prompts:
        with torch.no_grad():
            g = model.generate(torch.tensor([tok.encode(p)], dtype=torch.long),
                               max_new_tokens=64, temperature=0.8, top_p=0.9)
        f.write(f"\nPROMPT: {p}\nGEN: {tok.decode(g[0].tolist())}\n" + "-" * 72 + "\n")
        print("done:", p, flush=True)
print("WROTE", W + "/sample_generations.txt")
