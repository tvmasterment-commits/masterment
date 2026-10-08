import json
import re
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import test_app
from app.assistant import model_understanding, read_knowledge
from app.db import connect
from app.portfolio import read_portfolio
from app.migrations import validate_schema


class MastermentImplementation(unittest.TestCase):
    setUp = test_app.AppTest.setUp
    tearDown = test_app.AppTest.tearDown

    def test_responses_incomplete_refusal_and_empty_output_use_fallback(self):
        knowledge = read_knowledge(self.app.config['KNOWLEDGE_PATH'])
        history = [{'id': 1, 'role': 'user', 'content': 'I need photography.'}]
        from ai_fixtures import understanding
        valid = json.dumps(understanding('What location do you have in mind?'))
        cases = [
            SimpleNamespace(status='incomplete', output=[], output_text=valid),
            SimpleNamespace(status='completed', output=[SimpleNamespace(content=[SimpleNamespace(type='refusal')])], output_text=valid),
            SimpleNamespace(status='completed', output=[], output_text=''),
        ]
        for response in cases:
            with self.subTest(status=response.status), patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'}), patch('app.assistant.OpenAI') as provider:
                provider.return_value.responses.create.return_value = response
                with self.assertLogs('app.assistant', level='WARNING'):
                    self.assertIsNone(model_understanding(history, {}, knowledge))

    def turn(self, message, cid=None):
        response = self.client.post('/api/chat', json={'message': message, 'conversation_id': cid})
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_short_style_and_location_answers_persist_without_repeated_question(self):
        first = self.turn('I want a music video.')
        dark = self.turn('Dark.', first['conversation_id'])
        self.assertIn('Dark', dark['captured']['description'])
        self.assertNotIn('look, feel', dark['reply'])
        date = self.turn('October 20', first['conversation_id'])
        boston = self.turn('Boston', first['conversation_id'])
        self.assertEqual(boston['captured']['location'], 'Boston')
        self.assertIn('Dark', boston['captured']['description'])
        self.assertNotIn('Where', boston['reply'])
        self.assertNotIn('look, feel', boston['reply'])

    def test_portuguese_intake_and_context(self):
        first = self.turn('Quero um vídeo musical.')
        self.assertIn('estilo', first['reply'])
        second = self.turn('Escuro.', first['conversation_id'])
        self.assertEqual(second['captured']['description'], 'Escuro.')
        self.assertIn('data', second['reply'])
        third = self.turn('20 de outubro de 2026', first['conversation_id'])
        self.assertEqual(third['captured']['project_date'], 'October 20, 2026')
        fourth = self.turn('Boston', first['conversation_id'])
        self.assertEqual(fourth['captured']['location'], 'Boston')
        final = self.turn('Meu nome é Jordan. jordan@example.com', first['conversation_id'])
        self.assertEqual(final['captured']['name'], 'Jordan')
        self.assertEqual(final['captured']['email'], 'jordan@example.com')
        creole = self.turn('Can we speak Kriolu?')
        self.assertIn('English or Portuguese', creole['reply'])
        self.assertNotIn('fluent', creole['reply'])

    def test_curated_portfolio_exact_urls_and_no_unverified_alias(self):
        data = read_portfolio()
        self.assertEqual(len(data['projects']), 18)
        self.assertEqual(len(set(p['url'] for p in data['projects'])), 18)
        for project in data['projects']:
            for name in project['names_in_published_title']:
                self.assertIn(name.casefold(), project['title'].casefold())
        first = self.turn('I need a music video.')
        response = self.turn('Show me examples from your portfolio.', first['conversation_id'])
        self.assertIn('https://www.youtube.com/watch?v=', response['reply'])
        self.assertIn('official channel', response['reply'])
        for url in re.findall(r'https://\S+', response['reply']):
            self.assertIn(url, [p['url'] for p in data['projects']])
        unknown = self.turn('Did you make Match with Alexandra Leite?')
        self.assertIn('do not have a verified source', unknown['reply'])
        self.assertNotIn('Yes', unknown['reply'])
        wedding = self.turn('Show me wedding portfolio examples.')
        self.assertIn('do not yet have a verified example', wedding['reply'])
        self.assertIn('https://masterment.services/#work', wedding['reply'])
        contact = self.turn('My name is Jordan. jordan@example.com. Portrait photography in Boston on October 20.')
        self.assertNotIn('youtube.com', contact['reply'])

    def test_abandoned_pending_turn_recovers_once_without_ai_or_duplicate_lead(self):
        rid = str(uuid.uuid4())
        payload = {'message': "I'm looking for photography.", 'request_id': rid}
        with patch('app.workflow.model_understanding', side_effect=RuntimeError('synthetic worker interruption')):
            with self.assertLogs(self.app.logger, level='ERROR'):
                self.assertEqual(self.client.post('/api/chat', json=payload).status_code, 503)
        self.assertEqual(self.client.post('/api/chat', json=payload).status_code, 202)
        with connect(self.db_path) as db:
            stamp = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat()
            db.execute('UPDATE chat_requests SET created_at=? WHERE request_id=?', (stamp, rid))
        with patch('app.workflow.model_understanding') as ai:
            recovered = self.client.post('/api/chat', json=payload)
            replay = self.client.post('/api/chat', json=payload)
            ai.assert_not_called()
        self.assertEqual(recovered.status_code, 200)
        self.assertEqual(recovered.json, replay.json)
        with connect(self.db_path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM messages').fetchone()['n'], 2)
            self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM leads').fetchone()['n'], 1)

    def test_schema_validation_checks_all_chat_columns(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute('ALTER TABLE leads DROP COLUMN next_action')
        with self.assertRaises(RuntimeError):
            validate_schema(self.db_path)

    def test_model_prompt_has_language_and_curated_knowledge_without_api_storage(self):
        knowledge = read_knowledge(Path(__file__).resolve().parents[1] / 'knowledge/business.json')
        history = [{'id': 1, 'role': 'user', 'content': 'Quero um vídeo musical.'}]
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'}), patch('app.assistant.OpenAI') as provider:
            provider.return_value.responses.create.side_effect = TimeoutError('test')
            with self.assertLogs('app.assistant', level='WARNING'):
                self.assertIsNone(model_understanding(history, {}, knowledge))
            kwargs = provider.return_value.responses.create.call_args.kwargs
        self.assertFalse(kwargs['store'])
        self.assertTrue(kwargs['text']['format']['strict'])
        self.assertEqual(kwargs['text']['format']['type'], 'json_schema')
        self.assertLessEqual(kwargs['max_output_tokens'], 1600)
        self.assertIn('English or Portuguese', kwargs['input'][0]['content'])
        self.assertIn('verified_portfolio_examples', kwargs['input'][0]['content'])
        self.assertIn('Massachusetts and Rhode Island', kwargs['input'][0]['content'])
        self.assertNotIn('test-only', json.dumps(kwargs['input']))
