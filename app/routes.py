import re
import secrets
import hmac
import uuid
from functools import wraps
from flask import Blueprint, current_app, jsonify, render_template, request, Response, session, abort
from .db import connect, ensure_conversation, add_message, upsert_lead
from .assistant import extract_from_history, generate_reply, read_knowledge
from .limiter import check_rate_limit
from .pricing import pricing_view

bp = Blueprint("main", __name__)
FIELDS = ("name", "phone", "email", "service", "project_date", "location", "budget", "description")
STATUSES = ("New", "Contacted", "Booked", "Closed")

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != current_app.config["ADMIN_USERNAME"] or auth.password != current_app.config["ADMIN_PASSWORD"]:
            return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Masterment Admin"'})
        return fn(*args, **kwargs)
    return wrapped

@bp.get("/")
def home():
    from .security import visitor_hash
    visitor_hash()
    knowledge = read_knowledge(current_app.config["KNOWLEDGE_PATH"])
    return render_template("index.html", knowledge=knowledge, pricing_sections=pricing_view(knowledge))

@bp.get("/health")
def health():
    return jsonify(status="ok")

@bp.post("/api/contact")
def direct_contact():
    # JSON-only requests cannot be submitted by a cross-origin HTML form.
    if not request.is_json:
        return jsonify(error="Please submit the form with JavaScript enabled."), 415
    retry_after = check_rate_limit("contact:" + (request.remote_addr or "unknown"), 5, 600)
    if retry_after:
        response = jsonify(error="Please wait a few minutes before sending another message.")
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Please provide your name, email and message."), 400
    fields = {}
    for key, limit in (("name", 120), ("email", 254), ("message", 4000)):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            return jsonify(error=f"Please enter a valid {key} (maximum {limit} characters)."), 400
        fields[key] = value.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", fields["email"]):
        return jsonify(error="Please enter a valid email address."), 400
    try:
        with connect(current_app.config["DATABASE_PATH"]) as db:
            conversation_id = str(uuid.uuid4())
            ensure_conversation(db, conversation_id)
            upsert_lead(db, conversation_id, {
                "name": fields["name"], "email": fields["email"], "description": fields["message"],
            })
            add_message(db, conversation_id, "user", fields["message"])
    except Exception:
        current_app.logger.exception("Unable to save direct contact enquiry")
        return jsonify(error="We couldn't save your message. Please try again."), 500
    return jsonify(message="Thank you. Your message has been received."), 201

@bp.post("/api/chat")
def chat():
    retry_after = check_rate_limit(
        request.remote_addr or "unknown",
        current_app.config["CHAT_RATE_LIMIT"],
        current_app.config["CHAT_RATE_WINDOW"],
    )
    if retry_after:
        response = jsonify(error="Too many messages. Please wait before trying again.")
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object is required."), 400
    message = data.get("message")
    conversation_id = data.get("conversation_id") or str(uuid.uuid4())
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        return jsonify(error="Please enter a message under 4,000 characters."), 400
    if not isinstance(conversation_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", conversation_id, re.I):
        return jsonify(error="Invalid conversation."), 400
    request_id = data.get('request_id')
    if request_id is not None and (not isinstance(request_id,str) or not re.fullmatch(r'[a-f0-9-]{36}',request_id,re.I)):
        return jsonify(error='Invalid request identity.'),400
    from .security import visitor_hash
    from .workflow import chat_turn, ChatError
    try:
        result, status = chat_turn(message.strip(),data.get('conversation_id'),request_id,visitor_hash())
        return jsonify(result),status
    except ChatError as error:
        return jsonify(error=error.message),error.status
    except Exception as error:
        current_app.logger.error('chat_storage_failure category=%s',type(error).__name__)
        return jsonify(error='We could not complete that response. Please retry your message.'),503


@bp.get('/api/chat/session')
def chat_session():
    from .security import visitor_hash
    visitor_hash()
    response=jsonify(ready=True)
    response.headers['Cache-Control']='no-store'
    return response

@bp.get("/api/conversations/<conversation_id>")
def conversation_history(conversation_id):
    if not re.fullmatch(r"[a-f0-9-]{36}", conversation_id, re.I):
        return jsonify(error="Invalid conversation."), 400
    with connect(current_app.config["DATABASE_PATH"]) as db:
        from .security import visitor_hash
        exists = db.execute("SELECT 1 FROM conversations WHERE id=? AND owner_hash=?", (conversation_id,visitor_hash())).fetchone()
        if not exists: return jsonify(error="Conversation not found."), 404
        rows = db.execute("SELECT id,role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)).fetchall()
    response=jsonify(conversation_id=conversation_id,messages=[dict(row) for row in rows])
    response.headers['Cache-Control']='no-store'
    return response

@bp.get("/admin")
@admin_required
def admin():
    with connect(current_app.config["DATABASE_PATH"]) as db:
        leads = db.execute("SELECT * FROM leads ORDER BY created_at DESC").fetchall()
    return render_template("admin.html", leads=leads, statuses=STATUSES)

@bp.get("/admin/leads/<int:lead_id>")
@admin_required
def lead_detail(lead_id):
    csrf_token = session.setdefault("admin_csrf_token", secrets.token_urlsafe(32))
    with connect(current_app.config["DATABASE_PATH"]) as db:
        lead = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not lead: return "Lead not found", 404
        messages = db.execute("SELECT id,role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id", (lead["conversation_id"],)).fetchall()
    return render_template("lead.html", lead=lead, messages=messages, statuses=STATUSES, csrf_token=csrf_token)

@bp.post("/admin/leads/<int:lead_id>/status")
@admin_required
def update_status(lead_id):
    csrf_token = session.get("admin_csrf_token")
    submitted_token = request.headers.get("X-CSRF-Token") if request.is_json else request.form.get("csrf_token")
    if not csrf_token or not submitted_token or not hmac.compare_digest(csrf_token, submitted_token):
        abort(403)
    payload = request.get_json(silent=True) if request.is_json else request.form
    if not isinstance(payload, dict) and request.is_json:
        return jsonify(error="A JSON object is required."), 400
    status = payload.get("status")
    if status not in STATUSES: return jsonify(error="Invalid status"), 400
    with connect(current_app.config["DATABASE_PATH"]) as db:
        cur = db.execute("UPDATE leads SET status=?,updated_at=datetime('now') WHERE id=?", (status, lead_id))
        if cur.rowcount == 0: return jsonify(error="Lead not found"), 404
    if request.is_json: return jsonify(status=status)
    from flask import redirect, url_for
    return redirect(url_for("main.lead_detail", lead_id=lead_id))
