import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from app import create_app
from app.db import backend, database_target, postgres_sql, connect, add_message, Database
from app.migrations import migrate_postgres, validate_schema, postgres_files, check_history
import hashlib

class DatabaseBoundary(unittest.TestCase):
    def test_configuration(self):
        self.assertEqual(database_target({'DATABASE_PATH': 'local.db'}), 'local.db')
        self.assertEqual(backend('postgres://localhost/masterment_test'), 'postgresql')
        with self.assertRaises(ValueError): database_target({'DATABASE_URL': 'mysql://example/db'})
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://localhost/masterment_test', 'APP_ENV': 'development'}), patch('app.migrations.validate_schema') as validate, patch('app.db.init_db') as init:
            app = create_app()
            self.assertEqual(database_target(app.config), 'postgresql://localhost/masterment_test')
            validate.assert_called_once_with('postgresql://localhost/masterment_test')
            init.assert_not_called()

    def test_parameter_conversion_preserves_literals(self):
        self.assertEqual(postgres_sql("SELECT '?' AS literal, ? AS value, 'it''s ?' AS quoted"),
                         "SELECT '?' AS literal, %s AS value, 'it''s ?' AS quoted")
        raw = MagicMock()
        db = Database(raw, 'postgresql')
        db.execute("SELECT ? WHERE '50%' = '50%'", ("'; DROP TABLE leads;--",))
        raw.execute.assert_called_once_with("SELECT %s WHERE '50%%' = '50%%'", ("'; DROP TABLE leads;--",))

    def test_commit_rollback_close_and_lock(self):
        import psycopg
        for failure in (False, True):
            raw = MagicMock()
            with patch.object(psycopg, 'connect', return_value=raw):
                try:
                    with connect('postgresql://localhost/masterment_test') as db:
                        db.begin_write()
                        if failure: raise ValueError('test')
                except ValueError: pass
            raw.execute.assert_called_once_with('SELECT pg_advisory_xact_lock(734821906)', None)
            (raw.rollback if failure else raw.commit).assert_called_once()
            raw.close.assert_called_once()

    def test_postgres_message_returning(self):
        raw = MagicMock()
        raw.execute.return_value.fetchone.return_value = {'id': 42}
        self.assertEqual(add_message(Database(raw,'postgresql'), 'cid', 'user', 'Hello'), 42)
        self.assertIn('RETURNING id', raw.execute.call_args_list[0].args[0])

    def test_postgres_migration_boundary_and_history(self):
        db = MagicMock()
        db.execute.return_value.__iter__.return_value = iter([])
        with patch('app.migrations.connect') as connection:
            connection.return_value.__enter__.return_value = db
            migrate_postgres('postgresql://localhost/masterment_test')
        db.begin_write.assert_called_once()
        self.assertEqual(db.executescript.call_count, 2)
        for sql in [call.args[0] for call in db.executescript.call_args_list]:
            for unsupported in ('PRAGMA', 'AUTOINCREMENT', 'INSERT OR'):
                self.assertNotIn(unsupported, sql)
        files = postgres_files()
        checksums = {v:hashlib.sha256(f.read_text(encoding='utf-8').encode()).hexdigest() for v,f in files.items()}
        check_history(checksums, files)
        with self.assertRaises(RuntimeError): check_history({0:'changed',1:'changed'}, files)
        with self.assertRaises(RuntimeError): check_history({}, files)

    def test_read_only_startup_missing_schema_does_not_create_file(self):
        target = Path(__file__).resolve().parent / 'must-not-create.db'
        self.assertFalse(target.exists())
        with self.assertRaises(RuntimeError): validate_schema(target)
        self.assertFalse(target.exists())
        db = MagicMock()
        with patch('app.migrations.connect') as connection:
            connection.return_value.__enter__.return_value = db
            with self.assertRaises(RuntimeError): validate_schema('postgresql://localhost/masterment_test')
            connection.assert_called_once_with('postgresql://localhost/masterment_test', read_only=True)
            self.assertFalse(db.executescript.called)
            self.assertFalse(db.begin_write.called)
