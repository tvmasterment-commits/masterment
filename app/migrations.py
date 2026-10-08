"""Transactional, checksummed additive migrations. No application factory import."""
import hashlib
import sqlite3
from pathlib import Path
from .db import backend, connect

DIRECTORY = Path(__file__).resolve().parents[1] / 'migrations'


def migrate(path):
    if backend(path) == 'postgresql':
        return migrate_postgres(path)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, checksum TEXT NOT NULL)')
        files = sorted(DIRECTORY.glob('*.sql'))
        known = {int(p.name.split('_')[0]): p for p in files}
        applied = dict(db.execute('SELECT version,checksum FROM schema_migrations'))
        if set(applied) - set(known) or db.execute('PRAGMA user_version').fetchone()[0] != max(applied, default=0):
            raise RuntimeError('Unsupported database schema version')
        for version, file in known.items():
            sql = file.read_text(encoding='utf-8')
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError('Applied migration checksum mismatch')
                continue
            for statement in sql.split(';'):
                if statement.strip():
                    db.execute(statement)
            db.execute('INSERT INTO schema_migrations VALUES (?,?)', (version, checksum))
            db.execute(f'PRAGMA user_version={version}')
        required = {'owner_hash', 'revision'}
        if not required.issubset({row[1] for row in db.execute('PRAGMA table_info(conversations)')}):
            raise RuntimeError('Incomplete conversation schema')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Database foreign key validation failed')
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def postgres_files():
    return {int(p.name.split('_')[0]): p for p in sorted((DIRECTORY / 'postgresql').glob('*.sql'))}


def check_history(applied, files):
    if set(applied) != set(files):
        raise RuntimeError('Database requires explicit migration')
    for version, file in files.items():
        if applied[version] != hashlib.sha256(file.read_text(encoding='utf-8').encode()).hexdigest():
            raise RuntimeError('Applied migration checksum mismatch')


def validate_schema(target):
    """Read-only startup check: never bootstrap or migrate production data."""
    dialect = backend(target)
    files = postgres_files() if dialect == 'postgresql' else {
        int(p.name.split('_')[0]): p for p in sorted(DIRECTORY.glob('*.sql'))}
    try:
        with connect(target, read_only=True) as db:
            applied = {r['version']: r['checksum'] for r in db.execute('SELECT version,checksum FROM schema_migrations')}
            check_history(applied, files)
            if dialect == 'sqlite' and db.execute('PRAGMA user_version').fetchone()[0] != max(applied):
                raise RuntimeError('Unsupported database schema version')
            # Also fail clearly if tracked tables/columns have been removed.
            for sql in [
                'SELECT id,owner_hash,revision,created_at,updated_at FROM conversations LIMIT 0',
                'SELECT id,conversation_id,name,phone,email,service,project_date,location,budget,description,status,created_at,updated_at,sales_status,sales_intent,intent_confidence,service_id,package_id,conversation_summary,next_action,field_evidence,missing_fields,purchase_requested,legacy_review_required FROM leads LIMIT 0',
                'SELECT id,conversation_id,role,content,created_at FROM messages LIMIT 0',
                'SELECT request_id,conversation_id,owner_hash,input_hash,revision,user_message_id,state,response_json,created_at FROM chat_requests LIMIT 0',
                'SELECT id,conversation_id,revision,from_state,to_state,intent,created_at FROM sales_transitions LIMIT 0']:
                db.execute(sql)
    except Exception:
        # Do not expose connection strings or credentials through startup errors.
        raise RuntimeError('Database schema unavailable or incompatible; run explicit migrations first') from None


def migrate_postgres(target):
    """Explicit transactional migration only; application startup never calls it."""
    files = postgres_files()
    with connect(target) as db:
        db.begin_write()
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, checksum TEXT NOT NULL)')
        applied = {r['version']: r['checksum'] for r in db.execute('SELECT version,checksum FROM schema_migrations')}
        if set(applied) - set(files): raise RuntimeError('Unsupported database schema version')
        for version, file in files.items():
            sql = file.read_text(encoding='utf-8')
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if version in applied:
                if applied[version] != checksum: raise RuntimeError('Applied migration checksum mismatch')
                continue
            db.executescript(sql)
            db.execute('INSERT INTO schema_migrations VALUES (?,?)', (version, checksum))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--database')
    parser.add_argument('--postgres', action='store_true', help='Explicitly migrate DATABASE_URL from environment')
    args = parser.parse_args()
    if args.postgres:
        import os
        target = os.environ.get('DATABASE_URL', '').strip()
        if not target or backend(target) != 'postgresql': parser.error('Set DATABASE_URL to a PostgreSQL URL')
        if args.database: parser.error('Choose --postgres or --database')
        migrate(target)
    elif not args.database or not Path(args.database).is_file():
        parser.error('Database must already exist; back it up before migrating.')
    else:
        migrate(args.database)
