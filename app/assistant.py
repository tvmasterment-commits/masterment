import json
import os
import re
from openai import OpenAI

FIELDS = ("name", "phone", "email", "service", "project_date", "location", "budget", "description")

SERVICE_HINTS = (
    (("music video", "music-video"), "Music video production"),
    (("commercial production", "commercial video", "commercial shoot", "commercial", "advertisement", "ad campaign", "brand film", "promo video"), "Commercial production"),
    (("event coverage", "coverage for an event", "event photographer", "event photography", "event videography", "event video", "cover my event", "cover an event", "nightlife", "club night", "nightclub", "concert coverage", "festival coverage"), "Event coverage"),
    (("video production", "videography", "video shoot"), "Video production"),
    (("photography", "photographer", "photoshoot", "photo shoot"), "Photography"),
    (("creative content", "content production", "social content"), "Creative content production"),
    (("branding", "brand identity", "visual identity"), "Branding and visual creative services"),
    (("other creative production", "other creative project", "another creative project", "creative production", "creative project"), "Other creative production"),
)
DATE_RE = re.compile(
    r"\b(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|(?:sometime\s+)?next\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|week|month)"
    r"|(?:sometime\s+)?later\s+this\s+month"
    r"|this\s+(?:weekend|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
    r")\b", re.I)
UNKNOWN_DATE_RE = re.compile(r"\b(?:i\s+)?(?:don't|do not|haven't|have not)\s+(?:know|decided)(?:\s+yet)?\b|\bnot\s+sure\s+yet\b|\btbd\b", re.I)

def read_knowledge(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _extract_date(text):
    matches = [re.sub(r"\s+", " ", m.group(0)).strip(" .,!?;") for m in DATE_RE.finditer(text)]
    if matches:
        unique = list(dict.fromkeys(matches))
        if len(unique) > 1:
            return f"{unique[0]} or {unique[1]} (needs clarification)"
        return unique[0]
    if UNKNOWN_DATE_RE.search(text) and re.search(r"\b(date|shoot|film|event|schedule|when)\b", text, re.I):
        return "Not decided yet"
    return None

def _extract_name(text):
    found = _name_spans(text)
    return found[0][2] if found else None

def _name_spans(text):
    spans = []
    for match in re.finditer(r"\b(?:my name is|i am|i'm)\s+", text, re.I):
        remainder = text[match.end():]
        candidate = re.split(r"[,.!?;]|\s+(?:and|but|it's|it is|we're|i'm|i am|i want|we want)\b", remainder, maxsplit=1, flags=re.I)[0].strip()
        words = candidate.split()
        if not words or words[0].lower() in {"a", "an", "the", "looking", "planning", "interested", "hoping", "trying", "calling", "reaching"}:
            continue
        value = " ".join(words[:3])
        if re.fullmatch(r"[A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2}", value):
            spans.append((match.start(), match.end() + len(value), value.title()))
    return spans

def _extract_budget(text):
    match = re.search(r"\b(?:my\s+)?budget\s*(?:is|of|around|about|:)?\s*(\$\s?\d[\d,]*(?:\.\d{1,2})?\s*(?:k|thousand)?)", text, re.I)
    if not match:
        match = re.search(r"\b(?:around|about)\s+(\$\s?\d[\d,]*(?:\.\d{1,2})?\s*(?:k|thousand)?)", text, re.I)
    return re.sub(r"\s+", "", match.group(1)) if match else None

def _extract_location(text, history):
    # Look across turns, ignoring contact details and date phrases before interpreting
    # prepositions like "in" and "at" as location cues.
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        content = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", " ", item.get("content", ""))
        content = DATE_RE.sub(" ", content)
        matches = list(re.finditer(r"\b(?:in|at|near|around)\s+([A-Za-z][A-Za-z .'-]{1,45})", content))
        for match in reversed(matches):
            # An email after "reach me at" must not turn its local part into a city.
            if content[match.end(1):match.end(1) + 1] == "@":
                continue
            candidate = re.split(r"[,.;!?\n]|\b(?:on|by|for|to|next|this|sometime|later|during|with|how|what|when|and\s+(?:i|we)|i'd|i\s+would|to\s+shoot|to\s+film)\b", match.group(1), maxsplit=1, flags=re.I)[0].strip()
            normalized_candidate = re.sub(r"^(?:a|an|the)\s+", "", candidate, flags=re.I).strip().lower()
            if normalized_candidate in {"cinematic", "moody", "documentary", "vintage", "warm", "modern", "minimalist", "natural", "editorial", "black and white", "natural light", "soft light", "style", "look", "vibe", "mood", "tone"}:
                continue
            if candidate and candidate.lower() not in {"next month", "next week", "october", "oct", "a video", "the city", "sometime", "the venue"}:
                words = candidate.split()
                # Retain only the leading place-like words; lowercase common preposition phrases are not a location.
                candidate = " ".join(words[:3]).strip()
                if candidate:
                    return candidate
    # Short answers such as "Boston" are locations when responding to a location question.
    if len(history) >= 2 and history[-1].get("role") == "user" and history[-2].get("role") == "assistant":
        last = history[-1].get("content", "").strip()
        if re.search(r"\blocation\b|\bwhere\b", history[-2].get("content", ""), re.I) and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,45}", last):
            return last
    return None

