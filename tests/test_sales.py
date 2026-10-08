import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from ai_fixtures import understanding
from app import create_app
from app.assistant import extract_from_history, fallback_reply, generate_reply, read_knowledge
from app.db import connect
from app.sales import price_block, conversation_catalog

ROOT = Path(__file__).resolve().parents[1]


class SalesTest(unittest.TestCase):
    def setUp(self):
        self.knowledge = read_knowledge(ROOT / "knowledge/business.json")

    def answer(self, message, earlier=()):
        history = [*earlier, {"role": "user", "content": message}]
        lead = extract_from_history(history, self.knowledge)
        return fallback_reply(history, lead, self.knowledge), lead

    def test_all_price_blocks_resolve_and_have_approved_amounts(self):
        for key, entry in self.knowledge["catalog"].items():
            for block in entry["price_blocks"]:
                with self.subTest(block=block):
                    self.assertRegex(price_block(self.knowledge, key, block), r"\$[\d,]+")

    def test_monthly_deliverables_and_exclusions(self):
        for tier, reels, photos, revisions in (("Essential", 2, 10, 1), ("Growth", 4, 15, 1), ("Signature", 6, 25, 2)):
            reply, _ = self.answer(tier + " package")
            for expected in (f"{reels} professionally produced Reels", f"{photos} professionally edited photos", f"{revisions} revision", "30–60", "ad spend", "guidance only", "separate", "not guaranteed"):
                self.assertIn(expected, reply)

    def test_frequency_recommends_relevant_package_only(self):
        for text, expected, excluded in (("2 Reels every month", "Essential", "Signature"), ("4 videos every month", "Growth", "Signature"), ("weekly video content", "Growth", "Signature"), ("6 Reels monthly", "Signature", "Essential")):
            reply, _ = self.answer(text)
            self.assertIn(expected, reply)
            self.assertNotIn(excluded + ":", reply)

    def test_setup_monthly_and_external_cost_limits(self):
        reply, _ = self.answer("Advanced website")
        self.assertIn("Starting at $1,800 setup + Starting at $129/month", reply)
        self.assertIn("may cost extra", reply)
        reply, _ = self.answer("Advanced bot")
        self.assertIn("Starting at $800 setup + Starting at $249/month", reply)
        self.assertIn("reasonable plan limits", reply)

    def test_combinations_persist_across_turns(self):
        history = [{"role": "user", "content": "I need a music video"}]
        reply, lead = self.answer("Also 4 dancers, hip-hop style", history)
        self.assertIn("Music video production", lead["service"])
        self.assertIn("Dancers", lead["service"])
        self.assertIn("CUSTOM QUOTE", reply)
        self.assertIn("not a combined estimate", reply)

    def test_service_correction_replaces_prior_intent(self):
        keys = conversation_catalog([{"role": "user", "content": "I need a website"}, {"role": "user", "content": "Correction: only need a bot instead"}], self.knowledge)
        self.assertEqual(keys, ["bot"])

    def test_international_does_not_quote_domestic_music_video_price(self):
        reply, _ = self.answer("Basic music video in Cabo Verde")
        self.assertIn("CUSTOM QUOTE", reply)
        self.assertNotIn("$600", reply)
        self.assertNotIn("cannot help", reply)

    def test_existing_website_does_not_sell_new_website(self):
        reply, lead = self.answer("I already have a website but want the bot you guys have")
        self.assertEqual(lead["service"], "Business Bot")
        self.assertIn("existing website", reply)
        self.assertNotIn("$750", reply)

    def test_drone_is_conditional(self):
        reply, _ = self.answer("Real estate photos and video with drone")
        for text in ("$450", "not guaranteed", "weather", "airspace", "regulations"):
            self.assertIn(text, reply)

    def test_unknown_price_and_nonmatching_monthly_volume_need_quote(self):
        for text in ("How much are business cards?", "I need 9 Reels monthly", "I need 20 videos every month"):
            reply, _ = self.answer(text)
            self.assertIn("CUSTOM QUOTE", reply)
            self.assertNotIn("$", reply)

    def test_no_repeated_digital_questions_after_answers(self):
        history = [{"role": "user", "content": "My name is Ada. I need a website and bot for a gym at https://example.com, 5 pages, FAQs and lead capture. Budget $2,000. Next month. ada@example.com"}]
        reply, lead = self.answer("Please have the team review it", history)
        self.assertIn("team can review", reply)
        self.assertNotIn("?", reply)
        self.assertEqual(lead["name"], "Ada")
        self.assertEqual(lead["budget"], "$2,000")
        self.assertNotEqual(lead.get("location"), "https")

    def test_new_details_survive_short_followups(self):
        history = [{"role": "user", "content": "I need a bot for https://example.com"}, {"role": "assistant", "content": "What should it do?"}]
        _, lead = self.answer("Collect leads and ask which of our three locations they prefer", history)
        self.assertIn("https://example.com", lead["description"])
        self.assertIn("three locations", lead["description"])

    def test_model_receives_relevant_knowledge_and_lead_context(self):
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status="completed", output=[], output_text=json.dumps(understanding("The team can review your existing site and desired bot features.", kwargs)))
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        history = [{"role": "user", "content": "I already have a website and want a bot"}]
        lead = extract_from_history(history, self.knowledge)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("app.assistant.OpenAI", return_value=client):
            reply = generate_reply(history, lead, self.knowledge)
        prompt = calls[0]["input"][0]["content"]
        for text in ("$149/month", "creative network", "Do NOT invent", "already have a website", "digital solutions"):
            self.assertIn(text, prompt)
        self.assertNotIn("$650/month", prompt)
        self.assertIn("existing site", reply)

    def test_unapproved_model_price_discount_and_guarantee_are_replaced(self):
        for bad in ("A single Reel is $99.", "We guarantee viral results.", "You get a 25% discount.", "Our AI usage is unlimited."):
            client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(status="completed", output=[], output_text=json.dumps(understanding(bad, kwargs)))))
            history = [{"role": "user", "content": "How much is one Reel?"}]
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("app.assistant.OpenAI", return_value=client):
                reply = generate_reply(history, {}, self.knowledge)
            self.assertNotEqual(reply, bad)
            self.assertIn("$250", reply)

    def test_starting_price_cannot_become_a_fixed_model_quote(self):
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(status="completed", output=[], output_text=json.dumps(understanding("Photography costs $250 total.", kwargs)))))
        history = [{"role": "user", "content": "How much is photography?"}]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}), patch("app.assistant.OpenAI", return_value=client):
            reply = generate_reply(history, {}, self.knowledge)
        self.assertIn("Starting at $250", reply)
        self.assertIn("final pricing depends", reply)

    def test_prices_are_read_from_knowledge(self):
        self.knowledge["business_knowledge"]["1"] = self.knowledge["business_knowledge"]["1"].replace("$650/month", "$675/month")
        reply, _ = self.answer("Growth package")
        self.assertIn("$675/month", reply)
        self.assertNotIn("$650", reply)

    def test_short_intake_answers_are_not_repeated(self):
        history = [
            {"role": "user", "content": "I need dancers in Boston next month"},
            {"role": "assistant", "content": "What dance style or type of talent do you need?"},
            {"role": "user", "content": "Traditional"},
            {"role": "assistant", "content": "How many dancers or performers do you need?"},
            {"role": "user", "content": "5"},
            {"role": "assistant", "content": "What budget would you like the team to work within?"},
            {"role": "user", "content": "$2000"},
            {"role": "assistant", "content": "What name should I include with the project brief?"},
        ]
        reply, lead = self.answer("Ada", history)
        self.assertEqual(lead["budget"], "$2000")
        self.assertEqual(lead["name"], "Ada")
        self.assertIn("best way", reply)
        self.assertNotIn("How many", reply)

    def test_services_overview_and_unpriced_maintenance(self):
        reply, _ = self.answer("What services do you offer?")
        self.assertIn("creative production & digital solutions", reply)
        self.assertIn("Website development", reply)
        for message in ("Bot maintenance", "Business cards", "Custom programming"):
            reply, _ = self.answer(message)
            self.assertIn("CUSTOM QUOTE", reply)
            self.assertNotIn("$", reply)


