import json
import sqlite3
import tempfile
import threading
import unittest
import uuid
import os
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import test_app
from app.db import connect, init_db
from app.migrations import migrate
from app.ai_schema import validate
from ai_fixtures import understanding
from app.assistant import model_understanding, read_knowledge


class CheckpointB(unittest.TestCase):
    setUp = test_app.AppTest.setUp
    tearDown = test_app.AppTest.tearDown

    def turn(self, message, cid=None, rid=None, client=None):
        payload = {'message': message, 'request_id': rid or str(uuid.uuid4())}
        if cid: payload['conversation_id'] = cid
        return (client or self.client).post('/api/chat', json=payload)

    def lead(self, cid):
        with connect(self.db_path) as db:
            return dict(db.execute('SELECT * FROM leads WHERE conversation_id=?', (cid,)).fetchone())

    def test_sales_safety_and_context(self):
        first = self.turn('How much is Growth?').json
        cid = first['conversation_id']
        self.assertEqual(self.lead(cid)['sales_intent'], 'PRICING_QUESTION')
        self.assertNotEqual(self.lead(cid)['sales_status'], 'READY_TO_BOOK')
        self.turn('My name is Jordan. jordan@example.com. October 20 in Boston', cid)
        self.turn("Let's do it", cid)
        self.assertEqual(self.lead(cid)['sales_status'], 'READY_TO_BOOK')
        for message, intent in [('Book me October 20', 'BOOKING_REQUEST'),
                                ('I already paid', 'PAYMENT_REQUEST'),
                                ('I signed the contract', 'CONTRACT_REQUEST'),
                                ('I want a human', 'HUMAN_REQUEST')]:
            self.turn(message, cid)
            saved = self.lead(cid)
            self.assertEqual(saved['sales_intent'], intent)
            self.assertEqual(saved['status'], 'New')
        vague = self.turn("Let's do it").json
        self.assertNotEqual(self.lead(vague['conversation_id'])['sales_status'], 'READY_TO_BOOK')

    def test_corrections(self):
        cid = self.turn('I need a cinematic music video in Boston on October 15').json['conversation_id']
        for text, field, expected in [
            ('Actually October 20', 'project_date', 'October 20'),
            ('Change location to Providence', 'location', 'Providence'),
            ('My budget is $2000', 'budget', '$2000'),
            ('Actually budget is $3000', 'budget', '$3000'),
            ('My name is Jordan', 'name', 'Jordan'),
            ('Change name to Alex', 'name', 'Alex'),
            ('old@example.com', 'email', 'old@example.com'),
            ('Actually new@example.com', 'email', 'new@example.com'),
            ('My phone is 617-555-0100', 'phone', '617-555-0100'),
            ('Actually 617-555-0120', 'phone', '617-555-0120'),
            ('Change concept to bright natural portraits', 'description', 'bright natural portraits'),
            ('Instead I need a website', 'service_id', 'website'),
            ('I want Growth', 'service_id', 'monthly')]:
            self.assertEqual(self.turn(text, cid).status_code, 200)
            self.assertEqual(self.lead(cid)[field], expected)

    def test_ownership_and_request_conflict(self):
        rid = str(uuid.uuid4())
        first = self.turn('I need a music video', rid=rid).json
        cid = first['conversation_id']
        other = self.app.test_client()
        self.assertEqual(other.get('/api/conversations/' + cid).status_code, 404)
        self.assertEqual(self.turn('Hello', cid, client=other).status_code, 404)
        self.assertEqual(self.turn('I need a music video', cid, rid, other).status_code, 409)
        self.assertEqual(self.turn('Different text', cid, rid).status_code, 409)

    def test_pending_replay_and_stale_result(self):
        cid = self.turn('I need a music video on October 15').json['conversation_id']
        cookie = self.client.get_cookie('session').value
        started, release = threading.Event(), threading.Event()
        responses = []
        rid = str(uuid.uuid4())
        def model(history, lead, knowledge):
            if history[-1]['content'] == 'Dark cinematic':
                started.set()
                self.assertTrue(release.wait(10))
                result = understanding('What visual style do you want?')
                result['proposed_updates'] = [{'field': 'project_date', 'value': 'October 15',
                    'message_id': history[-1]['id'], 'quote': 'October 15'}]
                return result
            return None
        def old_turn():
            client = self.app.test_client()
            client.set_cookie('session', cookie)
            responses.append(self.turn('Dark cinematic', cid, rid, client))
        with patch('app.workflow.model_understanding', side_effect=model):
            thread = threading.Thread(target=old_turn)
            thread.start()
            self.assertTrue(started.wait(10))
            try:
                self.assertEqual(self.turn('Dark cinematic', cid, rid).status_code, 202)
                self.assertEqual(self.turn('Actually October 20', cid).status_code, 200)
            finally:
                release.set()
                thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertTrue(responses[0].json['stale'])
        self.assertEqual(self.lead(cid)['project_date'], 'October 20')
        history = self.client.get('/api/conversations/' + cid).json['messages']
        self.assertEqual(sum(m['content'] == 'Dark cinematic' for m in history), 1)
        self.assertEqual(sum(m['role'] == 'assistant' for m in history), 2)

    def test_schema_rejects_malformed(self):
        for value in [None, {}, {**understanding('Hello'), 'confidence': float('nan')},
                      {**understanding('Hello'), 'intent': 'PAID'},
                      {**understanding('Hello'), 'extra': True}]:
            with self.assertRaises(ValueError): validate(value)

    def test_provider_malformed_and_unsupported_ids_fall_back(self):
        knowledge = read_knowledge(self.app.config['KNOWLEDGE_PATH'])
        history = [{'id': 1, 'role': 'user', 'content': 'I need a music video'}]
        unsupported = understanding('Hello')
        unsupported['proposed_updates'] = [{'field': 'service_id', 'value': 'spaceship', 'message_id': 1, 'quote': 'music video'}]
        for content in ['not JSON', json.dumps({'intent': 'PAID'}), json.dumps(unsupported)]:
            client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs:
                SimpleNamespace(status="completed", output=[], output_text=content)))
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}), patch('app.assistant.OpenAI', return_value=client):
                self.assertIsNone(model_understanding(history, {}, knowledge))

    def test_model_context_is_bounded(self):
        knowledge = read_knowledge(self.app.config['KNOWLEDGE_PATH'])
        history = [{'id': i, 'role': 'user', 'content': 'x' * 4000} for i in range(100)]
        captured = []
        def create(**kwargs):
            captured.append(kwargs)
            return SimpleNamespace(status="completed", output=[], output_text=json.dumps(understanding('Hello')))
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}), patch('app.assistant.OpenAI', return_value=client):
            self.assertIsNotNone(model_understanding(history, {'description': 'x' * 100000}, knowledge))
        messages = captured[0]['input']
        self.assertLessEqual(len(messages), 13)
        self.assertLess(sum(len(m['content']) for m in messages), 25000)

    def test_package_correction_and_purchase(self):
        cid = self.turn('I want Growth. How do I pay?').json['conversation_id']
        self.assertEqual(self.lead(cid)['purchase_requested'], 1)
        self.assertNotEqual(self.lead(cid)['sales_status'], 'READY_TO_BOOK')
        self.turn('Actually Signature instead', cid)
        self.assertIn('signature', self.lead(cid)['package_id'])
        self.assertEqual(self.lead(cid)['purchase_requested'], 0)

    def test_migration_preserves_legacy_rows(self):
        with tempfile.TemporaryDirectory(dir=Path(self.db_path).parent) as directory:
            path = Path(directory) / 'legacy.db'
            init_db(path)
            with connect(path) as db:
                db.execute("INSERT INTO conversations VALUES ('legacy','before','before')")
                db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES ('legacy','user','Keep me','before')")
                db.execute("INSERT INTO leads(conversation_id,name,status,created_at,updated_at) VALUES ('legacy','Jordan','Booked','before','before')")
            migrate(path)
            migrate(path)
            with connect(path) as db:
                lead = dict(db.execute('SELECT * FROM leads').fetchone())
                self.assertEqual((lead['name'], lead['status'], lead['sales_status'], lead['legacy_review_required']), ('Jordan','Booked','NEW',1))
                self.assertEqual(db.execute('SELECT content FROM messages').fetchone()[0], 'Keep me')
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
