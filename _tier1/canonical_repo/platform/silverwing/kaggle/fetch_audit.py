import subprocess
import sys

result = subprocess.run(
    ["kaggle", "kernels", "logs", "videlisndichi/silverwing-hardware-audit"],
    capture_output=True, timeout=30
)

stdout = result.stdout.decode("utf-8", errors="replace")
stderr = result.stderr.decode("utf-8", errors="replace")

with open(r"F:\AI/Jarvis-super-intelligence-/silverwing/kaggle/hardware_audit_logs.txt", "w", encoding="utf-8") as f:
    f.write(stdout)
    if stderr:
        f.write("\n--- STDERR ---\n")
        f.write(stderr)

print(f"stdout: {len(stdout)} chars, stderr: {len(stderr)} chars")
print("Logs written to hardware_audit_logs.txt")