SCENARIOS = [
    ("essential", "Essential package", "$400/month"),
    ("growth", "Growth package", "$650/month"),
    ("signature", "Signature package", "$900/month"),
    ("single_reel", "How much is one Reel?", "Single Reel: $250"),
    ("photography", "Photography price", "Starting at $250"),
    ("event", "Event video price", "Starting at $350"),
    ("nightclub", "Nightclub coverage", "Starting at $400"),
    ("basic_music", "Basic music video", "Starting at $600"),
    ("standard_music", "Standard music video", "Starting at $1,000"),
    ("premium_music", "Premium music video", "Starting at $1,500"),
    ("wedding", "Wedding photo and video", "Starting at $1,200"),
    ("sweet16", "I'm having a Sweet 16", "Starting at $500"),
    ("real_estate_photo", "Real estate photos", "Starting at $250"),
    ("real_estate_video", "Real estate video", "Starting at $300"),
    ("realtor_recurring", "Realtor monthly content for multiple listings", "CUSTOM MONTHLY QUOTE"),
    ("starter_website", "Starter website", "$750 setup + $49/month"),
    ("business_website", "Business website", "$1,200 setup + $79/month"),
    ("advanced_website", "Advanced website", "Starting at $1,800"),
    ("existing_website_bot", "I have an existing website and want a bot", "existing website"),
    ("starter_bot", "Starter bot", "$300 setup + $79/month"),
    ("business_bot", "Business bot", "$500 setup + $149/month"),
    ("advanced_bot", "Advanced bot", "Starting at $800"),
    ("cabo_verde", "Film a music video in Cabo Verde", "creative network"),
    ("portugal", "Production in Portugal", "CUSTOM QUOTE"),
    ("mix_master", "Mix and master my song", "music professional"),
    ("beat", "Beat production", "CUSTOM QUOTE"),
    ("dancer", "Dancers for my music video", "confirmation"),
    ("website_bot", "Website + Bot", "not a combined estimate"),
    ("discount", "Can you do it cheaper?", "can’t authorize discounts"),
    ("results", "Can you guarantee sales?", "does not guarantee"),
    ("outside_package", "My requirements don't fit a package", "CUSTOM QUOTE"),
    ("management", "Manage my existing website", "technically feasible"),
    ("testimonial", "Business testimonial video", "Starting at $350"),
    ("poster", "A poster", "Starting at $100"),
]


