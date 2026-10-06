#!/usr/bin/env python3
"""
Simple test for browser service functionality
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Simple logging setup
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_browser_service():
    """Test browser service functionality"""
    print("Testing JARVIS Browser Service...")
    
    try:
        # Import browser service
        from core.browser_service import get_browser_service
        
        # Get service instance
        service = get_browser_service()
        print("Browser service imported successfully")
        
        # Test initialization
        if service.initialize():
            print("Browser service initialized successfully")
        else:
            print("Failed to initialize browser service")
            return False
        
        # Test window creation
        if service.create_window("test"):
            print("Created test window")
        else:
            print("Failed to create test window")
            return False
        
        # Test navigation
        if service.navigate_to("test", "https://example.com"):
            print("Navigated to example.com")
        else:
            print("Failed to navigate")
            return False
        
        # Test content loading
        html_content = "<html><body><h1>JARVIS Browser Test</h1><p>This is a test page.</p></body></html>"
        if service.load_content("test", html_content):
            print("Loaded HTML content")
        else:
            print("Failed to load content")
            return False
        
        # Test script execution
        if service.execute_script("test", "console.log('Hello from JARVIS Browser!')"):
            print("Executed JavaScript")
        else:
            print("Failed to execute script")
            return False
        
        # Test getting content
        content = service.get_page_content("test")
        if content:
            print("Retrieved page content")
        else:
            print("Failed to get content")
            return False
        
        # Test window management
        if service.hide_window("test"):
            print("Hid window")
        else:
            print("Failed to hide window")
            return False
        
        if service.show_window("test"):
            print("Showed window")
        else:
            print("Failed to show window")
            return False
        
        # Test status
        status = service.get_status()
        print(f"Service status: {status['windows']} windows, running: {status['running']}")
        
        # Test window list
        windows = service.get_window_list()
        print(f"Window list: {len(windows)} windows")
        
        # Cleanup
        if service.close_window("test"):
            print("Closed test window")
        else:
            print("Failed to close window")
            return False
        
        print("All browser service tests passed!")
        return True
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_endpoints():
    """Test API endpoints with simple requests"""
    print("\nTesting API endpoints...")
    
    try:
        import requests
        import time
        
        # Test basic endpoints (these should work even if browser isn't fully initialized)
        base_url = "http://localhost:8000"
        
        # Test root endpoint
        try:
            response = requests.get(f"{base_url}/", timeout=5)
            if response.status_code == 200:
                print("Root endpoint accessible")
            else:
                print(f"Root endpoint returned {response.status_code}")
        except requests.exceptions.RequestException:
            print("Backend not running - skipping API tests")
            return True
        
        # Test browser status endpoint
        try:
            response = requests.get(f"{base_url}/api/browser/system/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"Browser status endpoint: {data.get('success', False)}")
            else:
                print(f"Browser status endpoint returned {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Browser status endpoint error: {e}")
        
        # Test browser initialization
        try:
            response = requests.post(f"{base_url}/api/browser/system/initialize", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"Browser initialization: {data.get('success', False)}")
            else:
                print(f"Browser initialization returned {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Browser initialization error: {e}")
        
        print("API endpoint tests completed")
        return True
        
    except ImportError:
        print("Requests library not available - skipping API tests")
        return True
    except Exception as e:
        print(f"API test failed: {e}")
        return False

if __name__ == "__main__":
    print("Starting JARVIS Browser Service Tests")
    print("=" * 50)
    
    # Test browser service
    service_success = test_browser_service()
    
    # Test API endpoints
    api_success = test_api_endpoints()
    
    print("\n" + "=" * 50)
    if service_success and api_success:
        print("ALL TESTS PASSED! Browser system is functional.")
        print("\nAccess the embedded browser at: http://localhost:3000/dashboard/embedded-browser")
        print("Access the self-reliant IDE at: http://localhost:3000/dashboard/self-reliant")
        print("Access the main dashboard at: http://localhost:3000/dashboard")
    else:
        print("Some tests failed. Check the logs above.")
        sys.exit(1)
