import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@contextmanager
def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db(path):
    with connect(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
          id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leads (
          id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id),
          name TEXT, phone TEXT, email TEXT, service TEXT, project_date TEXT, location TEXT,
          budget TEXT, description TEXT, status TEXT NOT NULL DEFAULT 'New', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL REFERENCES conversations(id),
          role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
        CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at DESC);
        """)

def ensure_conversation(db, conversation_id):
    stamp = now()
    db.execute("INSERT OR IGNORE INTO conversations(id,created_at,updated_at) VALUES(?,?,?)", (conversation_id, stamp, stamp))

def add_message(db, conversation_id, role, content):
    stamp = now()
    db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)", (conversation_id, role, content, stamp))
    db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (stamp, conversation_id))

def upsert_lead(db, conversation_id, fields):
    stamp = now()
    db.execute("INSERT OR IGNORE INTO leads(conversation_id,created_at,updated_at) VALUES(?,?,?)", (conversation_id, stamp, stamp))
    allowed = {k: v for k, v in fields.items() if k in {"name","phone","email","service","project_date","location","budget","description"} and isinstance(v, str) and v.strip()}
    if allowed:
        assignments = ",".join(f"{k}=COALESCE(NULLIF(?,''),{k})" for k in allowed)
        db.execute(f"UPDATE leads SET {assignments}, updated_at=? WHERE conversation_id=?", (*allowed.values(), stamp, conversation_id))
    return db.execute("SELECT * FROM leads WHERE conversation_id=?", (conversation_id,)).fetchone()
