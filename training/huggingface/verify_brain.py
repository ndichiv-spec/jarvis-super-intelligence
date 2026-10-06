# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "torch",
#   "transformers>=4.51",
#   "peft>=0.19",
#   "accelerate",
#   "huggingface_hub",
#   "safetensors",
# ]
# ///

import os
import torch

from peft import PeftConfig
from transformers import AutoModelForCausalLM, AutoTokenizer

ADAPTER_REPO = "Reyvic-254/jarvis-brain"

print("JARVIS BRAIN VERIFICATION")
print("==========================")

cfg = PeftConfig.from_pretrained(ADAPTER_REPO)

print("base_model:", cfg.base_model_name_or_path)
print("peft_type:", cfg.peft_type)

tokenizer = AutoTokenizer.from_pretrained(
    cfg.base_model_name_or_path
)

model = AutoModelForCausalLM.from_pretrained(
    ADAPTER_REPO,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

model.eval()

print("model_loaded: true")
print("cuda:", torch.cuda.is_available())

tests = [
    "What is 2 + 2? Answer with only the number.",
    "Explain why a database index can make a query faster. Keep the answer concise.",
    "Write a Python function that returns the factorial of an integer.",
]

for index, prompt in enumerate(tests, start=1):
    print(f"\nTEST {index}")
    print("PROMPT:", prompt)

    messages = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    inputs = tokenizer(
        text,
        return_tensors="pt",
    )

    device = next(model.parameters()).device
    inputs = {
        key: value.to(device)
        for key, value in inputs.items()
    }

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=64,
            do_sample=False,
        )

    generated = outputs[0][inputs["input_ids"].shape[1]:]

    answer = tokenizer.decode(
        generated,
        skip_special_tokens=True,
    ).strip()

    print("ANSWER:", answer)

print("\nBRAIN_VERIFICATION_COMPLETE")
