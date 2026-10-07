import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def backend(target):
    value = str(target)
    if value.startswith(('postgresql://', 'postgres://')):
        return 'postgresql'
    if '://' in value:
        raise ValueError('Unsupported database URL scheme')
    return 'sqlite'

def database_target(config):
    url = config.get('DATABASE_URL')
    if url:
        if backend(url) != 'postgresql':
            raise ValueError('DATABASE_URL must be a PostgreSQL URL')
        return url
    return config['DATABASE_PATH']

def postgres_sql(sql):
    # Translate only bind markers outside SQL string/identifier literals.
    result = []
    quote = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote:
            result.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    result.append(char)
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            result.append(char)
        else:
            result.append('%s' if char == '?' else char)
        index += 1
    return ''.join(result)

class Database:
    def __init__(self, raw, dialect):
        self.raw, self.dialect = raw, dialect

    def execute(self, sql, parameters=()):
        if self.dialect == 'postgresql':
            if parameters:
                sql = postgres_sql(sql.replace('%', '%%'))
            return self.raw.execute(sql, parameters or None)
        return self.raw.execute(sql, parameters)

    def executescript(self, sql):
        for statement in sql.split(';'):
            if statement.strip(): self.execute(statement)

    def begin_write(self):
        if self.dialect == 'sqlite':
            self.execute('BEGIN IMMEDIATE')
        else:
            # Mirrors SQLite's short, serialized writers, including first-turn
            # request races with no existing conversation row to lock.
            self.execute('SELECT pg_advisory_xact_lock(734821906)')

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

@contextmanager
def connect(path, read_only=False):
    dialect = backend(path)
    if dialect == 'postgresql':
        import psycopg
        from psycopg.rows import dict_row
        raw = psycopg.connect(path, row_factory=dict_row, connect_timeout=10)
        if read_only: raw.read_only = True
    else:
        if read_only:
            from pathlib import Path
            raw = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
        else:
            raw = sqlite3.connect(path, timeout=10)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA foreign_keys = ON")
    db = Database(raw, dialect)
    try:
        yield db
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()

def init_db(path):
    if backend(path) != 'sqlite':
        raise ValueError('PostgreSQL requires explicit migrations')
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
    db.execute("INSERT INTO conversations(id,created_at,updated_at) VALUES(?,?,?) ON CONFLICT(id) DO NOTHING", (conversation_id, stamp, stamp))

def add_message(db, conversation_id, role, content):
    stamp = now()
    cursor = db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?) RETURNING id", (conversation_id, role, content, stamp))
    row = cursor.fetchone()
    message_id = row['id']
    db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (stamp, conversation_id))
    return message_id

def upsert_lead(db, conversation_id, fields):
    stamp = now()
    db.execute("INSERT INTO leads(conversation_id,created_at,updated_at) VALUES(?,?,?) ON CONFLICT(conversation_id) DO NOTHING", (conversation_id, stamp, stamp))
    allowed = {k: v for k, v in fields.items() if k in {"name","phone","email","service","project_date","location","budget","description"} and isinstance(v, str) and v.strip()}
    if allowed:
        assignments = ",".join(f"{k}=COALESCE(NULLIF(?,''),{k})" for k in allowed)
        db.execute(f"UPDATE leads SET {assignments}, updated_at=? WHERE conversation_id=?", (*allowed.values(), stamp, conversation_id))
    return db.execute("SELECT * FROM leads WHERE conversation_id=?", (conversation_id,)).fetchone()
