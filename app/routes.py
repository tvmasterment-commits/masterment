import re
import secrets
import hmac
import uuid
from functools import wraps
from flask import Blueprint, current_app, jsonify, render_template, request, Response, session, abort
from .db import connect, ensure_conversation, add_message, upsert_lead
from .assistant import extract_from_history, generate_reply, read_knowledge
from .limiter import check_rate_limit

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
    knowledge = read_knowledge(current_app.config["KNOWLEDGE_PATH"])
    return render_template("index.html", knowledge=knowledge)

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
    with connect(current_app.config["DATABASE_PATH"]) as db:
        ensure_conversation(db, conversation_id)
        add_message(db, conversation_id, "user", message.strip())
        lead_row = db.execute("SELECT * FROM leads WHERE conversation_id=?", (conversation_id,)).fetchone()
        lead = {field: (lead_row[field] if lead_row else None) for field in FIELDS}
        rows = db.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)).fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in rows]
        # Extraction and persistence are independent of the conversational response.
        extracted = {**lead, **extract_from_history(history)}
        reply = generate_reply(history, extracted, read_knowledge(current_app.config["KNOWLEDGE_PATH"]))
        saved = upsert_lead(db, conversation_id, extracted)
        add_message(db, conversation_id, "assistant", reply)
        captured = {field: saved[field] for field in FIELDS if saved[field]}
        return jsonify(conversation_id=conversation_id, reply=reply, captured=captured, status=saved["status"])

@bp.get("/api/conversations/<conversation_id>")
def conversation_history(conversation_id):
    if not re.fullmatch(r"[a-f0-9-]{36}", conversation_id, re.I):
        return jsonify(error="Invalid conversation."), 400
    with connect(current_app.config["DATABASE_PATH"]) as db:
        exists = db.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not exists: return jsonify(error="Conversation not found."), 404
        rows = db.execute("SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)).fetchall()
    return jsonify(conversation_id=conversation_id,messages=[dict(row) for row in rows])

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
        messages = db.execute("SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id", (lead["conversation_id"],)).fetchall()
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
