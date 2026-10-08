import json
import sqlite3
conn = sqlite3.connect(r'F:\AI\Jarvis-super-intelligence-\jarvis_data\jarvis.db')
cur = conn.cursor()
cur.execute("SELECT key, value FROM jarvis_kv WHERE key='00000000-0000-0000-0000-000000000001'")
rows = cur.fetchall()
for k, v in rows:
    try:
        d = json.loads(v)
        print(json.dumps(d, indent=2))
    except:
        print(v)
conn.close()
