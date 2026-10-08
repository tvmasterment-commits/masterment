"""Question intent checks shared by model validation and deterministic progression."""
import re

PATTERNS = {
    'description': r"\b(look|feel|story|style|visual direction|creative direction|vibe|concept|vision)\b",
    'project_date': r"\b(date|timeframe|when|schedule|day)\b",
    'location': r"\b(where|location|city|venue)\b",
    'budget': r"\b(budget|spend|afford)\b",
    'service': r"\b(type of project|kind of project|which service|what service)\b",
    'contact': r"\b(phone|email|reach you|contact method)\b",
    'name': r"\b(name|who am i speaking)\b",
}

def questions(text):
    # Include polite requests without a question mark as well as interrogatives.
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text)
            if '?' in s or re.match(r'(please|could you|can you|tell me|share|provide)\b', s, re.I)]

def intents(text):
    from .language import intake_text
    text = intake_text(text)
    return {field for field, pattern in PATTERNS.items() if re.search(pattern, text, re.I)}

def repeated_or_known(reply, history, lead):
    proposed = questions(reply)
    if len(proposed)>1 or reply.count('?')>1:
        return True
    for question in proposed:
        fields = intents(question)
        # Asking two independent facts in a single sentence is still two questions.
        if len(fields)>1:
            return True
        for field in fields:
            known = (lead.get('phone') or lead.get('email')) if field=='contact' else lead.get(field)
            if known and not (field=='project_date' and 'needs clarification' in str(known)):
                return True
        normalized = re.sub(r'[^a-z0-9]+', ' ', question.lower()).strip()
        for turn in history:
            if turn.get('role')!='assistant': continue
            for previous in questions(turn['content']):
                if fields and fields.intersection(intents(previous)):
                    return True
                if normalized == re.sub(r'[^a-z0-9]+', ' ', previous.lower()).strip():
                    return True
    return False
