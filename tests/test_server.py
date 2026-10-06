#!/usr/bin/env python3
"""Test Flask server - minimal version to debug"""

# Legacy debugging script (no test_* functions). It runs module-level work
# (prints, Flask app creation, web_server.py import) and calls sys.exit(1)
# when Flask is missing, which crashes pytest collection. Skip the module.
import pytest

pytest.importorskip("flask")

import sys
import traceback

print("=== Testing Flask Server ===")

# Test 1: Import Flask
try:
    from flask import Flask, render_template, jsonify

    print("[OK] Flask imported")
except Exception as e:
    print(f"[FAIL] Flask import: {e}")
    sys.exit(1)

# Test 2: Create minimal app
try:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    print("[OK] Flask app created")
except Exception as e:
    print(f"[FAIL] App creation: {e}")
    sys.exit(1)


# Test 3: Add route
@app.route("/")
def index():
    return "JARVIS Server Works!"


# Test 4: Test with client
try:
    client = app.test_client()

    # Test index
    r = client.get("/")
    print(f"[TEST] GET / = {r.status_code}")

    # Test static files
    r2 = client.get("/static/holographic.css")
    print(f"[TEST] CSS = {r2.status_code}")

    r3 = client.get("/static/script.js")
    print(f"[TEST] JS = {r3.status_code}")

    # Test template
    from flask import render_template_string

    test_html = """
    <!DOCTYPE html>
    <html>
    <head><link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}"></head>
    <body>Test</body>
    </html>
    """
    with app.test_request_context():
        from flask import url_for

        print(f"[TEST] url_for works: {url_for('static', filename='test.css')}")

except Exception as e:
    print(f"[FAIL] Test client: {e}")
    traceback.print_exc()

print("\n=== Testing with full web_server.py ===")

# Now try importing the real web_server
import importlib.util

spec = importlib.util.spec_from_file_location("web_server", "web_server.py")
try:
    ws = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ws)
    print("[OK] web_server.py imported successfully")

    # Test with the real app
    client = ws.app.test_client()
    r = client.get("/")
    print(f"[REAL] GET / = {r.status_code}")
    print(f"[REAL] Content length: {len(r.data)} bytes")

    if r.status_code == 200:
        print(f"[REAL] First 200 chars: {r.data[:200]}")

except Exception as e:
    print(f"[FAIL] web_server.py: {e}")
    traceback.print_exc()

print("\n=== Done ===")
