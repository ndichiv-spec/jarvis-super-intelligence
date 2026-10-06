#!/usr/bin/env python3
"""
JARVIS Web Dashboard Launcher
===========================
Launch the JARVIS web control panel for system observation and management.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Add drive_engine to Python path
drive_engine_dir = current_dir / "drive_engine"
sys.path.insert(0, str(drive_engine_dir))

try:
    from drive_engine.control_panel import ControlPanel
    from drive_engine.jarvis_drive_engine import get_drive_engine
    
    async def start_web_dashboard():
        """Start the JARVIS web dashboard"""
        print("=== JARVIS Web Dashboard Launcher ===")
        print("Starting JARVIS Drive Engine and Web Control Panel...")
        
        try:
            # Initialize drive engine
            drive_engine = get_drive_engine()
            await drive_engine.initialize()
            
            # Create and start control panel
            control_panel = ControlPanel(drive_engine)
            
            print("Drive Engine initialized")
            print("Control Panel created")
            print("Starting web server...")
            print()
            print("JARVIS Web Dashboard will be available at:")
            print("   http://localhost:8080")
            print("   http://127.0.0.1:8080")
            print()
            print("Features available:")
            print("   - Real-time system monitoring")
            print("   - Component management")
            print("   - AI capabilities control")
            print("   - Performance optimization")
            print("   - Testing and validation")
            print("   - Deployment management")
            print("   - Documentation and help")
            print()
            print("Press Ctrl+C to stop the dashboard")
            print("=" * 50)
            
            # Start the web server
            await control_panel.start()
            
        except KeyboardInterrupt:
            print("\nDashboard stopped by user")
        except Exception as e:
            print(f"Error starting dashboard: {e}")
            import traceback
            traceback.print_exc()
    
    if __name__ == "__main__":
        asyncio.run(start_web_dashboard())
        
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure all required dependencies are installed:")
    print("pip install -r requirements.txt")
    print("\nAlso ensure the drive_engine directory exists with all required files.")
    sys.exit(1)
