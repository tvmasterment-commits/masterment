ALTER TABLE conversations ADD COLUMN owner_hash TEXT;
ALTER TABLE conversations ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN sales_status TEXT NOT NULL DEFAULT 'NEW' CHECK(sales_status IN ('NEW','DISCOVERY','QUALIFIED','QUOTE_NEEDED','READY_TO_BOOK'));
ALTER TABLE leads ADD COLUMN sales_intent TEXT NOT NULL DEFAULT 'GENERAL_QUESTION';
ALTER TABLE leads ADD COLUMN intent_confidence REAL NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN service_id TEXT;
ALTER TABLE leads ADD COLUMN package_id TEXT;
ALTER TABLE leads ADD COLUMN conversation_summary TEXT;
ALTER TABLE leads ADD COLUMN next_action TEXT NOT NULL DEFAULT 'REVIEW_INQUIRY';
ALTER TABLE leads ADD COLUMN field_evidence TEXT NOT NULL DEFAULT '{}';
ALTER TABLE leads ADD COLUMN missing_fields TEXT NOT NULL DEFAULT '[]';
ALTER TABLE leads ADD COLUMN purchase_requested INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN legacy_review_required INTEGER NOT NULL DEFAULT 0;
UPDATE leads SET legacy_review_required=1 WHERE status='Booked';
CREATE TABLE chat_requests (
 request_id TEXT PRIMARY KEY,
 conversation_id TEXT NOT NULL REFERENCES conversations(id),
 owner_hash TEXT NOT NULL,
 input_hash TEXT NOT NULL,
 revision INTEGER NOT NULL,
 user_message_id INTEGER NOT NULL REFERENCES messages(id),
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','completed','stale')),
 response_json TEXT,
 created_at TEXT NOT NULL,
 UNIQUE(conversation_id, revision)
);
CREATE INDEX idx_chat_requests_owner ON chat_requests(owner_hash, created_at);
CREATE TABLE sales_transitions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 conversation_id TEXT NOT NULL REFERENCES conversations(id),
 revision INTEGER NOT NULL,
 from_state TEXT NOT NULL,
 to_state TEXT NOT NULL,
 intent TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(conversation_id, revision)
);