def _extract_description(text, history=None):
    detail_words = (
        "cinematic", "r&b", "hip-hop", "hip hop", "indie", "documentary", "two locations", "multiple locations",
        "concept", "style", "vibe", "story", "outdoor", "studio", "live performance", "album cover", "editorial",
        "portrait", "headshot", "product photography", "brand", "commercial", "advertisement", "ad campaign",
        "launch", "recap", "aftermovie", "club night", "nightlife", "concert", "festival", "dance", "performance",
        "social content", "travel", "wedding", "birthday", "food photography", "product shoot", "campaign",
    )
    if not any(word in text.lower() for word in detail_words):
        return None
    cleaned = text
    cleaned = re.sub(r"^\s*(?:correction|actually|update|to clarify)\s*[:,—-]\s*", "", cleaned, flags=re.I)
    for start, end, _ in reversed(_name_spans(text)):
        cleaned = cleaned[:start] + cleaned[end:]
    cleaned = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "", cleaned)
    cleaned = re.sub(r"\b(?:reach|contact|call|text)\s+me\s+(?:at|on)\b.*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:my\s+)?budget\s*(?:(?:is|of)\s+)?(?:around\s+|about\s+)?\$?\d[\d,]*(?:\.\d{1,2})?\s*(?:k|thousand|dollars?)?", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:around|about)\s+\$?\d[\d,]*(?:\.\d{1,2})?\s*(?:k|thousand|dollars?)?", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:my\s+)?budget\b|\b(?:filming|shooting)\s*$", "", cleaned, flags=re.I)
    cleaned = DATE_RE.sub("", cleaned)
    cleaned = re.sub(r"\b(?:and\s+)?(?:i'd|i would|i want to|we'd|we would|we want to)\s+(?:like to\s+)?(?:shoot|film|record)\b", "", cleaned, flags=re.I)
    location = _extract_location(text, history or [{"role": "user", "content": text}])
    if location:
        cleaned = re.sub(r"\b(?:in|at|near|around)\s+" + re.escape(location) + r"\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:filming|shooting)\s*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(?:on|at|for)\s*(?=[,.!?;]|$)", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+([,.!?;])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?:;-\n")
    return cleaned[:1000] or None

def extract_from_history(history):
    """Deterministically recover explicit lead details from every visitor turn."""
    users = [m.get("content", "") for m in history if m.get("role") == "user"]
    combined = "\n".join(users)
    fields = {}
    # A later service mention in the same or a later turn supersedes an earlier one.
    for text in users:
        lowered = text.lower()
        service_matches = []
        for hints, service in SERVICE_HINTS:
            for hint in hints:
                for match in re.finditer(re.escape(hint), lowered):
                    service_matches.append((match.start(), len(hint), service))
        if service_matches:
            fields["service"] = max(service_matches, key=lambda item: (item[0], item[1]))[2]
    name = next((value for value in (_extract_name(text) for text in reversed(users)) if value), None)
    if name:
        fields["name"] = name
    emails = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", combined)
    if emails:
        fields["email"] = emails[-1]
    phones = re.findall(r"(?:\+?\d[\d ().-]{7,}\d)", combined)
    if phones:
        fields["phone"] = phones[-1].strip()
    previous_assistant = ""
    for item in history:
        if item.get("role") == "assistant":
            previous_assistant = item.get("content", "")
            continue
        if item.get("role") != "user":
            continue
        text = item.get("content", "")
        budget = _extract_budget(text)
        if budget:
            fields["budget"] = budget
        date = _extract_date(text)
        if not date and UNKNOWN_DATE_RE.search(text) and re.search(r"\b(date|timeframe|when|schedule|shoot)\b", previous_assistant, re.I):
            date = "Not decided yet"
        if date:
            fields["project_date"] = date
    location = _extract_location(combined, history)
    if location:
        fields["location"] = location
    for text in users:
        description = _extract_description(text, history)
        if description:
            fields["description"] = description
    return fields

def _question_about_price(text):
    return bool(re.search(r"\b(?:how much|price|pricing|cost|rate|rates|budget range)\b", text, re.I))

def _followup(history, lead, knowledge):
    last = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
    if _question_about_price(last) and "PLACEHOLDER" in knowledge.get("pricing", ""):
        prefix = "Pricing depends on the concept and production needs, and I don’t have approved rates to quote here. "
    else:
        prefix = ""
    if (lead.get("project_date") or "").endswith("(needs clarification)"):
        choices = lead["project_date"].removesuffix("(needs clarification)").strip()
        return prefix + f"I caught two possible dates, {choices}. Which one should I note for the project?"
    # Prioritize creative context; collect contact details after the brief has shape.
    if not lead.get("description"):
        return prefix + "What kind of look, feel, or story do you have in mind for the project?"
    if not lead.get("project_date"):
        return prefix + "Do you have a date or timeframe in mind for the shoot or event?"
    if not lead.get("location"):
        return prefix + "Where would you like the project to take place?"
    if not lead.get("email") and not lead.get("phone"):
        if lead.get("name"):
            return prefix + "That gives me a clear sense of the project. What’s the best way for the team to reach you—a phone number or email?"
        return prefix + "I have a useful outline to share with the team. What name and best contact method should I include—phone or email?"
    return prefix + "I’ve got the project details and your contact information. The Masterment team can review the brief and follow up to discuss next steps; no booking or availability is confirmed here."

def _has_repeated_field_question(reply, lead):
    checks = {
        "project_date": r"\b(?:what|when|which).{0,35}\b(?:date|day|timeframe|schedule|shoot)\b|\bdo you have a date\b",
        "location": r"\bwhere\b|\bwhat.{0,20}\blocation\b",
        "budget": r"\bwhat.{0,25}\bbudget\b|\bhow much can you spend\b",
        "name": r"\bwhat is your name\b|\bwho am i speaking with\b",
        "email": r"\bemail address\b|\bwhat is your email\b",
        "phone": r"\bphone number\b|\bwhat is your phone\b",
    }
    return any(lead.get(field) and re.search(pattern, reply, re.I) for field, pattern in checks.items())

def _asks_for_contact(reply):
    return bool(re.search(r"\b(?:what(?:'s| is)|share|provide|send|could you|can you|do you have|would you|best way|contact method)\b.{0,70}\b(?:phone|email|contact|reach you)\b|\b(?:phone|email)\s+or\s+(?:phone|email)\b", reply, re.I))

def _conversation_stage(lead):
    has_project_context = any(lead.get(field) for field in ("service", "description", "project_date", "location", "budget"))
    has_service = bool(lead.get("service"))
    has_contact = bool(lead.get("phone") or lead.get("email"))
    if has_contact and has_project_context:
        return "captured"
    if has_service and has_project_context:
        return "ready_for_contact"
    if has_service or has_project_context:
        return "qualification"
    return "discovery"

def _reply_has_known_field_request(reply, lead):
    if _has_repeated_field_question(reply, lead):
        return True
    # Phone and email are alternative ways to follow up. Either one is enough.
    if lead.get("phone") or lead.get("email"):
        if _asks_for_contact(reply):
            return True
        other_contact = "email" if lead.get("phone") else "phone"
        other_question = r"\b(?:what|which|your|share|provide|send|could you|can you)\b.{0,35}\b" + other_contact + r"\b"
        if re.search(other_question, reply, re.I):
            return True
    return False

def _has_generic_service_opening(reply):
    return bool(re.search(r"^\s*(?:thank you for reaching out|we(?:'re| are) excited to hear|it's great to learn more|we appreciate you sharing)", reply, re.I))

def fallback_reply(history, lead, knowledge):
    return _followup(history, lead, knowledge)

def generate_reply(history, lead, knowledge):
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return fallback_reply(history, lead, knowledge)
    stage = _conversation_stage(lead)
    system = {"role":"system","content":f"You are {knowledge['assistant_name']}, a modern, premium, creative, confident, natural and concise representative of {knowledge['company_name']}. Sound human and professional, never slang-heavy. Avoid generic customer-service openings and filler such as 'Thank you for reaching out', 'We're excited to hear', 'It's great to learn more', and 'We appreciate you sharing'. Respond to the specific project details instead of offering canned enthusiasm. APPROVED BUSINESS INFORMATION: {json.dumps(knowledge,ensure_ascii=False)}. Never invent prices, availability, policies, portfolio credits, contact details, hours, or company facts. Answer the customer's direct question first using approved facts. If pricing is not approved, acknowledge the question, explain briefly that pricing depends on production scope, and ask about the most relevant missing creative or logistical detail. Read the latest customer message in the context of the full conversation and captured lead. Acknowledge important details they just shared. Continue like a helpful creative producer, not an intake form: decide what is naturally useful to say next from the conversation, not by finding an empty database field. Ask at most one relevant follow-up, and only when it moves the conversation forward. Never ask for captured information. Do not request phone or email until the project has enough shape for a team follow-up; when appropriate ask for the best contact method, with phone OR email accepted. If either phone or email is already captured, do not ask for another contact method. Do not require both. When useful project details and one contact method are captured, close naturally: tell them the Masterment team can review the project and follow up, without promising a response time unless approved knowledge provides one. Avoid checklist language, repeated reassurance, or saying information can be skipped. Do not claim that a booking, availability, or estimate is confirmed. Current derived conversation stage: {stage}. Current captured project context (reference for continuity; not a question checklist): {json.dumps(lead,ensure_ascii=False)}."}
    messages = [system, *history]
    try:
        client = OpenAI(api_key=key)
        schema = {"type":"object","properties":{"reply":{"type":"string"}},"required":["reply"],"additionalProperties":False}
        def ask_model(context):
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0.5,
                response_format={"type":"json_schema","json_schema":{"name":"receptionist_reply","strict":True,"schema":schema}},
                messages=context,
            )
            return json.loads(response.choices[0].message.content)["reply"].strip()
        reply = ask_model(messages)
        if _reply_has_known_field_request(reply, lead) or _has_generic_service_opening(reply):
            correction = {"role":"system","content":f"Revise your previous draft. It either asked the customer for information that is already captured, requested another contact method even though one is enough, or used generic customer-service filler. Previous draft: {reply!r}. Respond naturally to the actual latest customer message, acknowledge its specific details, and continue the creative conversation without asking for any known facts or another contact method. Avoid canned openings like 'Thank you for reaching out', 'We're excited to hear', or 'We appreciate you sharing'. Answer any direct question first. Ask one useful creative follow-up only if that helps; otherwise acknowledge and move toward next steps."}
            reply = ask_model([*messages, correction])
        if _reply_has_known_field_request(reply, lead) or _has_generic_service_opening(reply):
            # A brief acknowledgement is safer than exposing an extraction checklist.
            reply = "That gives me a helpful picture of the project. I’ve noted those details for the team."
        return reply
    except Exception:
        # A configured AI path must not silently turn into the deterministic intake flow.
        return "Thanks for sharing those details. I’ve saved what you provided, but I’m having trouble responding right now. Please try again shortly."
