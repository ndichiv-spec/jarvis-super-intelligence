import sqlite3, json, os, hashlib, hmac

db_path = os.path.join(r"F:\AI\Jarvis-super-intelligence-", "jarvis_data", "jarvis.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get the admin user
c.execute("SELECT key, value FROM jarvis_kv WHERE store_name='users'")
for key, val in c.fetchall():
    user = json.loads(val)
    print(f"User id={key}")
    print(f"  email={user.get('email')}")
    print(f"  username={user.get('username')}")
    print(f"  roles={user.get('roles')}")
    print(f"  is_admin={user.get('is_admin')}")
    print(f"  password_hash={user.get('password_hash', 'N/A')}")

# Now verify what password the hash corresponds to
stored_hash = user.get("password_hash", "")
parts = stored_hash.split("$")
if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
    _, iterations, salt, digest = parts
    iterations = int(iterations)
    
    # Check with videlis@254
    test_pw = "videlis@254"
    computed = hashlib.pbkdf2_hmac("sha256", test_pw.encode(), bytes.fromhex(salt), iterations).hex()
    match_videlis = hmac.compare_digest(computed, digest)
    print(f"\nPassword 'videlis@254' matches hash: {match_videlis}")
    
    # Check with test-password-for-testing
    test_pw2 = "test-password-for-testing"
    computed2 = hashlib.pbkdf2_hmac("sha256", test_pw2.encode(), bytes.fromhex(salt), iterations).hex()
    match_test = hmac.compare_digest(computed2, digest)
    print(f"Password 'test-password-for-testing' matches hash: {match_test}")

conn.close()
