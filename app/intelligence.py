"""Evidence-grounded field updates and early sales decisions, never execution."""
import calendar
import json
import re
from datetime import date
from .sales import match_catalog, conversation_catalog, selected_blocks, sales_answer

EARLY_STATES = ('NEW','DISCOVERY','QUALIFIED','QUOTE_NEEDED','READY_TO_BOOK')
CORRECTION = re.compile(r'\b(actually|instead|correction|change|make it|switch|no longer|only need|use|update)\b', re.I)


def offers(knowledge):
    return {key+':'+re.sub(r'[^a-z0-9]+','-',heading.lower()).strip('-'):(key,heading)
            for key,entry in knowledge['catalog'].items() for heading in entry['price_blocks']}


def valid_date(value):
    if '(needs clarification)' in value or value=='Not decided yet': return True
    if re.search(r'\b(next|this|later)\b',value,re.I): return bool(re.fullmatch(r'[A-Za-z ]{3,60}',value))
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value): date.fromisoformat(value); return True
        if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',value):
            month,day,year=map(int,value.split('/'));date(year,month,day);return True
        m=re.fullmatch(r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?',value)
        if m:
            month=next((i for i in range(1,13) if m[1].lower() in (calendar.month_name[i].lower(),calendar.month_abbr[i].lower())),None)
            if month: date(int(m[3] or 2000),month,int(m[2]));return True
    except ValueError: pass
    return False


def valid_field(field,value):
    if not isinstance(value,str) or not value.strip(): return False
    if field=='email': return len(value)<=254 and bool(re.fullmatch(r'[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+',value))
    if field=='phone': return bool(re.fullmatch(r'\+?[\d ().-]+',value)) and 8<=len(re.sub(r'\D','',value))<=15 and not re.fullmatch(r'\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}',value)
    if field=='project_date': return valid_date(value)
    if field=='budget': return len(value)<=100 and bool(re.search(r'\d',value))
    if field=='name': return len(value)<=120 and value.lower() not in ('ready','interested','ready to book','looking','paid','not ready') and not re.search(r'\b(book|pay|need|want)\b',value,re.I)
    return len(value)<= (1000 if field=='description' else 200)


def selection(history,lead,knowledge):
    last=history[-1]['content']
    keys=match_catalog(last,knowledge)
    current=lead.get('service_id')
    if keys:
        current=keys[0] if len(keys)==1 else None
    elif not current:
        all_keys=conversation_catalog(history,knowledge)
        if len(all_keys)==1: current=all_keys[0]
    package=lead.get('package_id') if current==lead.get('service_id') else None
    candidates=offers(knowledge)
    if current:
        blocks=knowledge['catalog'][current]['price_blocks']
        for identifier,(key,heading) in candidates.items():
            if key!=current:continue
            aliases=[heading.lower()]
            if current=='monthly':aliases.append(heading.lower().split()[0])
            if current in ('website','bot','music_video'):aliases.append(heading.lower().split()[0])
            if any(re.search(r'\b'+re.escape(a)+r'\b',last,re.I) for a in aliases):package=identifier;break
        ordinal=re.search(r'\b(first|second|third) (?:one|package|option|plan)\b',last,re.I)
        if ordinal:
            previous=next((h['content'] for h in reversed(history[:-1]) if h['role']=='assistant'),'')
            displayed=[(identifier,heading) for identifier,(key,heading) in candidates.items() if key==current and heading.lower() in previous.lower()]
            displayed.sort(key=lambda item:previous.lower().index(item[1].lower()))
            index=('first','second','third').index(ordinal[1].lower())
            if len(displayed)>index:package=displayed[index][0]
        if len(blocks)==1:package=next((p for p,(k,_) in candidates.items() if k==current),None)
    return current,package


def deterministic_updates(history,lead,knowledge):
    from .assistant import extract_from_history
    # Incremental extraction prevents old transcript values overriding a corrected field.
    latest=history[-1]
    prior=next((h for h in reversed(history[:-1]) if h['role']=='assistant'),None)
    local=([prior] if prior else [])+[latest]
    raw=extract_from_history(local,knowledge)
    text=latest['content']
    # A free-text answer to creative direction is evidence even without style keywords.
    from .conversation import questions, intents
    if prior and any('description' in intents(q) for q in questions(prior['content'])):
        if '?' not in text and not re.match(r'^(?:how much|price|cost|my name|my email|call me)\b', text, re.I):
            raw['description']=text[:1000]
    for field,pattern in {
        'name':r'(?:name is|name to|call me)\s+([^,.!?;]+)',
        'location':r'(?:location (?:is|to) |(?:shoot|film|event) (?:is )?in )([A-Za-z][A-Za-z .,-]{1,70})',
        'budget':r'budget\s*(?:is|to|of|around|about|:)?\s*(\$?\d[\d,]*(?:\.\d{1,2})?(?:\s*[kK])?(?:\s*[-–]\s*\$?\d[\d,]*)?)',
        'description':r'(?:description|concept|vision)\s*(?:is|to|:)?\s+(.+)',
    }.items():
        match=re.search(pattern,text,re.I)
        if match and (field!='location' or not re.match(r'(?:October|November|December|January|February|March|April|May|June|July|August|September|\d)',match[1],re.I)):
            raw[field]=re.split(r'\b(?:on|and|budget|next)\b',match[1],maxsplit=1,flags=re.I)[0].strip(' .,') if field=='location' else match[1].strip(' .,')
    iso=re.search(r'\b\d{4}-\d{2}-\d{2}\b',text)
    if iso: raw['project_date']=iso[0]
    updates={k:v for k,v in raw.items() if k!='service' and valid_field(k,v)}
    # Preserve the established cumulative brief for expanded digital/network inquiries.
    expanded={'monthly','single','wedding','sweet16','real_estate','website','management','bot','bot_maintenance','unpriced','international','music_network','talent'}
    if expanded.intersection(conversation_catalog(history,knowledge)) and not (CORRECTION.search(text) and 'description' in updates):
        previous=lead.get('description') or ''
        updates['description']='\n'.join(dict.fromkeys([s for s in [previous,text] if s]))[-8000:]
    service,package=selection(history,lead,knowledge)
    updates.update(service_id=service,package_id=package)
    if service: updates['service']=knowledge['catalog'][service]['service']
    elif raw.get('service'):updates['service']=raw['service']
    return updates


def evidence_updates(result,history,lead,knowledge):
    if not result or result['confidence']<0.75:return {},{}
    latest=history[-1]
    accepted={};evidence={}
    expected_service,expected_package=selection(history,lead,knowledge)
    for update in result['proposed_updates']:
        field,value,quote=update['field'],update['value'].strip(),update['quote']
        if update['message_id']!=latest['id'] or quote not in latest['content']:continue
        if field=='service_id':
            if value!=expected_service:continue
        elif field=='package_id':
            if value!=expected_package or value not in offers(knowledge):continue
        elif value.casefold() not in quote.casefold() or not valid_field(field,value):continue
        accepted[field]=value
        evidence[field]={'message_id':latest['id'],'quote':quote,'source':'model_validated'}
    if 'service_id' in accepted:accepted['service']=knowledge['catalog'][accepted['service_id']]['service']
    return accepted,evidence


def classify(history,lead,knowledge):
    text=history[-1]['content'];lower=text.lower().replace('’',"'")
    negative=bool(re.search(r"\b(?:don't|do not|not ready|cancel|no longer|not interested|if i|if we)\b",lower))
    context=bool(lead.get('service_id'))
    purchase=not negative and bool(re.search(r"\b(book me|want to book|ready to book|i'm ready|i am ready|let's (?:do it|start)|let us start|i'll take|i will take|i want (?:growth|essential|signature))\b",lower)) and context
    if re.search(r'\b(?:speak|talk) (?:to|with) (?:someone|a person|a human)|\b(?:ivan|someone) call me|\bhuman\b',lower): return 'HUMAN_REQUEST',False
    if re.search(r'\b(?:paid|pay|payment|checkout|apple pay|google pay)\b',lower): return 'PAYMENT_REQUEST',purchase
    if re.search(r'\bdeposit\b',lower):return 'DEPOSIT_REQUEST',purchase
    if re.search(r'\bcontract|agreement|signed\b',lower):return 'CONTRACT_REQUEST',purchase
    if re.search(r'\bbook(?:ing)?\b',lower) and not negative:return 'BOOKING_REQUEST',purchase
    if re.search(r'how much|\bprice|\bpricing|\bcost',lower):return 'PRICING_QUESTION',False
    if re.search(r'custom quote|custom programming|outside|twenty reels',lower) or lead.get('service_id') in {'international','unpriced','management','bot_maintenance','talent','music_network'}:return 'QUOTE_NEEDED',purchase
    if purchase:return 'READY_TO_BOOK',True
    if lead.get('package_id') and match_catalog(text,knowledge):return 'PACKAGE_INTEREST',False
    if context:return 'SERVICE_DISCOVERY',False
    return 'GENERAL_QUESTION',False


def decision(history,lead,knowledge,result=None):
    intent,purchase=classify(history,lead,knowledge)
    # A model can add semantic intent only with current-turn evidence. Consequential
    # purchase detection always remains the explicit, context-aware application gate.
    if result and result['confidence']>=0.75 and intent=='GENERAL_QUESTION':
        evidence=any(e['message_id']==history[-1]['id'] and e['quote'] in history[-1]['content'] for e in result['evidence'])
        if evidence and result['intent'] in ('GENERAL_QUESTION','SERVICE_DISCOVERY','PRICING_QUESTION','PACKAGE_INTEREST','QUOTE_NEEDED'):
            intent=result['intent']
    missing=[]
    service=lead.get('service_id');package=lead.get('package_id')
    if not service:missing.append('service_id')
    if service and len(knowledge['catalog'][service]['price_blocks'])>1 and not package:missing.append('package_id')
    if not lead.get('name'):missing.append('name')
    if not (lead.get('email') or lead.get('phone')):missing.append('email')
    if not lead.get('project_date') or lead['project_date']=='Not decided yet' or 'clarification' in lead['project_date']:missing.append('project_date')
    if service not in ('website','bot','management','bot_maintenance') and not lead.get('location'):missing.append('location')
    qualified=not missing
    old=lead.get('sales_status','NEW')
    requested=bool(lead.get('purchase_requested')) or purchase
    if re.search(r"don't want|do not want|not ready|cancel|no longer",history[-1]['content'],re.I):requested=False
    custom=intent=='QUOTE_NEEDED' or (service and not knowledge['catalog'][service]['price_blocks']) or len(match_catalog(history[-1]['content'],knowledge))>1
    state='QUOTE_NEEDED' if custom else ('READY_TO_BOOK' if qualified and requested else ('QUALIFIED' if qualified else 'DISCOVERY'))
    if intent=='HUMAN_REQUEST':state=old if old!='NEW' else 'DISCOVERY'
    action='PREPARE_QUOTE' if custom else ('ASK_FOR_CONTACT' if 'email' in missing else ('ASK_FOR_DATE' if 'project_date' in missing else 'REVIEW_INQUIRY'))
    if intent=='HUMAN_REQUEST':action='HUMAN_FOLLOW_UP'
    elif intent=='CONTRACT_REQUEST':action='PREPARE_CONTRACT'
    elif intent=='DEPOSIT_REQUEST':action='REQUEST_DEPOSIT'
    elif intent=='PAYMENT_REQUEST':action='REVIEW_INQUIRY' if re.search(r'\bpaid\b',history[-1]['content'],re.I) else action
    elif intent=='BOOKING_REQUEST' or state=='READY_TO_BOOK':action='VERIFY_AVAILABILITY'
    confidence=result['confidence'] if result and intent==result['intent'] else 1.0
    summary='; '.join(str(lead[k])[:180] for k in ('name','service','package_id','project_date','location','budget') if lead.get(k))
    summary=(summary+'; Customer request: '+history[-1]['content'][:200])[:800] if summary else ''
    return {'sales_status':state,'sales_intent':intent,'intent_confidence':confidence,'next_action':action,'purchase_requested':int(requested),'missing_fields':json.dumps(missing),'conversation_summary':summary}


def safe_special_reply(history,lead,decision):
    text=history[-1]['content'];intent=decision['sales_intent']
    if intent=='HUMAN_REQUEST':return 'I’ve noted your request to speak with the Masterment team. '+('They can use the contact information you shared to follow up.' if lead.get('email') or lead.get('phone') else 'What’s the best phone number or email for them to reach you?')
    if re.search(r'\bavailability|\bavailable\b',text,re.I) or intent=='BOOKING_REQUEST':return 'I can note '+(lead.get('project_date') or 'your preferred date')+' for the team to review. Masterment still needs to confirm availability; your booking is not confirmed.'
    if intent=='CONTRACT_REQUEST':return 'I’ve noted your agreement request for the team to review. I can’t send or verify a signed contract here yet.'
    if intent in ('PAYMENT_REQUEST','DEPOSIT_REQUEST'):
        if re.search(r'\bpaid\b',text,re.I):return 'I’ve noted that you reported a payment for the team to review. I can’t verify payment here, and this does not confirm a booking.'
        if re.search(r'apple pay|google pay|card',text,re.I):return 'An approved secure checkout would display the payment methods available for your device and account. Checkout is not connected here yet; please don’t share card or bank details in chat.'
        return 'I’ve noted that you’d like to move forward. The Masterment team needs to review the project and approved payment terms; I can’t create a payment link or confirm a booking here yet.'
    if intent=='READY_TO_BOOK':return 'I’ve noted that you’d like to move forward with '+(lead.get('service') or 'the project')+'. The team still needs to confirm the details and availability.'
    if re.search(r"let['’]s do it|let['’]s start|i['’]ll take that one",text,re.I) and not lead.get('service_id'):return 'Which service or package would you like to move forward with?'
    return None
