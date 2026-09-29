import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.db import connect


class ContactTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = str(Path(self.temp.name) / "contact.sqlite3")
        self.app = create_app({"TESTING": True, "DATABASE_PATH": self.db_path})
        self.client = self.app.test_client()
        self.limiter = patch("app.routes.check_rate_limit", return_value=None)
        self.limiter.start()
        self.addCleanup(self.limiter.stop)
        self.payload = {"name": " Ada ", "email": "ada@example.com", "message": "A film collaboration."}

    def test_saves_enquiry_for_admin_without_calling_chat(self):
        with patch("app.routes.generate_reply") as bot:
            response = self.client.post("/api/contact", json=self.payload)
        self.assertEqual(response.status_code, 201)
        bot.assert_not_called()
        with connect(self.db_path) as db:
            lead = db.execute("SELECT * FROM leads").fetchone()
            self.assertEqual(lead["name"], "Ada")
            self.assertEqual(lead["email"], self.payload["email"])
            self.assertEqual(lead["description"], self.payload["message"])
            self.assertEqual(lead["status"], "New")
            self.assertEqual(db.execute("SELECT content FROM messages").fetchone()[0], self.payload["message"])

    def test_invalid_fields_do_not_create_leads(self):
        for field, values in {"name": [None, " ", "x" * 121], "email": ["invalid", "a@b..com", "x" * 255], "message": [[], "", "x" * 4001]}.items():
            for value in values:
                with self.subTest(field=field, value=str(value)[:20]):
                    self.assertEqual(self.client.post("/api/contact", json={**self.payload, field: value}).status_code, 400)
        with connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM leads").fetchone()[0], 0)

    def test_json_only_and_rate_limit(self):
        self.assertEqual(self.client.post("/api/contact", data=self.payload).status_code, 415)
        self.assertEqual(self.client.post("/api/contact", json=[]).status_code, 400)
        with patch("app.routes.check_rate_limit", return_value=45):
            response = self.client.post("/api/contact", json=self.payload)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "45")

    def test_storage_failure_does_not_report_success(self):
        with patch("app.routes.upsert_lead", side_effect=RuntimeError("private database details")):
            response = self.client.post("/api/contact", json=self.payload)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private database details", response.get_data(as_text=True))
        with connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0], 0)
