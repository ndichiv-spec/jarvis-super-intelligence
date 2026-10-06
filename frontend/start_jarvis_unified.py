#!/usr/bin/env python3
"""
JARVIS Complete Unified Launcher
================================
Start all JARVIS components in an integrated system.
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path

def start_backend():
    """Start the unified backend"""
    print("Starting unified backend...")
    
    backend_code = '''
import asyncio
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "drive_engine"))

app = FastAPI(title="JARVIS Unified", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

drive_engine = None

@app.on_event("startup")
async def startup():
    global drive_engine
    try:
        from drive_engine.jarvis_drive_engine import get_drive_engine
        drive_engine = get_drive_engine()
        await drive_engine.initialize()
        print("Drive Engine initialized")
    except Exception as e:
        print(f"Drive Engine warning: {e}")

@app.get("/")
async def root():
    return {"name": "JARVIS Unified", "status": "running"}

@app.get("/api/v1/status")
async def status():
    if drive_engine:
        return drive_engine.get_status()
    return {"status": "Drive Engine not available"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
'''
    
    with open("unified_backend.py", "w") as f:
        f.write(backend_code)
    
    subprocess.run([sys.executable, "unified_backend.py"])

def start_frontend():
    """Start Next.js frontend"""
    print("Starting frontend...")
    
    web_dir = Path("web")
    if not (web_dir / "node_modules").exists():
        print("Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=str(web_dir))
    
    subprocess.run(["npm", "run", "dev"], cwd=str(web_dir))

def main():
    print("JARVIS Unified System Launcher")
    print("=" * 40)
    
    try:
        # Start backend
        backend_process = subprocess.Popen([sys.executable, "unified_backend.py"])
        print("Backend started on port 8000")
        
        time.sleep(3)
        
        # Start frontend
        frontend_process = subprocess.Popen(
            ["npm", "run", "dev"], 
            cwd="web"
        )
        print("Frontend started on port 3000")
        
        print("\nSystem running:")
        print("Frontend: http://localhost:3000")
        print("Backend: http://localhost:8000")
        print("Press Ctrl+C to stop")
        
        # Wait for processes
        try:
            backend_process.wait()
        except KeyboardInterrupt:
            print("\nStopping...")
            backend_process.terminate()
            frontend_process.terminate()
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
