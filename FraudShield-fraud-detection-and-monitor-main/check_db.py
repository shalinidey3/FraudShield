import sqlite3

conn = sqlite3.connect("database/fraud.db")
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM transactions")

print("Rows:", cur.fetchone()[0])

conn.close()