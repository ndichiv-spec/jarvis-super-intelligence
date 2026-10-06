#!/usr/bin/env python3
"""
JARVIS Unified Launcher
=======================
Complete integrated JARVIS system with all interfaces working together.

Features:
- Integrated Drive Engine with FastAPI backend
- Next.js frontend integration
- Unified configuration system
- Complete system monitoring
- All JARVIS capabilities in one interface
"""

import asyncio
import subprocess
import sys
import os
import time
import signal
import threading
from pathlib import Path
from typing import Dict, List, Optional

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir / "drive_engine"))

class UnifiedJarvisLauncher:
    """Unified JARVIS system launcher"""
    
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = True
        self.base_dir = current_dir
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        self.running = False
        self.stop_all_processes()
        sys.exit(0)
    
    def start_backend(self) -> bool:
        """Start FastAPI backend with Drive Engine integration"""
        print("Starting FastAPI Backend with Drive Engine integration...")
        
        try:
            # Create a simplified backend that includes Drive Engine
            backend_script = self.base_dir / "unified_backend.py"
            
            cmd = [
                sys.executable,
                str(backend_script),
                "--host", "0.0.0.0",
                "--port", "8000"
            ]
            
            process = subprocess.Popen(
                cmd,
                cwd=str(self.base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.processes["backend"] = process
            
            # Wait for backend to start
            time.sleep(3)
            
            if process.poll() is None:
                print("Backend started successfully on port 8000")
                return True
            else:
                print("Backend failed to start")
                return False
                
        except Exception as e:
            print(f"Error starting backend: {e}")
            return False
    
    def start_frontend(self) -> bool:
        """Start Next.js frontend"""
        print("Starting Next.js Frontend...")
        
        try:
            frontend_dir = self.base_dir / "web"
            
            # Check if node_modules exists
            if not (frontend_dir / "node_modules").exists():
                print("Installing frontend dependencies...")
                npm_install = subprocess.run(
                    ["npm", "install"],
                    cwd=str(frontend_dir),
                    capture_output=True,
                    text=True
                )
                if npm_install.returncode != 0:
                    print(f"npm install failed: {npm_install.stderr}")
                    return False
            
            cmd = ["npm", "run", "dev"]
            
            process = subprocess.Popen(
                cmd,
                cwd=str(frontend_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.processes["frontend"] = process
            
            # Wait for frontend to start
            time.sleep(5)
            
            if process.poll() is None:
                print("Frontend started successfully on port 3000")
                return True
            else:
                print("Frontend failed to start")
                return False
                
        except Exception as e:
            print(f"Error starting frontend: {e}")
            return False
    
    def start_drive_engine(self) -> bool:
        """Start Drive Engine for advanced capabilities"""
        print("Starting Drive Engine...")
        
        try:
            # Import and start Drive Engine
            from drive_engine.jarvis_drive_engine import get_drive_engine
            
            async def start_drive():
                drive_engine = get_drive_engine()
                await drive_engine.initialize()
                await drive_engine.start()
                return drive_engine
            
            # Run in background thread
            drive_thread = threading.Thread(
                target=lambda: asyncio.run(start_drive()),
                daemon=True
            )
            drive_thread.start()
            
            time.sleep(2)
            print("Drive Engine started successfully")
            return True
            
        except Exception as e:
            print(f"Error starting Drive Engine: {e}")
            return False
    
    def monitor_processes(self):
        """Monitor all running processes"""
        while self.running:
            for name, process in list(self.processes.items()):
                if process.poll() is not None:
                    print(f"Process {name} stopped unexpectedly")
                    self.running = False
                    break
            
            time.sleep(2)
    
    def stop_all_processes(self):
        """Stop all running processes"""
        print("Stopping all processes...")
        
        for name, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"Stopped {name}")
            except subprocess.TimeoutExpired:
                process.kill()
                print(f"Force killed {name}")
            except Exception as e:
                print(f"Error stopping {name}: {e}")
        
        self.processes.clear()
    
    def create_unified_backend(self):
        """Create unified backend that integrates Drive Engine"""
        backend_code = '''#!/usr/bin/env python3
"""
Unified JARVIS Backend with Drive Engine Integration
==================================================
"""

import asyncio
import sys
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "drive_engine"))

app = FastAPI(
    title="JARVIS Unified System",
    description="Complete JARVIS system with Drive Engine integration",
    version="3.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Drive Engine integration
drive_engine = None

@app.on_event("startup")
async def startup_event():
    """Initialize Drive Engine on startup"""
    global drive_engine
    try:
        from drive_engine.jarvis_drive_engine import get_drive_engine
        drive_engine = get_drive_engine()
        await drive_engine.initialize()
        print("Drive Engine initialized")
    except Exception as e:
        print(f"Drive Engine initialization warning: {e}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "JARVIS Unified System",
        "version": "3.0.0",
        "status": "running",
        "components": {
            "backend": "active",
            "drive_engine": "integrated" if drive_engine else "disabled"
        }
    }

@app.get("/api/v1/status")
async def get_status():
    """Get system status"""
    if drive_engine:
        return drive_engine.get_status()
    return {"status": "Drive Engine not available"}

@app.get("/api/v1/components")
async def get_components():
    """Get components"""
    if drive_engine:
        return drive_engine.get_components()
    return {"components": []}

@app.get("/api/v1/metrics")
async def get_metrics():
    """Get metrics"""
    if drive_engine:
        return drive_engine.get_metrics()
    return {"metrics": {}}

@app.post("/api/v1/control/{action}")
async def execute_control(action: str, args: list = None):
    """Execute control command"""
    if drive_engine:
        return await drive_engine.execute_command(action, args or [])
    return {"error": "Drive Engine not available"}

# Drive Engine specific endpoints
@app.get("/api/v1/drive/status")
async def drive_status():
    """Drive Engine status"""
    if drive_engine:
        return {
            "status": drive_engine.status.value,
            "components": len(drive_engine.components),
            "uptime": drive_engine.uptime
        }
    return {"error": "Drive Engine not available"}

@app.get("/api/v1/ai/status")
async def ai_status():
    """AI capabilities status"""
    if drive_engine and hasattr(drive_engine, 'ai_orchestrator'):
        return drive_engine.ai_orchestrator.get_system_status()
    return {"error": "AI Orchestrator not available"}

@app.get("/api/v1/monitoring/dashboard")
async def monitoring_dashboard():
    """Monitoring dashboard data"""
    if drive_engine and hasattr(drive_engine, 'monitoring_interface'):
        return drive_engine.monitoring_interface.get_dashboard_data()
    return {"error": "Monitoring interface not available"}

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="JARVIS Unified Backend")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
'''
        
        backend_file = self.base_dir / "unified_backend.py"
        with open(backend_file, 'w') as f:
            f.write(backend_code)
        
        print("Created unified backend")
    
    def run(self):
        """Run the unified JARVIS system"""
        print("JARVIS Unified System Launcher")
        print("=" * 50)
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Create unified backend
        self.create_unified_backend()
        
        # Start components
        success = True
        
        # Start Drive Engine
        if not self.start_drive_engine():
            success = False
        
        # Start backend
        if not self.start_backend():
            success = False
        
        # Start frontend
        if not self.start_frontend():
            success = False
        
        if not success:
            print("Failed to start some components")
            self.stop_all_processes()
            return
        
        print("\nJARVIS Unified System is running!")
        print("=" * 50)
        print("Frontend: http://localhost:3000")
        print("Backend API: http://localhost:8000")
        print("API Docs: http://localhost:8000/docs")
        print("=" * 50)
        print("Press Ctrl+C to stop all services")
        print()
        
        # Monitor processes
        try:
            self.monitor_processes()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop_all_processes()

def main():
    """Main entry point"""
    launcher = UnifiedJarvisLauncher()
    launcher.run()

if __name__ == "__main__":
    main()
