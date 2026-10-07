"""Conversation ownership is independent of its public conversation identifier."""
import hashlib
import secrets
from flask import session


def visitor_hash():
    token = session.get('chat_owner')
    if not token:
        token = secrets.token_urlsafe(32)
        session['chat_owner'] = token
    return hashlib.sha256(token.encode()).hexdigest()
