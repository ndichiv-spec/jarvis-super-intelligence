import _env
_env.apply()
import os
for key in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GROQ_API_KEY', 'DEEPSEEK_API_KEY', 'HF_TOKEN', 'JARVIS_BRAIN_API_KEY', 'JARVIS_BRAIN_ENDPOINT']:
    val = os.environ.get(key, '')
    status = f"set (len={len(val)})" if val else "(unset)"
    print(f"{key}: {status}")