def scenario_test(message, expected):
    def test(self):
        reply, _ = self.answer(message)
        self.assertIn(expected, reply)
    return test


for name, message, expected in SCENARIOS:
    setattr(SalesTest, "test_inquiry_" + name, scenario_test(message, expected))


class SalesPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "tests/sales-test.sqlite3"
        self.path.unlink(missing_ok=True)
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "", "APP_ENV": "development"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = create_app({"TESTING": True, "DATABASE_PATH": str(self.path), "KNOWLEDGE_PATH": str(ROOT / "knowledge/business.json"), "CHAT_RATE_LIMIT": 1000}).test_client()

    def check_lead(self, brief, service, detail):
        response = self.client.post('/api/chat', json={"message": "My name is Ada. " + brief + " in Boston next month. Budget $2,000. ada@example.com"})
        self.assertEqual(response.status_code, 200)
        lead = response.json["captured"]
        for field, expected in (("name", "Ada"), ("location", "Boston"), ("project_date", "next month"), ("budget", "$2,000"), ("email", "ada@example.com")):
            self.assertEqual(lead[field], expected)
        self.assertIn(service, lead["service"])
        self.assertIn(detail, lead["description"])
        cid = response.json['conversation_id']
        second = self.client.post('/api/chat', json={"conversation_id": cid, "message": "Our reference is https://example.com/brief"})
        self.assertIn(detail, second.json['captured']['description'])
        self.assertIn("https://example.com/brief", second.json['captured']['description'])
        self.assertEqual(len(self.client.get('/api/conversations/' + cid).json['messages']), 4)
        with connect(str(self.path)) as db:
            row = db.execute('SELECT * FROM leads WHERE conversation_id=?', (cid,)).fetchone()
            self.assertEqual(row['status'], 'New')
            self.assertIn(detail, row['description'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM leads').fetchone()[0], 1)

    def test_website_lead(self):
        self.check_lead("I need a website with 5 pages and a booking form", "Website development", "5 pages")

    def test_bot_lead(self):
        self.check_lead("I need a bot with lead capture and custom questions", "Business Bot", "custom questions")

    def test_international_lead(self):
        self.check_lead("I need a music video in Cabo Verde, Praia, coordinated from our office", "International", "Praia")

    def test_real_estate_lead(self):
        self.check_lead("I need real estate photos of a 2000 square feet house", "Real estate", "2000 square feet")
