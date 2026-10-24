import sqlite3
from urllib.parse import unquote

def handle(value: str, root: str):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE items(id INTEGER, visibility TEXT, name TEXT)")
    db.executemany("INSERT INTO items VALUES(?,?,?)", [(1, "PUBLIC", "hello"), (2, "PRIVATE", "private")])
    return db.execute("SELECT id, visibility FROM items WHERE visibility=? AND name=?", ("PUBLIC", value)).fetchall()
