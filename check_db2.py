import sqlite3
conn = sqlite3.connect(r'F:\AI\Jarvis-super-intelligence-\jarvis_data\jarvis.db')
cur = conn.cursor()
cur.execute("SELECT key, value FROM jarvis_kv LIMIT 50")
rows = cur.fetchall()
for k, v in rows:
    # Try to print truncated
    if v and len(str(v)) > 120:
        print(k, ':', str(v)[:120] + '...')
    else:
        print(k, ':', v)
conn.close()
