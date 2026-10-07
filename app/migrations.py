"""Transactional, checksummed additive migrations. No application factory import."""
import hashlib
import sqlite3
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1] / 'migrations'


def migrate(path):
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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    if not Path(args.database).is_file():
        parser.error('Database must already exist; back it up before migrating.')
    migrate(args.database)
