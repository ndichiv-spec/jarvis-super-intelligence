import json, sqlite3
conn = sqlite3.connect(r'F:\AI\Jarvis-super-intelligence-\jarvis_data\jarvis.db')
cur = conn.cursor()
cur.execute("SELECT key, value FROM jarvis_kv")
for k, v in cur.fetchall():
    try:
        d = json.loads(v)
        if isinstance(d, dict) and d.get('email') == 'ndichiv@gmail.com':
            print('KEY:', k)
            print(json.dumps(d, indent=2))
    except Exception:
        pass
conn.close()
