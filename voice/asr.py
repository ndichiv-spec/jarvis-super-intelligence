import os
import subprocess

# Basic ASR wrapper — supports using local Whisper via `whisper` CLI if available

def transcribe_audio(path: str) -> str:
    """Transcribe audio file at `path` using whisper CLI if installed, else returns empty string."""
    try:
        proc = subprocess.run(["whisper", path, "--model", "small"], capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            # Whisper CLI prints path to txt or outputs to stdout depending on version; try reading txt
            txt_path = path + ".txt"
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            return proc.stdout.strip()
        return ""
    except FileNotFoundError:
        return ""
    except Exception as e:
        return f"[asr-error] {e}"
