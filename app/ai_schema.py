"""Strict model proposal format. It intentionally has no financial/booking writes."""
import math

INTENTS = ('GENERAL_QUESTION','SERVICE_DISCOVERY','PRICING_QUESTION','PACKAGE_INTEREST','QUALIFIED','QUOTE_NEEDED','READY_TO_BOOK','BOOKING_REQUEST','CONTRACT_REQUEST','DEPOSIT_REQUEST','PAYMENT_REQUEST','HUMAN_REQUEST')
ACTIONS = ('REVIEW_INQUIRY','ASK_FOR_DATE','ASK_FOR_CONTACT','PREPARE_QUOTE','VERIFY_AVAILABILITY','CONTACT_CUSTOMER','PREPARE_CONTRACT','REQUEST_DEPOSIT','HUMAN_FOLLOW_UP')
FIELDS = ('name','email','phone','service_id','package_id','budget','project_date','location','description')


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


EVIDENCE = obj({'message_id':{'type':'integer'},'quote':{'type':'string'}})
SCHEMA = obj({
    'intent':{'type':'string','enum':list(INTENTS)},
    'confidence':{'type':'number'},
    'proposed_updates':{'type':'array','items':obj({'field':{'type':'string','enum':list(FIELDS)},'value':{'type':'string'},'message_id':{'type':'integer'},'quote':{'type':'string'}})},
    'evidence':{'type':'array','items':EVIDENCE},
    'summary':{'type':'string'},
    'recommended_next_action':{'type':'string','enum':list(ACTIONS)},
    'missing_fields':{'type':'array','items':{'type':'string','enum':list(FIELDS)}},
    'reply':{'type':'string'},
})


def validate(value):
    if not isinstance(value,dict) or set(value)!=set(SCHEMA['properties']):
        raise ValueError('schema_keys')
    if value['intent'] not in INTENTS or value['recommended_next_action'] not in ACTIONS:
        raise ValueError('invalid_enum')
    confidence=value['confidence']
    if type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1:
        raise ValueError('invalid_confidence')
    for key,limit in (('summary',800),('reply',3000)):
        if not isinstance(value[key],str) or len(value[key])>limit:
            raise ValueError('invalid_text')
    if not isinstance(value['missing_fields'],list) or len(value['missing_fields'])>len(FIELDS) or any(x not in FIELDS for x in value['missing_fields']):
        raise ValueError('invalid_missing_fields')
    for key,allowed,limit in [('evidence',{'message_id','quote'},12),('proposed_updates',{'field','value','message_id','quote'},len(FIELDS))]:
        if not isinstance(value[key],list) or len(value[key])>limit:
            raise ValueError('invalid_list')
        seen=set()
        for item in value[key]:
            if not isinstance(item,dict) or set(item)!=allowed or type(item['message_id']) is not int:
                raise ValueError('invalid_evidence')
            if not isinstance(item['quote'],str) or not 1<=len(item['quote'])<=4000:
                raise ValueError('invalid_quote')
            if key=='proposed_updates':
                if item['field'] not in FIELDS or item['field'] in seen or not isinstance(item['value'],str) or not 1<=len(item['value'])<=1000:
                    raise ValueError('invalid_update')
                seen.add(item['field'])
    return value
