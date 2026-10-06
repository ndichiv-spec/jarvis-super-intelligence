#!/usr/bin/env python3
"""
JARVIS App Packager
Creates a downloadable package of the JARVIS desktop application
"""

import os
import sys
import shutil
import zipfile
import json
from pathlib import Path
from datetime import datetime

def create_app_package():
    """Create a downloadable JARVIS app package"""
    print("Creating JARVIS App Package...")
    
    project_root = Path(__file__).parent
    package_dir = project_root / "JARVIS_Desktop_App_Package"
    dist_dir = project_root / "dist"
    
    # Clean previous package
    if package_dir.exists():
        shutil.rmtree(package_dir)
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    
    # Create package directory
    package_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    
    # Files to include in package
    files_to_copy = [
        "jarvis_desktop_app.py",
        "launch_jarvis_app.py",
        "core/browser_service.py",
        "core/embedded_browser.py",
        "api/routers/embedded_browser.py",
        "README.md"
    ]
    
    # Copy essential files
    print("📋 Copying application files...")
    for file_path in files_to_copy:
        source = project_root / file_path
        if source.exists():
            dest = package_dir / file_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            print(f"  ✓ {file_path}")
        else:
            print(f"  ⚠ {file_path} not found, skipping")
    
    # Create requirements file
    requirements_content = """
# JARVIS Desktop Application Requirements
PyQt5>=5.15.0
PyQtWebEngine>=5.15.0
psutil>=5.8.0
fastapi>=0.68.0
uvicorn>=0.15.0
pydantic>=1.8.0
"""
    
    requirements_file = package_dir / "requirements.txt"
    requirements_file.write_text(requirements_content.strip())
    print("  ✓ requirements.txt")
    
    # Create installation script
    install_script = """@echo off
echo ========================================
echo JARVIS Desktop Application Installer
echo ========================================
echo.

echo Installing Python dependencies...
python -m pip install -r requirements.txt

echo.
echo Installation complete!
echo.
echo To launch JARVIS:
echo   python launch_jarvis_app.py
echo.
echo Press any key to exit...
pause > nul
"""
    
    install_file = package_dir / "install.bat"
    install_file.write_text(install_script.strip())
    print("  ✓ install.bat")
    
    # Create launcher script
    launcher_script = """@echo off
echo Launching JARVIS Desktop Application...
python launch_jarvis_app.py
"""
    
    launcher_file = package_dir / "run_jarvis.bat"
    launcher_file.write_text(launcher_script.strip())
    print("  ✓ run_jarvis.bat")
    
    # Create README
    readme_content = """# JARVIS Desktop Application

## Overview
JARVIS Desktop is a standalone AI assistant application with an embedded web browser, providing complete independence from external browsers.

## Features
- 🌐 **Embedded Browser**: Self-contained web browser with no external dependencies
- 🤖 **AI Chat Interface**: Interactive AI assistant
- 📊 **System Monitor**: Real-time system performance monitoring
- 🧠 **Self-Reliant IDE**: Built-in code editor and development environment
- 🔧 **Complete Independence**: Works offline without external browsers

## Installation

### Windows
1. Double-click `install.bat` to install dependencies
2. Double-click `run_jarvis.bat` to launch JARVIS

### Manual Installation
1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Launch the application:
   ```bash
   python launch_jarvis_app.py
   ```

## Usage

### Browser Tab
- Navigate websites using the embedded browser
- No external browser required
- Full HTML5/CSS3/JavaScript support

### AI Chat Tab
- Interact with JARVIS AI assistant
- Get help with various tasks
- Real-time conversation

### System Monitor Tab
- Monitor CPU, memory, and disk usage
- Check service status
- Restart services if needed

## Keyboard Shortcuts
- `Ctrl+T`: New browser tab
- `F11`: Toggle fullscreen
- `Ctrl+Q`: Exit application

## System Requirements
- Python 3.8 or higher
- Windows 10/11 (recommended)
- 4GB RAM minimum
- 500MB disk space

## Troubleshooting

### Application won't start
1. Ensure Python is installed and in PATH
2. Run `install.bat` to install dependencies
3. Check Windows Defender isn't blocking the app

### Browser not working
1. Ensure PyQtWebEngine is installed
2. Restart the application
3. Check internet connection for external sites

### Performance issues
1. Close unnecessary browser tabs
2. Restart the application
3. Check system resources in Monitor tab

## Support
For issues and support, please check the system logs or contact the development team.

---
**JARVIS Desktop Application v1.0.0**
*Complete AI Independence*
"""
    
    readme_file = package_dir / "README.md"
    readme_file.write_text(readme_content.strip())
    print("  ✓ README.md")
    
    # Create version info
    version_info = {
        "version": "1.0.0",
        "build_date": datetime.now().isoformat(),
        "features": [
            "embedded_browser",
            "ai_chat",
            "system_monitor",
            "self_reliant_ide",
            "complete_independence"
        ],
        "requirements": [
            "Python 3.8+",
            "PyQt5",
            "PyQtWebEngine",
            "psutil"
        ],
        "platforms": ["Windows", "Linux", "macOS"]
    }
    
    version_file = package_dir / "version.json"
    version_file.write_text(json.dumps(version_info, indent=2))
    print("  ✓ version.json")
    
    # Create ZIP package
    print("\n📦 Creating ZIP package...")
    zip_filename = f"JARVIS_Desktop_App_v1.0.0_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = dist_dir / zip_filename
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in package_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(package_dir)
                zipf.write(file_path, arcname)
    
    print(f"✓ Package created: {zip_path}")
    
    # Calculate package size
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"📊 Package size: {size_mb:.1f} MB")
    
    # Create installation summary
    summary = f"""
JARVIS Desktop Application Package Created Successfully!

Package Details:
- Version: 1.0.0
- Build Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Package Size: {size_mb:.1f} MB
- File Location: {zip_path}

Installation Instructions:
1. Extract the ZIP file to a desired location
2. Run 'install.bat' to install dependencies
3. Run 'run_jarvis.bat' to launch JARVIS

Features Included:
✓ Embedded Web Browser
✓ AI Chat Interface
✓ System Monitoring
✓ Self-Reliant IDE
✓ Complete Independence from External Browsers

System Requirements:
- Python 3.8 or higher
- 4GB RAM minimum
- 500MB disk space

Ready for distribution!
"""
    
    summary_file = dist_dir / "installation_summary.txt"
    summary_file.write_text(summary.strip())
    
    print("\n" + "="*60)
    print("🎉 JARVIS Desktop Application Package Ready!")
    print("="*60)
    print(summary)
    
    return zip_path

def main():
    """Main packaging function"""
    try:
        package_path = create_app_package()
        
        # Ask if user wants to open the package location
        print(f"\n📂 Package location: {package_path.parent}")
        
        # Open the distribution folder
        if os.name == 'nt':  # Windows
            os.startfile(package_path.parent)
        elif os.name == 'posix':  # macOS/Linux
            subprocess.run(['open', str(package_path.parent)], check=False)
        
        return True
        
    except Exception as e:
        print(f"❌ Packaging failed: {e}")
        return False

if __name__ == "__main__":
    main()
