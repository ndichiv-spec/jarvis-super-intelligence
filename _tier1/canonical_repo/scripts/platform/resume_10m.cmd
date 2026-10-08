@echo off
REM Resume the corrected 10M-token run from the step-3000 checkpoint.
REM Foreground launch (no start /b) so it stays tied to the launching shell session
REM (pollable via shell_tail) and still writes a durable checkpoint every save_steps.
REM Append to the existing log (>>); metrics.jsonl is appended by the script itself.
set "SILVERWING_WORK_DIR=F:\AI\silverwing-10m"
"C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" -u "F:\AI\Jarvis-super-intelligence-\silverwing\kaggle\train_kernel_cpu\silverwing_train.py" --resume --resume_from "F:/AI/silverwing-10m/checkpoints/step-3000" --steps 9800 --lr 1e-5 --log_steps 50 --save_steps 500 --eval_steps 500 >> "F:/AI/silverwing-10m.log" 2>&1
