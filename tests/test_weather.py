import requests
import json

try:
    r = requests.get("http://127.0.0.1:5000/api/web/weather", timeout=30)
    print("Status:", r.status_code)
    print("Response:", r.text[:500])
except Exception as e:
    print("Error:", e)
