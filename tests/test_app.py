import json
import html
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from app import create_app
from app.assistant import extract_from_history, _conversation_stage

def fake_openai(responses, calls=None):
    calls = calls if calls is not None else []
    queue = list(responses)
    def create(**kwargs):
        calls.append(kwargs["messages"])
        value = queue.pop(0) if queue else responses[-1]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"reply":value})))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return lambda **kwargs: client

class AppTest(unittest.TestCase):
    def setUp(self):
        self.env_patch=patch.dict(os.environ,{"OPENAI_API_KEY":"","APP_ENV":"development"})
        self.env_patch.start()
        root = Path(__file__).resolve().parents[1]
        self.db_path = root / "tests" / "test.sqlite3"
        if self.db_path.exists(): self.db_path.unlink()
        self.app = create_app({"TESTING":True,"DATABASE_PATH":str(self.db_path),"KNOWLEDGE_PATH":str(root/"knowledge"/"business.json"),"ADMIN_USERNAME":"testadmin","ADMIN_PASSWORD":"testpass","SECRET_KEY":"test"})
        self.app.config["CHAT_RATE_LIMIT"]=200
        self.client = self.app.test_client()
        self.auth = {"Authorization":"Basic dGVzdGFkbWluOnRlc3RwYXNz"}
    def tearDown(self):
        if self.db_path.exists(): self.db_path.unlink()
        self.env_patch.stop()
    def test_customer_flow_and_saved_lead(self):
        first = self.client.post("/api/chat",json={"message":"I need a music video"})
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.json["captured"]["service"],"Music video production")
        cid=first.json["conversation_id"]
        second=self.client.post("/api/chat",json={"message":"My name is Jordan. My email is jordan@example.com","conversation_id":cid})
        self.assertEqual(second.status_code,200)
        self.assertEqual(second.json["captured"]["email"],"jordan@example.com")
        restored=self.client.get(f"/api/conversations/{cid}")
        self.assertEqual(len(restored.json["messages"]),4)
        with self.app.app_context():
            from app.db import connect
            with connect(self.app.config["DATABASE_PATH"]) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM leads").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],4)

    def test_five_service_conversations_persist_complete_leads_and_admin_history(self):
        scenarios = (
            {
                "message": "I am Maya, an R&B artist. I need a cinematic music video in Boston on October 17, 2026, two locations, around $1,000. Reach me at maya@example.com.",
                "service": "Music video production", "name": "Maya", "location": "Boston",
                "project_date": "October 17, 2026", "budget": "$1,000", "contact": "maya@example.com",
                "detail": "R&B artist", "contact_field": "email",
            },
            {
                "message": "My name is Jordan. I need editorial portrait photography for my album cover in Providence next Saturday. Budget about $500. Call me at 617-555-0199.",
                "service": "Photography", "name": "Jordan", "location": "Providence",
                "project_date": "next Saturday", "budget": "$500", "contact": "617-555-0199",
                "detail": "album cover", "contact_field": "phone",
            },
            {
                "message": "I am Chris. I need event coverage for a club night in Boston on November 14. About $800 budget. chris@example.com",
                "service": "Event coverage", "name": "Chris", "location": "Boston",
                "project_date": "November 14", "budget": "$800", "contact": "chris@example.com",
                "detail": "club night", "contact_field": "email",
            },
            {
                "message": "My name is Sam. We need a 30-second commercial for our coffee brand, warm cinematic look, filming in Cambridge next month. Budget is $2,000. sam@example.com",
                "service": "Commercial production", "name": "Sam", "location": "Cambridge",
                "project_date": "next month", "budget": "$2,000", "contact": "sam@example.com",
                "detail": "warm cinematic look", "contact_field": "email",
            },
            {
                "message": "I am Riley. I have another creative project in mind: a live dance performance recap, intimate and documentary style, in New York next month. Budget around $1,200. riley@example.com",
                "service": "Other creative production", "name": "Riley", "location": "New York",
                "project_date": "next month", "budget": "$1,200", "contact": "riley@example.com",
                "detail": "dance performance recap", "contact_field": "email",
            },
        )
        lead_ids=[]
        for scenario in scenarios:
            response=self.client.post("/api/chat",json={"message":scenario["message"]})
            self.assertEqual(response.status_code,200)
            captured=response.json["captured"]
            for field in ("name","service","project_date","location","budget"):
                self.assertEqual(captured[field],scenario[field],(scenario["service"],field))
            self.assertEqual(captured[scenario["contact_field"]],scenario["contact"])
            self.assertIn(scenario["detail"].lower(),captured["description"].lower())
            self.assertIn("team can review",response.json["reply"].lower())
            self.assertNotRegex(response.json["reply"],r"\b(?:within|in)\s+\d+\s+(?:hours|days|weeks)\b")
            cid=response.json["conversation_id"]
            restored=self.client.get(f"/api/conversations/{cid}")
            self.assertEqual([m["role"] for m in restored.json["messages"]],["user","assistant"])
            with self.app.app_context():
                from app.db import connect
                with connect(self.app.config["DATABASE_PATH"]) as db:
                    row=db.execute("SELECT * FROM leads WHERE conversation_id=?",(cid,)).fetchone()
                    self.assertEqual(row["status"],"New")
                    self.assertEqual(row["service"],scenario["service"])
                    self.assertEqual(row[scenario["contact_field"]],scenario["contact"])
                    lead_ids.append(row["id"])

        dashboard=self.client.get("/admin",headers=self.auth)
        self.assertEqual(dashboard.status_code,200)
        self.assertIn(b"5 leads captured",dashboard.data)
        for scenario, lead_id in zip(scenarios,lead_ids):
            with self.subTest(admin_detail=scenario["service"]):
                detail=self.client.get(f"/admin/leads/{lead_id}",headers=self.auth)
                self.assertEqual(detail.status_code,200)
                for field in ("name","service","project_date","location","budget","contact","detail"):
                    value=html.escape(scenario[field]).encode()
                    self.assertIn(value,detail.data,(scenario["service"],field))

    def test_price_fallback_uses_approved_limits_and_never_promises_timing(self):
        response=self.client.post("/api/chat",json={"message":"How much does a commercial video cost? We want a warm 30-second ad."})
        reply=response.json["reply"].lower()
        self.assertIn("pricing depends",reply)
        self.assertIn("starting at $500",reply)
        self.assertNotRegex(reply,r"\b(?:within|in)\s+\d+\s+(?:hours|days|weeks)\b")
        self.assertIn("final pricing depends",reply)

    def test_multiturn_music_video_intake_keeps_context_and_closes_after_email(self):
        first=self.client.post("/api/chat",json={"message":"Hi, I'm looking to shoot a music video next month in Boston. How much do you charge?"})
        cid=first.json["conversation_id"]
        self.assertEqual(first.json["captured"]["project_date"],"next month")
        self.assertEqual(first.json["captured"]["location"],"Boston")
        self.assertIn("pricing depends",first.json["reply"].lower())
        self.assertIn("Starting at $600",first.json["reply"])

        second=self.client.post("/api/chat",json={"message":"My name is Alex. I'm an R&B artist. I want a cinematic music video with two locations. My budget is around $1,000 and I'd like to shoot October 17, 2026.","conversation_id":cid})
        lead=second.json["captured"]
        self.assertEqual(lead["name"],"Alex")
        self.assertEqual(lead["service"],"Music video production")
        self.assertEqual(lead["location"],"Boston")
        self.assertEqual(lead["project_date"],"October 17, 2026")
        self.assertEqual(lead["budget"],"$1,000")
        self.assertIn("R&B artist",lead["description"])
        self.assertNotIn("date",second.json["reply"].lower())
        self.assertIn("best way",second.json["reply"].lower())

        third=self.client.post("/api/chat",json={"message":"Email is alex@example.com.","conversation_id":cid})
        self.assertEqual(third.json["captured"]["email"],"alex@example.com")
        self.assertIn("team can review",third.json["reply"].lower())
        self.assertNotIn("phone",third.json["reply"].lower())
        restored=self.client.get(f"/api/conversations/{cid}")
        self.assertEqual(len(restored.json["messages"]),6)
        with self.app.app_context():
            from app.db import connect
            with connect(self.app.config["DATABASE_PATH"]) as db:
                row=db.execute("SELECT * FROM leads WHERE conversation_id=?",(cid,)).fetchone()
                self.assertEqual(row["status"],"New")
                self.assertEqual(row["location"],"Boston")
                self.assertEqual(row["email"],"alex@example.com")

    def test_customer_correction_updates_lead_fields_without_duplicate(self):
        first=self.client.post("/api/chat",json={"message":"My name is Alex. I want a cinematic music video in Boston on October 17, 2026, two locations. Budget $1,000. Email alex@example.com."})
        cid=first.json["conversation_id"]
        corrected=self.client.post("/api/chat",json={"message":"Correction: my name is Alexa. It is a commercial instead, in Providence on October 24, 2026, budget $2,000. Please use alexa@example.com.","conversation_id":cid})
        self.assertEqual(corrected.status_code,200)
        lead=corrected.json["captured"]
        self.assertEqual(lead["name"],"Alexa")
        self.assertEqual(lead["service"],"Commercial production")
        self.assertEqual(lead["location"],"Providence")
        self.assertEqual(lead["project_date"],"October 24, 2026")
        self.assertEqual(lead["budget"],"$2,000")
        self.assertEqual(lead["email"],"alexa@example.com")
        self.assertNotIn("Correction",lead["description"])
        with self.app.app_context():
            from app.db import connect
            with connect(self.app.config["DATABASE_PATH"]) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM leads WHERE conversation_id=?",(cid,)).fetchone()[0],1)
                row=db.execute("SELECT name,service,location,project_date,budget,email FROM leads WHERE conversation_id=?",(cid,)).fetchone()
                self.assertEqual(row["name"],"Alexa")
                self.assertEqual(row["service"],"Commercial production")
        admin=self.client.get("/admin",headers=self.auth)
        self.assertIn(b"Alexa",admin.data)
        with self.app.app_context():
            with connect(self.app.config["DATABASE_PATH"]) as db: lead_id=db.execute("SELECT id FROM leads WHERE conversation_id=?",(cid,)).fetchone()[0]
        detail=self.client.get(f"/admin/leads/{lead_id}",headers=self.auth)
        self.assertIn(b"October 24, 2026",detail.data)
        self.assertIn(b"alexa@example.com",detail.data)

    def test_quick_start_intents_map_to_supported_services(self):
        from app.assistant import extract_from_history
        quick_starts=(
            ("I'm interested in a music video.","Music video production"),
            ("I'm looking for photography.","Photography"),
            ("I need coverage for an event.","Event coverage"),
            ("I'm exploring a commercial production.","Commercial production"),
            ("I have another creative project in mind.","Other creative production"),
        )
        for prompt, expected in quick_starts:
            with self.subTest(prompt=prompt):
                self.assertEqual(extract_from_history([{"role":"user","content":prompt}])["service"],expected)

    def test_visual_style_is_not_misclassified_as_a_project_location(self):
        response=self.client.post("/api/chat",json={"message":"I need a cinematic music video in a moody, documentary style. I want to shoot October 17."})
        self.assertEqual(response.status_code,200)
        self.assertNotIn("location",response.json["captured"])
        self.assertIn("where would you like",response.json["reply"].lower())

    def test_openai_prompt_uses_masterment_brand_identity(self):
        calls=[]
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test-key"}), patch("app.assistant.OpenAI",side_effect=fake_openai(["What kind of visual direction do you have in mind?"],calls)):
            response=self.client.post("/api/chat",json={"message":"I need a photography project."})
        self.assertEqual(response.status_code,200)
        system_message=calls[0][0]["content"]
        self.assertIn("You are Masterment,",system_message)
        self.assertNotIn("You are Masterment AI",system_message)
    def test_admin_auth_dashboard_detail_and_status(self):
        response=self.client.post("/api/chat",json={"message":"Photographer for an event"})
        self.assertEqual(self.client.get("/admin").status_code,401)
        dashboard=self.client.get("/admin",headers=self.auth)
        self.assertEqual(dashboard.status_code,200)
        self.assertIn(b"Project inquiries",dashboard.data)
        with self.app.app_context():
            from app.db import connect
            with connect(self.app.config["DATABASE_PATH"]) as db: lead_id=db.execute("SELECT id FROM leads").fetchone()[0]
        detail=self.client.get(f"/admin/leads/{lead_id}",headers=self.auth)
        self.assertEqual(detail.status_code,200)
        csrf=re.search(rb'name="csrf_token" value="([^"]+)"',detail.data).group(1).decode()
        missing_csrf=self.client.post(f"/admin/leads/{lead_id}/status",headers={**self.auth,"Content-Type":"application/json"},data=json.dumps({"status":"Contacted"}))
        self.assertEqual(missing_csrf.status_code,403)
        updated=self.client.post(f"/admin/leads/{lead_id}/status",headers={**self.auth,"Content-Type":"application/json","X-CSRF-Token":csrf},data=json.dumps({"status":"Contacted"}))
        self.assertEqual(updated.json["status"],"Contacted")
        self.assertEqual(self.client.get(f"/admin/leads/{lead_id}").status_code,401)
        self.assertEqual(self.client.post(f"/admin/leads/{lead_id}/status",data={"status":"Closed"}).status_code,401)
    def test_validation(self):
        self.assertEqual(self.client.post("/api/chat",json={"message":" "}).status_code,400)
        self.assertEqual(self.client.post("/api/chat",json=["not","an object"]).status_code,400)
        self.assertEqual(self.client.post("/api/chat",json={"message":"hello","conversation_id":123}).status_code,400)
        self.assertEqual(self.client.post("/api/chat",json={"message":"x"*4001}).status_code,400)

    def test_natural_date_formats_are_extracted(self):
        for value in ("October 17, 2026", "Oct 17", "10/17/2026", "next Saturday", "sometime next month"):
            with self.subTest(value=value):
                lead=extract_from_history([{"role":"user","content":f"We'd like to shoot {value}."}])
                self.assertEqual(lead["project_date"],value.rstrip("."))

    def test_unknown_date_answer_is_preserved_as_an_answer(self):
        lead=extract_from_history([
            {"role":"assistant","content":"Do you have a date or timeframe in mind for the shoot?"},
            {"role":"user","content":"I don't know yet."},
        ])
        self.assertEqual(lead["project_date"],"Not decided yet")

    def test_multiple_possible_dates_get_a_clarifying_question(self):
        lead=extract_from_history([{"role":"user","content":"We could shoot October 17 or October 24."}])
        self.assertIn("needs clarification",lead["project_date"])
        from app.assistant import fallback_reply
        root=Path(__file__).resolve().parents[1]
        from app.assistant import read_knowledge
        reply=fallback_reply([{"role":"user","content":"We could shoot October 17 or October 24."}],lead,read_knowledge(root/"knowledge"/"business.json"))
        self.assertIn("Which one",reply)

    def test_multifield_intake_persists_date_location_budget_and_style(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY":""}):
            first=self.client.post("/api/chat",json={"message":"Hi, I'm looking to shoot a music video next month in Boston. How much do you charge?"})
            self.assertEqual(first.status_code,200)
            cid=first.json["conversation_id"]
            self.assertIn("final pricing depends",first.json["reply"])
            self.assertEqual(first.json["captured"]["project_date"],"next month")
            self.assertEqual(first.json["captured"]["location"],"Boston")
            second=self.client.post("/api/chat",json={"message":"My name is Alex. It's an R&B video, cinematic, two locations. My budget is around $1,000 and I'd like to shoot October 17.","conversation_id":cid})
        self.assertEqual(second.status_code,200)
        lead=second.json["captured"]
        self.assertEqual(lead["name"],"Alex")
        self.assertEqual(lead["service"],"Music video production")
        self.assertEqual(lead["description"],"It's an R&B video, cinematic, two locations")
        self.assertEqual(lead["budget"],"$1,000")
        self.assertEqual(lead["project_date"],"October 17")
        self.assertEqual(lead["location"],"Boston")
        self.assertNotIn("what is your project or event date",second.json["reply"].lower())
        self.assertIn("best way",second.json["reply"].lower())

    def test_model_null_date_cannot_trigger_a_repeated_date_question(self):
        calls=[]
        with patch.dict("os.environ", {"OPENAI_API_KEY":"test-key"}), patch("app.assistant.OpenAI",side_effect=fake_openai(["What is your project or event date?", "That has a clear visual direction. What feeling do you want the video to leave with the audience?"],calls)):
            response=self.client.post("/api/chat",json={"message":"I'm shooting a cinematic music video October 17, 2026 in Boston. Budget is $1,000."})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json["captured"]["project_date"],"October 17, 2026")
        self.assertNotIn("project or event date",response.json["reply"].lower())
        self.assertIn("feeling",response.json["reply"].lower())
        self.assertEqual(len(calls),2)
        self.assertIn("Revise your previous draft",calls[1][-1]["content"])

    def test_phone_or_email_is_one_contact_choice_and_state_survives_turns(self):
        calls=[]
        with patch.dict("os.environ", {"OPENAI_API_KEY":"test-key"}), patch("app.assistant.OpenAI",side_effect=fake_openai([
            "That sounds like a strong concept. What’s the best way to reach you—a phone or email?",
            "What is your phone number?",
            "Thanks, Alex. I’ve noted that email for the team. Do you have a visual reference in mind?",
        ],calls)):
            first=self.client.post("/api/chat",json={"message":"My name is Alex. I'm an R&B artist. I want a cinematic music video with two locations. My budget is around $1,000 and I'd like to shoot October 17, 2026."})
            cid=first.json["conversation_id"]
            second=self.client.post("/api/chat",json={"message":"Use alex@example.com to reach me.","conversation_id":cid})
        self.assertIn("best way",first.json["reply"].lower())
        self.assertEqual(second.json["captured"]["email"],"alex@example.com")
        self.assertNotIn("phone",second.json["reply"].lower())
        self.assertNotIn("phone",second.json["captured"])
        # Later model context contains both the earlier creative brief and persisted contact detail.
        second_context=calls[1]
        self.assertTrue(any("two locations" in item.get("content","") for item in second_context))
        self.assertTrue(any("alex@example.com" in item.get("content","") for item in second_context if item.get("role")=="system"))
        self.assertEqual(_conversation_stage(second.json["captured"]),"captured")

    def test_one_contact_method_is_enough_to_capture_lead(self):
        self.assertEqual(_conversation_stage({"service":"Music video production","description":"Cinematic R&B video","email":"alex@example.com"}),"captured")
        self.assertEqual(_conversation_stage({"service":"Music video production","description":"Cinematic R&B video","phone":"5551234567"}),"captured")

    def test_model_answers_direct_question_before_discovery_followup(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY":"test-key"}), patch("app.assistant.OpenAI",side_effect=fake_openai([
            "Pricing depends on the concept and production needs. I don’t have approved rates to quote, but I can help the team understand the scope. What visual style are you imagining?"
        ])):
            response=self.client.post("/api/chat",json={"message":"How much do you charge for an R&B music video?"})
        self.assertIn("don’t have approved rates",response.json["reply"])
        self.assertLess(response.json["reply"].lower().index("pricing"),response.json["reply"].lower().index("what visual style"))

    def test_no_key_keeps_deterministic_fallback_available(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY":""}):
            response=self.client.post("/api/chat",json={"message":"I need a music video"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json["captured"]["service"],"Music video production")
        self.assertTrue(response.json["reply"])

    def test_configured_model_error_does_not_switch_to_missing_field_prompts(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY":"configured-key"}), patch("app.assistant.OpenAI",side_effect=RuntimeError("provider unavailable")):
            response=self.client.post("/api/chat",json={"message":"I need a music video"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json["captured"]["service"],"Music video production")
        self.assertIn("trouble responding",response.json["reply"].lower())
        self.assertNotIn("provider unavailable",response.json["reply"].lower())
        self.assertNotIn("what kind of look",response.json["reply"].lower())

    def test_r_and_b_artist_description_keeps_ampersand_and_full_phrase(self):
        message="My name is Alex. I'm an R&B artist. I want a cinematic music video with two locations."
        with patch.dict(os.environ,{"OPENAI_API_KEY":""}):
            response=self.client.post("/api/chat",json={"message":message})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json["captured"]["name"],"Alex")
        description=response.json["captured"]["description"]
        self.assertIn("I'm an R&B artist",description)
        self.assertIn("cinematic music video with two locations",description)
        self.assertFalse(description.startswith("&B"))

    def test_generic_model_opening_is_revised(self):
        calls=[]
        with patch.dict(os.environ,{"OPENAI_API_KEY":"test-key"}), patch("app.assistant.OpenAI",side_effect=fake_openai([
            "Thank you for reaching out! We're excited to hear about your project.",
            "Cinematic R&B across two locations gives this a strong visual direction. Do you have a reference in mind?",
        ],calls)):
            response=self.client.post("/api/chat",json={"message":"I want a cinematic R&B music video with two locations."})
        self.assertIn("strong visual direction",response.json["reply"])
        self.assertEqual(len(calls),2)

    def test_health_endpoint_is_minimal(self):
        response=self.client.get("/health")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json,{"status":"ok"})

    def test_chat_rate_limit_returns_retry_after(self):
        self.app.config["CHAT_RATE_LIMIT"]=2
        self.app.config["CHAT_RATE_WINDOW"]=60
        for _ in range(2):
            self.assertEqual(self.client.post("/api/chat",json={"message":"Hello"},environ_overrides={"REMOTE_ADDR":"198.51.100.77"}).status_code,200)
        limited=self.client.post("/api/chat",json={"message":"Hello"},environ_overrides={"REMOTE_ADDR":"198.51.100.77"})
        self.assertEqual(limited.status_code,429)
        self.assertEqual(limited.headers["Retry-After"],"60")

    def test_production_requires_non_default_secrets(self):
        with patch.dict(os.environ,{"APP_ENV":"production","FLASK_SECRET_KEY":"short","ADMIN_USERNAME":"admin","ADMIN_PASSWORD":"change-this-before-deploying"}):
            with self.assertRaisesRegex(RuntimeError,"FLASK_SECRET_KEY"):
                create_app()
        with patch.dict(os.environ,{"APP_ENV":"production","FLASK_SECRET_KEY":"Ab3dEf6hJ9kLm2NpQr5sTv8xY1zC4wGh","ADMIN_USERNAME":"admin","ADMIN_PASSWORD":"a-strong-test-password"}):
            with self.assertRaisesRegex(RuntimeError,"ADMIN_USERNAME"):
                create_app()

    def test_secret_hygiene_frontend_escaping_and_input_limit(self):
        root=Path(__file__).resolve().parents[1]
        self.assertRegex((root/".gitignore").read_text(encoding="utf-8"),r"(?m)^\.env$")
        env_example=(root/".env.example").read_text(encoding="utf-8-sig")
        self.assertRegex(env_example,r"(?m)^OPENAI_API_KEY=\s*$")
        self.assertRegex(env_example,r"(?m)^FLASK_SECRET_KEY=\s*$")
        self.assertIn("waitress>=3.0",(root/"requirements.txt").read_text(encoding="utf-8-sig"))
        self.assertRegex((root/".gitignore").read_text(encoding="utf-8"),r"(?m)^instance/$")
        javascript=(root/"app"/"static"/"chat.js").read_text(encoding="utf-8")
        self.assertNotIn("OPENAI_API_KEY",javascript)
        self.assertIn("textContent = text",javascript)
        too_long=self.client.post("/api/chat",json={"message":"x"*4001})
        self.assertEqual(too_long.status_code,400)
        xss=self.client.post("/api/chat",json={"message":"<script>alert(1)</script>"})
        with self.app.app_context():
            from app.db import connect
            with connect(self.app.config["DATABASE_PATH"]) as db: lead_id=db.execute("SELECT id FROM leads WHERE conversation_id=?",(xss.json["conversation_id"],)).fetchone()[0]
        detail=self.client.get(f"/admin/leads/{lead_id}",headers=self.auth)
        self.assertNotIn(b"<script>alert(1)</script>",detail.data)

    def test_customer_redesign_keeps_brand_navigation_and_existing_chat_hooks(self):
        page = self.client.get("/").get_data(as_text=True)
        root = Path(__file__).resolve().parents[1]
        for text in ("MASTERMENT", "CREATIVE AGENCY", "BRING YOUR", "Start a Project", "Welcome to Masterment.", "SELECTED WORK"):
            self.assertIn(text, page)
        for anchor in ("work", "services", "about", "contact"):
            self.assertIn(f'href="#{anchor}"', page)
        for hook in ('id="chat-form"', 'id="chat-panel"', 'id="chat-widget"', 'id="direct-contact"', 'id="messages"'):
            self.assertIn(hook, page)
        self.assertEqual(page.count("data-prompt="), 5)
        script = (root / "app/static/chat.js").read_text(encoding="utf-8-sig")
        for hook in ("/api/chat", "/api/conversations/", "sessionStorage", "textContent = text", "form.requestSubmit()"):
            self.assertIn(hook, script)
        self.assertIn('/static/videos/hero-showreel.mp4', page)
        self.assertIn('class="hero-video" autoplay muted loop playsinline', page)

    def test_current_portfolio_media_and_profile_links_are_preserved(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertEqual(page.count('class="reels-video"'), 9)
        self.assertEqual(page.count('class="portfolio-card'), 2)
        for number in (1, 3):
            self.assertIn(f'/static/videos/work/work-{number:02d}.mp4', page)
        for number in range(1, 10):
            self.assertIn(f'/static/videos/reels/reels-{number}.mp4', page)
        for url in ("https://youtube.com/@masterment", "https://www.instagram.com/master_ment", "https://www.instagram.com/kriolspirit/", "https://open.spotify.com/artist/", "https://music.apple.com/us/artist/masterment"):
            self.assertIn(url, page)
        self.assertIn('class="project-video" autoplay muted loop playsinline', page)

    def test_current_customer_page_hierarchy_preserves_project_intake(self):
        page = self.client.get("/").get_data(as_text=True)
        self.assertLess(page.index('id="work"'), page.index('id="services"'))
        self.assertLess(page.index('id="services"'), page.index('id="about"'))
        self.assertLess(page.index('id="about"'), page.index('id="contact"'))
        for label in ("VIDEO PRODUCTION", "PHOTOGRAPHY", "CREATIVE DIRECTION", "BRANDING &amp; DESIGN", "WEB &amp; DIGITAL DEVELOPMENT", "ARTIST &amp; MUSIC SERVICES"):
            self.assertIn(f"<h3>{label}</h3>", page)
        for text in ('<span>BUILT</span>', '<span>FROM</span>', 'MUSIC.</span>', 'OUR PARTNERS:', 'class="about-partner-track"', 'class="about-logo"'):
            self.assertIn(text, page)
        self.assertIn('action="/api/contact"', page)
        for asset in ("customer.css", "reels.css", "chat-widget.css", "chat.js", "customer.js", "reels.js", "contact.js", "chat-widget.js"):
            self.assertIn('/static/' + asset, page)

    def test_admin_credentials_are_loaded_from_environment(self):
        root=Path(__file__).resolve().parents[1]
        db_path=root/"tests"/"environment-config.sqlite3"
        if db_path.exists(): db_path.unlink()
        with patch.dict(os.environ,{"ADMIN_USERNAME":"environment-admin","ADMIN_PASSWORD":"a-unique-test-password","FLASK_SECRET_KEY":"test-secret-key-with-enough-characters"}):
            configured=create_app({"DATABASE_PATH":str(db_path),"KNOWLEDGE_PATH":str(root/"knowledge"/"business.json")})
        self.assertEqual(configured.config["ADMIN_USERNAME"],"environment-admin")
        self.assertEqual(configured.config["ADMIN_PASSWORD"],"a-unique-test-password")
        self.assertFalse(configured.debug)
        if db_path.exists(): db_path.unlink()

    def test_a_later_turn_does_not_erase_an_earlier_date(self):
        first=self.client.post("/api/chat",json={"message":"The shoot is October 17, 2026 in Boston."})
        cid=first.json["conversation_id"]
        second=self.client.post("/api/chat",json={"message":"It's a cinematic R&B music video with two locations.","conversation_id":cid})
        self.assertEqual(second.json["captured"]["project_date"],"October 17, 2026")
        self.assertEqual(second.json["captured"]["location"],"Boston")
        self.assertNotIn("project or event date",second.json["reply"].lower())

if __name__ == "__main__": unittest.main()
