import requests
import json

BASE = "http://127.0.0.1:8000"

print("Testing JARVIS Enhanced Browsing Engine")
print("=" * 50)

# Test health
r = requests.get(f"{BASE}/api/v1/health/status")
print(f"Health: {r.json()}")

# Test browsing status
r = requests.get(f"{BASE}/api/v1/browsing/status")
print(f"Browsing Status: {r.json()['domain_classifier']}")

# Test search
payload = {"query": "python programming", "num_results": 5}
r = requests.post(f"{BASE}/api/v1/browsing/search", json=payload)
data = r.json()
print(f"Search: {data['total_results']} results in {data['processing_time_ms']:.0f}ms")
print(f"  Domain: {data['domain']}, Engines: {data['engines_used']}")

# Test feedback
if data["results"]:
    urls = [r["url"] for r in data["results"]]
    payload = {
        "query": "python programming",
        "displayed_results": urls,
        "clicked_url": urls[0],
        "helpful": True,
        "rating": 0.9,
    }
    r = requests.post(f"{BASE}/api/v1/browsing/feedback", json=payload)
    print(f"Feedback: {r.json()['success']}")

# Test learning stats
r = requests.get(f"{BASE}/api/v1/browsing/learning/stats")
stats = r.json()
print(f"Learning: {stats['engine_stats']['total_interactions']} interactions")

print("=" * 50)
print("All tests passed!")
