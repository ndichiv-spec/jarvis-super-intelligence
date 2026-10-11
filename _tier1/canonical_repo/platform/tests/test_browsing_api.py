import requests


def run_browsing_api_smoke():
    base = "http://127.0.0.1:8000"
    print("Testing JARVIS browsing API")
    print("=" * 50)

    response = requests.get(f"{base}/api/v1/health/status", timeout=10)
    print(f"Health: {response.json()}")

    response = requests.get(f"{base}/api/v1/browsing/status", timeout=10)
    print(f"Browsing Status: {response.json()['domain_classifier']}")

    payload = {"query": "python programming", "num_results": 5}
    response = requests.post(f"{base}/api/v1/browsing/search", json=payload, timeout=30)
    data = response.json()
    print(f"Search: {data['total_results']} results in {data['processing_time_ms']:.0f}ms")
    print(f"  Domain: {data['domain']}, Engines: {data['engines_used']}")

    if data["results"]:
        urls = [result["url"] for result in data["results"]]
        feedback = {
            "query": "python programming",
            "displayed_results": urls,
            "clicked_url": urls[0],
            "helpful": True,
            "rating": 0.9,
        }
        response = requests.post(
            f"{base}/api/v1/browsing/feedback", json=feedback, timeout=10
        )
        print(f"Feedback: {response.json()['success']}")

    response = requests.get(
        f"{base}/api/v1/browsing/learning/stats", timeout=10
    )
    stats = response.json()
    print(f"Learning: {stats['engine_stats']['total_interactions']} interactions")

    print("=" * 50)


if __name__ == "__main__":
    run_browsing_api_smoke()
