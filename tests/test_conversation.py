import os
import unittest
from unittest.mock import patch
import test_app
from app.assistant import render_reply, read_knowledge
from app.conversation import repeated_or_known
from pathlib import Path

class ConversationRegression(unittest.TestCase):
    setUp = test_app.AppTest.setUp
    tearDown = test_app.AppTest.tearDown

    def turn(self, message, cid=None, request_id=None):
        data={'message':message}
        if cid:data['conversation_id']=cid
        if request_id:data['request_id']=request_id
        response=self.client.post('/api/chat',json=data)
        self.assertEqual(response.status_code,200)
        self.assertLessEqual(response.json['reply'].count('?'),1)
        return response.json

    def test_progression_and_known_fields(self):
        first=self.turn('I need a music video')
        second=self.turn('Dark cinematic R&B', first['conversation_id'])
        self.assertIn('date',second['reply'])
        third=self.turn('October 20',first['conversation_id'])
        self.assertIn('Where',third['reply'])
        fourth=self.turn('Boston',first['conversation_id'])
        self.assertNotIn('Where',fourth['reply'])
        self.assertEqual(fourth['captured']['location'],'Boston')
        known=self.turn('I want a cinematic R&B music video in Boston')
        self.assertIn('date',known['reply'])

    def test_identical_and_semantic_repeat(self):
        history=[{'role':'assistant','content':'What kind of look are you going for?'},
                 {'role':'user','content':'Not sure'}]
        for text in ('What kind of look are you going for?',
                     'What kind of visual style do you have in mind?',
                     'What kind of look, feel, or story do you have in mind?'):
            self.assertTrue(repeated_or_known(text,history,{}))

    def test_free_text_answer_is_captured(self):
        first=self.turn('I need a music video')
        second=self.turn('A lonely astronaut walking through abandoned streets',first['conversation_id'])
        self.assertIn('astronaut',second['captured']['description'])
        self.assertIn('date',second['reply'])

    def test_replay_and_history_have_one_reply(self):
        import uuid
        rid=str(uuid.uuid4())
        first=self.turn('I need a music video',request_id=rid)
        replay=self.turn('I need a music video',first['conversation_id'],rid)
        self.assertEqual(first,replay)
        for _ in range(2):
            history=self.client.get('/api/conversations/'+first['conversation_id']).json['messages']
            self.assertEqual([m['role'] for m in history],['user','assistant'])
            self.assertEqual(history[-1]['id'],first['assistant_message_id'])

    def test_model_is_only_authority_and_failure_falls_back(self):
        with patch('app.workflow.model_understanding',return_value={'reply':'Do you have a date in mind?', 'confidence':1.,'intent':'SERVICE_DISCOVERY','proposed_updates':[], 'evidence':[]}):
            first=self.turn('I want a cinematic music video in Boston')
        self.assertEqual(first['reply'],'Do you have a date in mind?')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}), patch('app.workflow.model_understanding',return_value=None):
            failed=self.turn('I need a music video')
        self.assertIn('look',failed['reply'])

    def test_model_repeat_and_multiple_questions_rejected(self):
        knowledge=read_knowledge(Path(__file__).resolve().parents[1]/'knowledge/business.json')
        history=[{'role':'assistant','content':'What kind of look are you going for?'},
                 {'role':'user','content':'Dark cinematic R&B'}]
        for reply in ('What visual style do you have in mind?', 'What date? Where will it be?',
                      'What date and location do you have in mind?'):
            result={'reply':reply,'confidence':1.,'intent':'SERVICE_DISCOVERY','proposed_updates':[], 'evidence':[]}
            final=render_reply(history,{'service':'Music video production','description':'Dark cinematic R&B'},knowledge,result)
            self.assertIn('date',final)
            self.assertEqual(final.count('?'),1)

    def test_pricing_one_followup(self):
        first=self.turn('How much is a music video?')
        self.assertIn('$',first['reply'])
        self.assertEqual(first['reply'].count('?'),1)
        history=self.client.get('/api/conversations/'+first['conversation_id']).json['messages']
        self.assertEqual(len(history),2)
