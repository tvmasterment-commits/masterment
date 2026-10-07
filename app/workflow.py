"""Short transactional chat turns, ownership, durable replay, revision checks."""
import hashlib
import json
import logging
import uuid
from flask import current_app
from .db import connect, ensure_conversation, add_message, upsert_lead, now
from .assistant import read_knowledge, model_understanding, render_reply
from .intelligence import deterministic_updates, evidence_updates, decision

log=logging.getLogger(__name__)
LEAD_FIELDS=('name','phone','email','service','project_date','location','budget','description')


class ChatError(Exception):
    def __init__(self,message,status=400):self.message=message;self.status=status


def owned(db,conversation_id,owner):
    row=db.execute('SELECT * FROM conversations WHERE id=? AND owner_hash=?',(conversation_id,owner)).fetchone()
    if not row:raise ChatError('Conversation unavailable. Please start a new conversation.',404)
    return row


def save_intelligence(db,cid,revision,lead,updates,derived,evidence):
    previous=lead.get('sales_status','NEW')
    upsert_lead(db,cid,updates)
    fields={**derived,'service_id':updates.get('service_id',lead.get('service_id')),
            'package_id':updates.get('package_id',lead.get('package_id')),'field_evidence':json.dumps(evidence), 'updated_at':now()}
    db.execute('UPDATE leads SET '+','.join(k+'=?' for k in fields)+' WHERE conversation_id=?',(*fields.values(),cid))
    if previous!=derived['sales_status']:
        db.execute('INSERT OR IGNORE INTO sales_transitions(conversation_id,revision,from_state,to_state,intent,created_at) VALUES (?,?,?,?,?,?)',
                   (cid,revision,previous,derived['sales_status'],derived['sales_intent'],now()))
        log.info('sales_transition revision=%s from=%s to=%s',revision,previous,derived['sales_status'])


def chat_turn(message,cid,request_id,owner):
    path=current_app.config['DATABASE_PATH']
    knowledge=read_knowledge(current_app.config['KNOWLEDGE_PATH'])
    input_hash=hashlib.sha256(message.encode()).hexdigest()
    # Legacy clients without request IDs get content-based replay; current clients
    # always send a fresh UUID per deliberate message and retain it across retries.
    request_id=request_id or str(uuid.uuid5(uuid.NAMESPACE_URL,owner+':'+str(cid)+':'+message))
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT * FROM chat_requests WHERE request_id=?',(request_id,)).fetchone()
        if existing:
            if existing['owner_hash']!=owner or existing['input_hash']!=input_hash or (cid and cid!=existing['conversation_id']):
                raise ChatError('Request identity conflict.',409)
            if existing['response_json']:return json.loads(existing['response_json']),200
            # A completed newer revision supersedes this pending turn. A retry never
            # invokes the model twice or appends another message.
            return {'conversation_id':existing['conversation_id'],'request_id':request_id,'pending':True},202
        if cid:
            conversation=owned(db,cid,owner)
        else:
            cid=str(uuid.uuid4())
            ensure_conversation(db,cid)
            db.execute('UPDATE conversations SET owner_hash=? WHERE id=?',(owner,cid))
            conversation=owned(db,cid,owner)
        revision=conversation['revision']+1
        db.execute('UPDATE conversations SET revision=? WHERE id=?',(revision,cid))
        add_message(db,cid,'user',message)
        message_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
        history=[dict(row) for row in db.execute('SELECT id,role,content FROM messages WHERE conversation_id=? ORDER BY id DESC',(cid,))][::-1]
        row=db.execute('SELECT * FROM leads WHERE conversation_id=?',(cid,)).fetchone()
        lead=dict(row) if row else {}
        updates=deterministic_updates(history,lead,knowledge)
        # A changed selection invalidates prior acceptance; never carry a purchase
        # request across a different project/package without new customer intent.
        if any(updates.get(k)!=lead.get(k) for k in ('service_id','package_id')):lead['purchase_requested']=0
        evidence=json.loads(lead.get('field_evidence') or '{}')
        for field,value in updates.items():
            if value is not None and value!=lead.get(field):evidence[field]={'message_id':message_id,'source':'deterministic'}
        merged={**lead,**updates}
        derived=decision(history,merged,knowledge)
        save_intelligence(db,cid,revision,lead,updates,derived,evidence)
        db.execute('INSERT INTO chat_requests(request_id,conversation_id,owner_hash,input_hash,revision,user_message_id,created_at) VALUES (?,?,?,?,?,?,?)',
                   (request_id,cid,owner,input_hash,revision,message_id,now()))
        lead={**merged,**derived}
    # No SQLite connection/transaction remains open during this external call.
    result=model_understanding(history,lead,knowledge)
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        conversation=owned(db,cid,owner)
        if conversation['revision']!=revision:
            response={'conversation_id':cid,'request_id':request_id,'revision':revision,'stale':True,
                      'reply':'I’ve saved your message. Your newer details take priority.'}
            db.execute("UPDATE chat_requests SET state='stale',response_json=? WHERE request_id=?",(json.dumps(response),request_id))
            log.info('ai_result_stale revision=%s',revision)
            return response,200
        updates,model_evidence=evidence_updates(result,history,lead,knowledge)
        evidence.update(model_evidence)
        merged={**lead,**updates}
        derived=decision(history,merged,knowledge,result)
        save_intelligence(db,cid,revision,lead,updates,derived,evidence)
        reply=render_reply(history,{**merged,**derived},knowledge,result)
        add_message(db,cid,'assistant',reply)
        assistant_message_id=db.execute('SELECT last_insert_rowid()').fetchone()[0]
        saved=db.execute('SELECT * FROM leads WHERE conversation_id=?',(cid,)).fetchone()
        response={'conversation_id':cid,'request_id':request_id,'revision':revision,'reply':reply,'assistant_message_id':assistant_message_id,
                  'captured':{field:saved[field] for field in LEAD_FIELDS if saved[field]},'status':saved['status']}
        db.execute("UPDATE chat_requests SET state='completed',response_json=? WHERE request_id=?",(json.dumps(response),request_id))
        log.info('chat_turn_saved revision=%s',revision)
    return response,200
