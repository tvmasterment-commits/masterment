import sqlite3
import unittest
import uuid
from unittest.mock import patch

import test_app
from app.db import connect


class ChatReliability(unittest.TestCase):
    setUp = test_app.AppTest.setUp
    tearDown = test_app.AppTest.tearDown

    def test_history_database_failure_returns_safe_retryable_json(self):
        with patch('app.routes.connect', side_effect=sqlite3.OperationalError('private connection details')):
            with self.assertLogs(self.app.logger, level='ERROR') as logs:
                response = self.client.get('/api/conversations/' + str(uuid.uuid4()))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('temporarily unavailable', response.json['error'])
        self.assertIn('chat_history_failure category=OperationalError backend=sqlite', logs.output[0])
        self.assertNotIn('private connection details', str(logs.output) + response.text)

    def test_storage_failure_does_not_claim_success_and_retry_saves_once(self):
        payload = {'message': "I'm looking for photography.", 'request_id': str(uuid.uuid4())}
        with patch('app.workflow.connect', side_effect=sqlite3.OperationalError('private details')):
            with self.assertLogs(self.app.logger, level='ERROR') as logs:
                failed = self.client.post('/api/chat', json=payload)
        self.assertEqual(failed.status_code, 503)
        self.assertNotIn('private details', str(logs.output) + failed.text)
        first = self.client.post('/api/chat', json=payload)
        replay = self.client.post('/api/chat', json=payload)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json, replay.json)
        with connect(self.db_path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM messages').fetchone()['n'], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM leads').fetchone()['n'], 1)

    def test_provider_failure_falls_back_and_captures_photography_lead(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only-not-a-real-key'}):
            with patch('app.assistant.OpenAI', side_effect=TimeoutError('private provider details')):
                first = self.client.post('/api/chat', json={'message': "I'm looking for photography."})
                self.assertEqual(first.status_code, 200)
                second = self.client.post('/api/chat', json={
                    'conversation_id': first.json['conversation_id'],
                    'message': 'My name is Jordan. jordan@example.com. Portraits in Boston on October 20.'})
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json['reply'])
        self.assertEqual(second.json['captured']['email'], 'jordan@example.com')
        with connect(self.db_path) as db:
            lead = db.execute('SELECT * FROM leads WHERE conversation_id=?',
                              (first.json['conversation_id'],)).fetchone()
            self.assertEqual(lead['email'], 'jordan@example.com')
            self.assertIn('Photography', lead['service'])
        history = self.client.get('/api/conversations/' + first.json['conversation_id'])
        self.assertEqual(len(history.json['messages']), 4)
        self.assertNotIn('private provider details', history.text)
