@echo off
cd /d "c:\Users\Administrator\Jarvis\jarvis-remix"
echo Installing dependencies...
call npm install
echo Dependencies installed successfully!
echo.
echo Starting development server...
call npm run dev
pause
