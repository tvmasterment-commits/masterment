import copy
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.assistant import read_knowledge
from app.pricing import pricing_view
from app.sales import price_block, offer_data

ROOT = Path(__file__).resolve().parents[1]


class PricingTest(unittest.TestCase):
    def setUp(self):
        self.knowledge = read_knowledge(ROOT / 'knowledge/business.json')
        self.path = ROOT / 'tests/pricing-test.sqlite3'
        self.path.unlink(missing_ok=True)
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))
        env = patch.dict(os.environ, {'APP_ENV': 'development', 'OPENAI_API_KEY': ''})
        env.start()
        self.addCleanup(env.stop)
        self.client = create_app({'TESTING': True, 'DATABASE_PATH': str(self.path)}).test_client()
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.page = response.get_data(as_text=True)

    def test_accessible_modal_and_navigation(self):
        self.assertIn('class="pricing-trigger" type="button" aria-haspopup="dialog"', self.page)
        self.assertIn('<dialog class="pricing-dialog" id="pricing-dialog"', self.page)
        self.assertIn('aria-labelledby="pricing-title"', self.page)
        self.assertIn('aria-label="Close pricing"', self.page)
        self.assertEqual(self.page.count('<dialog '), 1)
        self.assertEqual(self.page.count('VIEW DETAILS'), 3)

    def test_services_trigger_reuses_modal_and_preserves_list(self):
        section = re.search(r'<section class="disciplines-section.*?</section>', self.page, re.S).group()
        self.assertIn('class="services-pricing-trigger" type="button" aria-haspopup="dialog" aria-controls="pricing-dialog"', section)
        self.assertIn('Explore packages &amp; starting rates', section)
        self.assertEqual(section.count('<li>'), 6)
        for label in ('VIDEO PRODUCTION', 'PHOTOGRAPHY', 'CREATIVE DIRECTION', 'BRANDING &amp; DESIGN', 'WEB &amp; DIGITAL DEVELOPMENT', 'ARTIST &amp; MUSIC SERVICES'):
            self.assertIn(f'<h3>{label}</h3>', section)
        self.assertEqual(self.page.count('id="pricing-dialog"'), 1)

    def test_all_prices_match_shared_chat_source(self):
        for section in pricing_view(self.knowledge):
            for offer in section['offers']:
                with self.subTest(offer=offer['name']):
                    self.assertIn(f'data-pricing-price="{offer["display_price"]}"', self.page)
        for key, entry in self.knowledge['catalog'].items():
            for heading in entry['price_blocks']:
                for price in offer_data(self.knowledge, key, heading)['prices']:
                    self.assertIn(price, price_block(self.knowledge, key, heading))

    def test_public_and_chat_prices_change_together(self):
        knowledge = copy.deepcopy(self.knowledge)
        knowledge['business_knowledge']['1'] = knowledge['business_knowledge']['1'].replace('$650/month', '$675/month')
        growth = pricing_view(knowledge)[0]['offers'][1]
        self.assertEqual(growth['display_price'], '$675/month')
        self.assertIn('$675/month', price_block(knowledge, 'monthly', 'GROWTH'))
        with patch('app.routes.read_knowledge', return_value=knowledge):
            page = self.client.get('/').get_data(as_text=True)
        self.assertIn('data-pricing-price="$675/month"', page)
        self.assertNotIn('$650', page)

    def test_missing_price_does_not_borrow_next_tier(self):
        self.knowledge['business_knowledge']['3'] = self.knowledge['business_knowledge']['3'].replace('Starting at $600', '')
        with self.assertRaises(ValueError):
            offer_data(self.knowledge, 'music_video', 'BASIC MUSIC VIDEO')

    def test_qualifiers_exclusions_and_no_unapproved_custom_prices(self):
        for expected in ('Integration subject to technical compatibility', 'Advertising guidance only', 'AI/API usage', 'Domain fees', 'Starting prices are not final quotes'):
            self.assertIn(expected, self.page)
        for section in ('maintenance', 'network'):
            block = re.search(r'<section class="pricing-section" id="pricing-' + section + r'".*?</section>', self.page, re.S).group()
            self.assertIn('CUSTOM QUOTE', block)
            self.assertNotIn('$', block)
        self.assertNotIn('PLACEHOLDER', self.page)

    def test_existing_contact_and_chat_interfaces_are_unique(self):
        for element in ('direct-contact', 'contact-message', 'chat-widget', 'chat-panel', 'chat-form', 'chat-input'):
            self.assertEqual(self.page.count(f'id="{element}"'), 1)
        self.assertIn('class="pricing-project" href="#contact"', self.page)
        self.assertIn('class="pricing-ask"', self.page)
        self.assertIn('data-pricing-selection="Monthly Content — Growth"', self.page)
        self.assertIn('data-pricing-price="$650/month"', self.page)

    def test_selected_package_can_use_existing_contact_storage(self):
        message = 'Selected service/package: Monthly Content — Growth\nDisplayed price: $650/month\n\nContent for my gym.'
        response = self.client.post('/api/contact', json={'name': 'Pricing Test', 'email': 'pricing@example.com', 'message': message})
        self.assertEqual(response.status_code, 201)
        from app.db import connect
        with connect(str(self.path)) as db:
            row = db.execute('SELECT description,status FROM leads').fetchone()
            self.assertEqual(row['description'], message)
            self.assertEqual(row['status'], 'New')

    def test_modal_adds_no_media_or_framework(self):
        template = (ROOT / 'app/templates/_pricing.html').read_text(encoding='utf-8')
        self.assertNotRegex(template, r'<(?:video|img|iframe)\b')
        javascript = (ROOT / 'app/static/pricing.js').read_text(encoding='utf-8')
        self.assertNotIn('fetch(', javascript)
        self.assertNotIn('.load(', javascript)
        self.assertLess(len(javascript.encode()), 7000)


EXPECTED = {
    'monthly': ['$400/month', '$650/month', '$900/month'],
    'creative': ['$250', 'Starting at $250', 'Starting at $350', 'Starting at $400', 'Starting at $350', 'Starting at $500', 'Starting at $150', 'Starting at $100'],
    'music': ['Starting at $600', 'Starting at $1,000', 'Starting at $1,500'],
    'weddings': ['Starting at $750', 'Starting at $1,200'],
    'birthday': ['Starting at $500', 'Starting at $400', 'Starting at $800', 'Starting at $250'],
    'property': ['Starting at $250', 'Starting at $300', 'Starting at $450', 'Starting at $250', 'Starting at $150'],
    'web': ['$750 setup + $49/month', '$1,200 setup + $79/month', 'Starting at $1,800 setup + Starting at $129/month'],
    'bots': ['$300 setup + $79/month', '$500 setup + $149/month', 'Starting at $800 setup + Starting at $249/month'],
}


def category_test(category, expected):
    def test(self):
        section = next(s for s in pricing_view(self.knowledge) if s['id'] == category)
        self.assertEqual([offer['display_price'] for offer in section['offers']], expected)
    return test


for category, expected in EXPECTED.items():
    setattr(PricingTest, 'test_approved_prices_' + category, category_test(category, expected))
