import requests


def run_api_smoke():
    endpoints = (
        "/api/status",
        "/api/system/status",
        "/api/system/processes?limit=5",
        "/api/knowledge",
    )
    for endpoint in endpoints:
        try:
            response = requests.get(f"http://127.0.0.1:5000{endpoint}", timeout=10)
            print(f"HTTP {response.status_code}: {endpoint}")
        except requests.RequestException as exc:
            print(f"FAIL {endpoint}: {str(exc)[:50]}")


if __name__ == "__main__":
    run_api_smoke()
