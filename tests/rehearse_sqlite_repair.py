"""Back up an existing accessible SQLite file and migrate copies only.

Never applies a migration to the supplied source. Output contains schema,
counts and checksums only, never customer records or connection credentials.
"""
import argparse
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@contextmanager
def readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    try:
        yield db
    finally:
        db.close()


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def check(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RuntimeError('Integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchone():
        raise RuntimeError('Foreign key check failed')


def snapshot(source, target):
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with readonly(source) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
        check(dst)


def checksum(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def fingerprint(db, table, columns):
    # Order-independent fingerprints retain duplicate rows, without printing data.
    hashes = []
    for row in db.execute('SELECT ' + ','.join(map(quote, columns)) + ' FROM ' + quote(table)):
        hashes.append(hashlib.sha256(repr(tuple(row)).encode()).digest())
    return hashlib.sha256(b''.join(sorted(hashes))).hexdigest()


def rehearse(source, output):
    if not source.is_file():
        raise RuntimeError('Existing source file required')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    backup, repaired, smoke = [output / name for name in ('verified-backup.sqlite3', 'rehearsal.sqlite3', 'smoke-test.sqlite3')]
    snapshot(source, backup)
    original_checksum = checksum(backup)
    with readonly(backup) as db:
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
        tables = [row[1] for row in schema if row[0] == 'table']
        # All original rows/columns are compared after migration, including custom tables.
        columns = {table: [row[1] for row in db.execute('PRAGMA table_info(' + quote(table) + ')')] for table in tables}
        fingerprints = {table: fingerprint(db, table, cols) for table, cols in columns.items()}
        counts = {table: db.execute('SELECT COUNT(*) FROM ' + quote(table)).fetchone()[0] for table in tables}
        history = db.execute('SELECT version,checksum FROM schema_migrations ORDER BY version').fetchall() if 'schema_migrations' in tables else []
        report = {'backup_integrity': 'ok', 'backup_sha256': original_checksum,
                  'schema_before': schema, 'row_counts_before': counts,
                  'migration_history_before': history, 'user_version_before': db.execute('PRAGMA user_version').fetchone()[0]}
    snapshot(backup, repaired)
    from app.migrations import migrate, validate_schema
    migrate(str(repaired))
    validate_schema(str(repaired))
    migrated_checksum = checksum(repaired)
    migrate(str(repaired))
    validate_schema(str(repaired))
    if checksum(repaired) != migrated_checksum:
        raise RuntimeError('Repeated migration changed the repaired database')
    with readonly(repaired) as db:
        check(db)
        for table, cols in columns.items():
            # Migration history is expected to gain a migration entry.
            if table == 'schema_migrations':
                for version, value in history:
                    if db.execute('SELECT checksum FROM schema_migrations WHERE version=?', (version,)).fetchone() != (value,):
                        raise RuntimeError('Prior migration history changed')
            elif fingerprint(db, table, cols) != fingerprints[table]:
                raise RuntimeError('Original customer rows changed')
        report['migration_history_after'] = db.execute('SELECT version,checksum FROM schema_migrations ORDER BY version').fetchall()
        report['unowned_legacy_conversations'] = db.execute('SELECT COUNT(*) FROM conversations WHERE owner_hash IS NULL').fetchone()[0]
    snapshot(repaired, smoke)
    from app import create_app
    with patch.dict(os.environ, {'APP_ENV': 'development', 'OPENAI_API_KEY': ''}):
        app = create_app({'TESTING': True, 'DATABASE_PATH': str(smoke), 'DATABASE_URL': '',
                          'AUTO_MIGRATE': False, 'SECRET_KEY': 'local-rehearsal-only',
                          'CHAT_RATE_LIMIT': 10000,
                          'KNOWLEDGE_PATH': str(ROOT / 'knowledge/business.json')})
        client = app.test_client()
        with readonly(repaired) as db:
            legacy = db.execute('SELECT id FROM conversations WHERE owner_hash IS NULL LIMIT 1').fetchone()
        if legacy and client.get('/api/conversations/' + legacy[0]).status_code != 404:
            raise RuntimeError('Legacy conversation ownership protection failed')
        import uuid
        payload = {'message': "I'm looking for photography.", 'request_id': str(uuid.uuid4())}
        first = client.post('/api/chat', json=payload)
        if first.status_code != 200 or not first.json.get('reply'):
            raise RuntimeError('Chat smoke test failed')
        if client.post('/api/chat', json=payload).json != first.json:
            raise RuntimeError('Chat replay test failed')
        cid = first.json['conversation_id']
        second = client.post('/api/chat', json={'conversation_id': cid, 'message': 'My name is Test Customer. rehearsal@example.invalid.'})
        if second.status_code != 200 or second.json['captured'].get('email') != 'rehearsal@example.invalid':
            raise RuntimeError('Lead capture test failed')
        if len(client.get('/api/conversations/' + cid).json['messages']) != 4:
            raise RuntimeError('History test failed')
        if app.test_client().get('/api/conversations/' + cid).status_code != 404:
            raise RuntimeError('Cross-visitor ownership test failed')
    if checksum(backup) != original_checksum:
        raise RuntimeError('Backup changed during rehearsal')
    report.update(original_rows_preserved=True, legacy_ownership_secure=True,
                  chatbot_smoke_tests='passed on separate copy', source_migrated=False)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New private output directory, preferably under ignored instance/')
    args = parser.parse_args()
    try:
        print(json.dumps(rehearse(args.source, args.output), indent=2))
    except Exception as error:
        # SQL errors can contain identifiers or customer values. Do not print them.
        sys.exit('Rehearsal stopped: ' + type(error).__name__ + '. Source was not migrated; do not apply a production repair.')
