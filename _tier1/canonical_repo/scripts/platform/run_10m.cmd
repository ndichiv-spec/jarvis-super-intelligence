@echo off
REM Stage 3A corrected 10M-token continuation.
REM Fully detached (start /b, file redirect) so it survives shell-session TTL.
set "SILVERWING_WORK_DIR=F:\AI\silverwing-10m"
start /b python -u "F:\AI\Jarvis-super-intelligence-\silverwing\kaggle\train_kernel_cpu\silverwing_train.py" --resume --resume_from "F:\AI\silverwing-r2000\final" --steps 9800 --lr 1e-5 --log_steps 50 --save_steps 1000 --eval_steps 200 > "F:\AI\silverwing-10m.log" 2>&1
