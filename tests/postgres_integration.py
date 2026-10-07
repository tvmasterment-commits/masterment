"""Opt-in real PostgreSQL tests. Only a loopback test database is accepted.

POSTGRES_TEST_URL must point at an existing disposable local database.
Run: python tests/postgres_integration.py
Each run creates/removes only its own unique schema, never the public schema.
"""
import os
import sys
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from app import create_app
from app.db import connect
from app.migrations import migrate, validate_schema


class RealPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = os.environ.get('POSTGRES_TEST_URL', '')
        parsed = urlparse(original)
        if parsed.scheme not in ('postgres','postgresql') or parsed.hostname not in ('localhost','127.0.0.1','::1') or 'test' not in parsed.path.lower():
            raise RuntimeError('POSTGRES_TEST_URL must be a loopback disposable test database URL')
        cls.original = original
        cls.schema = 'masterment_test_' + uuid.uuid4().hex
        with psycopg.connect(original) as db:
            db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(cls.schema)))
        query = dict(parse_qsl(parsed.query))
        query['options'] = '-c search_path=' + cls.schema
        cls.target = urlunparse(parsed._replace(query=urlencode(query)))
        try:
            migrate(cls.target)
            migrate(cls.target)
            validate_schema(cls.target)
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(cls.original) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(cls.schema)))

    def setUp(self):
        self.app = create_app({'TESTING': True, 'DATABASE_URL': self.target,
            'SECRET_KEY':'local-postgres-test', 'ADMIN_USERNAME':'testadmin',
            'ADMIN_PASSWORD':'testpass', 'CHAT_RATE_LIMIT':1000})
        self.client = self.app.test_client()

    def test_persistence_replay_ownership_and_admin(self):
        from unittest.mock import patch
        rid = str(uuid.uuid4())
        payload = {'message':'I need a cinematic music video in Boston on October 15', 'request_id':rid}
        with patch('app.workflow.model_understanding', return_value=None):
            first = self.client.post('/api/chat', json=payload)
            self.assertEqual(first.status_code,200)
            cid = first.json['conversation_id']
            self.assertEqual(self.client.post('/api/chat',json={**payload,'conversation_id':cid}).json,first.json)
            corrected = self.client.post('/api/chat',json={'message':'Actually October 20','conversation_id':cid,'request_id':str(uuid.uuid4())})
        self.assertEqual(corrected.json['captured']['project_date'],'October 20')
        self.assertEqual(len(self.client.get('/api/conversations/'+cid).json['messages']),4)
        other = self.app.test_client()
        self.assertEqual(other.get('/api/conversations/'+cid).status_code,404)
        with connect(self.target) as db:
            self.assertEqual(db.execute('SELECT revision FROM conversations WHERE id=?',(cid,)).fetchone()['revision'],2)
            self.assertEqual(len(list(db.execute('SELECT * FROM chat_requests WHERE conversation_id=?',(cid,)))),2)
            self.assertTrue(list(db.execute('SELECT * FROM sales_transitions WHERE conversation_id=?',(cid,))))
            lead = db.execute('SELECT * FROM leads WHERE conversation_id=?',(cid,)).fetchone()
        auth = {'Authorization':'Basic dGVzdGFkbWluOnRlc3RwYXNz'}
        self.assertEqual(self.client.get('/admin',headers=auth).status_code,200)
        self.assertEqual(self.client.get('/admin/leads/'+str(lead['id']),headers=auth).status_code,200)
        with self.client.session_transaction() as session: token = session['admin_csrf_token']
        self.assertEqual(self.client.post('/admin/leads/'+str(lead['id'])+'/status',headers={**auth,'X-CSRF-Token':token},json={'status':'Contacted'}).status_code,200)

    def test_concurrent_duplicate_reservation(self):
        import threading
        from unittest.mock import patch
        self.client.get('/api/chat/session')
        cookie = self.client.get_cookie('session').value
        payload = {'message':'I need a music video','request_id':str(uuid.uuid4())}
        ready, release = threading.Event(), threading.Event()
        responses = []
        def model(*args):
            ready.set()
            if not release.wait(10): raise RuntimeError('Test timed out')
            return None
        def first():
            client = self.app.test_client()
            client.set_cookie('session',cookie)
            responses.append(client.post('/api/chat',json=payload))
        with patch('app.workflow.model_understanding',side_effect=model):
            thread = threading.Thread(target=first)
            thread.start()
            try:
                self.assertTrue(ready.wait(10))
                self.assertEqual(self.client.post('/api/chat',json=payload).status_code,202)
            finally:
                release.set()
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(responses[0].status_code,200)
        self.assertEqual(len(self.client.get('/api/conversations/'+responses[0].json['conversation_id']).json['messages']),2)

if __name__ == '__main__': unittest.main()
