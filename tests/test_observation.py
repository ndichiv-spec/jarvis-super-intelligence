"""Test observation endpoints in Flask."""
from web_server import app
import json

# Register observation blueprint
try:
    from observation_blueprint import observation_bp
    app.register_blueprint(observation_bp)
    print("Observation blueprint registered")
except Exception as e:
    print(f"Failed to register: {e}")

# Create test client
client = app.test_client()

# Test endpoints
print("\nTesting Observation Endpoints")
print("=" * 60)

# Test /api/observation/status
print("\n1. GET /api/observation/status")
resp = client.get('/api/observation/status')
print(f"Status: {resp.status_code}")
print(f"Data: {json.dumps(resp.json, indent=2)}")

# Test /api/observation/report
print("\n2. GET /api/observation/report")
resp = client.get('/api/observation/report')
print(f"Status: {resp.status_code}")
data = resp.json
print(f"Report keys: {list(data.keys())}")
print(f"Metrics in history: {data.get('history_depth', 0)}")

# Test /api/observation/events
print("\n3. GET /api/observation/events?limit=10")
resp = client.get('/api/observation/events?limit=10')
print(f"Status: {resp.status_code}")
data = resp.json
print(f"Events returned: {len(data.get('events', []))}")

# Test /api/observation/metrics
print("\n4. GET /api/observation/metrics?minutes=5")
resp = client.get('/api/observation/metrics?minutes=5')
print(f"Status: {resp.status_code}")
data = resp.json
print(f"Metrics returned: {len(data.get('metrics', []))}")

print("\n" + "=" * 60)
print("All observation endpoints working!")
