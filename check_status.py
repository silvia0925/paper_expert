import sqlite3, json
conn = sqlite3.connect(r"C:\Users\Administrator\paper_expert-library\metadata.db")
conn.row_factory = sqlite3.Row

logs = conn.execute("SELECT * FROM watch_logs ORDER BY run_at DESC LIMIT 5").fetchall()
print("=== Watch Logs ===")
for l in logs:
    print(dict(l))

topics = conn.execute("SELECT * FROM watch_topics").fetchall()
print("\n=== Watch Topics ===")
for t in topics:
    d = dict(t)
    d["queries_json_parsed"] = json.loads(d["queries_json"])
    print(f"ID={d['id']}, name={d['name']}, active={d['is_active']}")

count = conn.execute("SELECT COUNT(*) as c FROM papers").fetchone()["c"]
print(f"\nTotal papers: {count}")
recent = conn.execute("SELECT id, title, year, state FROM papers ORDER BY id DESC LIMIT 10").fetchall()
for r in recent:
    print(f"  #{r['id']} [{r['year']}] [{r['state']}] {r['title'][:80]}")
conn.close()
