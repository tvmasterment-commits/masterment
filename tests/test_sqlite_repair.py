import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app.db import init_db
from rehearse_sqlite_repair import rehearse


class RepairRehearsal(unittest.TestCase):
    def test_legacy_data_preserved_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.sqlite3'
            init_db(str(source))
            with closing(sqlite3.connect(source)) as db:
                cid = '11111111-1111-4111-8111-111111111111'
                db.execute('INSERT INTO conversations VALUES (?,?,?)', (cid, 'old', 'old'))
                db.execute("INSERT INTO leads(conversation_id,name,status,created_at,updated_at) VALUES (?,?,?,?,?)", (cid, 'Synthetic customer', 'Booked', 'old', 'old'))
                db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES (?,?,?,?)", (cid, 'user', 'Synthetic legacy inquiry', 'old'))
                db.commit()
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            result = rehearse(source, Path(directory) / 'copies')
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertTrue(result['original_rows_preserved'])
            self.assertEqual(result['unowned_legacy_conversations'], 1)
            self.assertEqual(result['migration_history_after'][0][0], 1)
            self.assertEqual(result['chatbot_smoke_tests'], 'passed on separate copy')

    def test_partial_schema_aborts_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.sqlite3'
            init_db(str(source))
            with closing(sqlite3.connect(source)) as db:
                db.execute('ALTER TABLE conversations ADD COLUMN owner_hash TEXT')
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            with self.assertRaises(sqlite3.OperationalError):
                rehearse(source, Path(directory) / 'copies')
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())
