import requests
import json
import time

# Test smart responses
queries = [
    "hello",
    "what time is it",
    "who are you",
    "what can you do",
    "help",
    "thank you",
    "goodbye",
    "what is the weather",
    "how are you",
    "system status",
]

base_url = "http://127.0.0.1:5000"

print("Testing JARVIS Smart Response Engine\n" + "=" * 50)

for q in queries:
    try:
        start = time.time()
        r = requests.post(f"{base_url}/api/chat", json={"message": q}, timeout=10)
        elapsed = time.time() - start

        if r.status_code == 200:
            data = r.json()
            print(f"\nQ: {q}")
            print(f"A: {data.get('response', 'N/A')[:80]}...")
            print(f"Source: {data.get('source', 'N/A')} | Time: {elapsed:.4f}s")
        else:
            print(f"\nQ: {q} - Error: {r.status_code}")
    except Exception as e:
        print(f"\nQ: {q} - Failed: {str(e)[:50]}")

print("\n" + "=" * 50)
print("Test complete!")
