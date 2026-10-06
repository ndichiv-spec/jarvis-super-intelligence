import requests

tests = [
    ("/api/status", "GET"),
    ("/api/system/status", "GET"),
    ("/api/system/processes?limit=5", "GET"),
    ("/api/knowledge", "GET"),
]

for endpoint, method in tests:
    try:
        if method == "GET":
            r = requests.get(f"http://127.0.0.1:5000{endpoint}", timeout=10)
            print(f"✓ {endpoint}: {r.status_code}")
    except Exception as e:
        print(f"✗ {endpoint}: {str(e)[:50]}")
