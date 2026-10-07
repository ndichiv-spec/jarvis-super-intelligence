from fastapi.testclient import TestClient
from jarvis_backend.main import app

client = TestClient(app)

# Register a user
reg = client.post('/api/v1/auth/register', json={
    'email': 'verify3@example.com', 'username': 'verify3', 'password': 'S3cret!pass',
}).json()

verification_token = reg.get('verification_token')
print('Token:', verification_token[:20] + '...' if verification_token else None)

# Verify email first time
r1 = client.post('/api/v1/auth/verify-email', json={'token': verification_token})
print('First verify status:', r1.status_code)
print('First verify response:', r1.json())

# Try to verify again
r2 = client.post('/api/v1/auth/verify-email', json={'token': verification_token})
print('Second verify status:', r2.status_code)
print('Second verify response:', r2.json())