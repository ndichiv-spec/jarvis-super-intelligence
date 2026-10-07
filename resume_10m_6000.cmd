@echo off
REM Detached resume of the Silverwing-10M run from the step-6000 checkpoint.
REM Uses `start /b` so training SURVIVES shell-session termination -- the
REM foreground resume_10m.cmd died when its session TTL expired at step ~6350.
REM Resuming step-6000 -> 9800. Hyperparameters match the prior resume_10m.cmd.
set "SILVERWING_WORK_DIR=F:\AI\silverwing-10m"
cd /d F:\AI
start /b "" "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" -u "F:\AI\Jarvis-super-intelligence-\silverwing\kaggle\train_kernel_cpu\silverwing_train.py" --resume --resume_from "F:\AI\silverwing-10m\checkpoints\step-6000" --steps 9800 --lr 1e-5 --log_steps 50 --save_steps 500 --eval_steps 500 >> "F:\AI\silverwing-10m.log" 2>&1
