"""Valid structured fixtures for existing conversational regression tests."""
import json


def understanding(reply, kwargs=None):
    messages=(kwargs or {}).get('input',[])
    last=next((m for m in reversed(messages) if m['role']=='user'),None)
    evidence=[]
    if last:
        value=json.loads(last['content'])
        evidence=[{'message_id':value['message_id'],'quote':value['text']}]
    return {'intent':'GENERAL_QUESTION','confidence':0.9,'proposed_updates':[],
            'evidence':evidence,'summary':'','recommended_next_action':'REVIEW_INQUIRY',
            'missing_fields':[],'reply':reply}
