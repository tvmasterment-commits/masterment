import json
import os
import re
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from app import create_app
from app.seo import SOCIAL_PROFILES


class SEOTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = Path(__file__).parent / ('seo-' + uuid.uuid4().hex + '.sqlite3')
        with patch.dict(os.environ, {'APP_ENV': 'development', 'OPENAI_API_KEY': ''}):
            cls.app = create_app({'TESTING': True, 'DATABASE_PATH': str(cls.database),
                                  'GOOGLE_SITE_VERIFICATION': ''})
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.database.unlink(missing_ok=True)

    def test_metadata_and_host_independent_canonical(self):
        response = self.client.get('/?campaign=test', base_url='http://untrusted.example')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertEqual(page.count('rel="canonical"'), 1)
        self.assertIn('href="https://masterment.services/"', page)
        self.assertNotIn('untrusted.example', page)
        for term in ('Masterment LLC', 'Massachusetts', 'Rhode Island', 'Boston',
                     'photography and music video production'):
            self.assertIn(term, page)
        for field in ('og:title', 'og:description', 'og:url', 'og:image', 'twitter:card'):
            self.assertIn(field, page)
        self.assertNotIn('google-site-verification', page)
        image = self.client.get('/static/images/posters/hero.webp')
        self.assertEqual(image.status_code, 200)
        image.close()

    def test_structured_data_uses_existing_profiles_without_unverified_facts(self):
        page = self.client.get('/').get_data(as_text=True)
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)[1])
        self.assertEqual(data['@type'], 'Organization')
        self.assertEqual(data['sameAs'], SOCIAL_PROFILES)
        self.assertEqual(data['name'], 'Masterment LLC')
        for key in ('address', 'telephone', 'review', 'aggregateRating', 'openingHours'):
            self.assertNotIn(key, data)
        self.assertNotIn('LocalBusiness', page)
        for profile in SOCIAL_PROFILES:
            self.assertIn(profile.rstrip('/'), page)

    def test_sitemap_and_robots(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.mimetype, 'application/xml')
        root = ElementTree.fromstring(response.data)
        locations = root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
        self.assertEqual([item.text for item in locations], ['https://masterment.services/'])
        robots = self.client.get('/robots.txt')
        self.assertEqual(robots.mimetype, 'text/plain')
        self.assertIn('Sitemap: https://masterment.services/sitemap.xml', robots.text)
        self.assertNotIn('Disallow: /\n', robots.text)

    def test_private_and_error_responses_are_not_indexable(self):
        for path in ('/admin', '/admin/leads/1', '/api/chat/session', '/health', '/missing'):
            self.assertEqual(self.client.get(path).headers['X-Robots-Tag'], 'noindex, nofollow')
        self.assertNotIn('X-Robots-Tag', self.client.get('/').headers)

    def test_verification_token_is_optional_and_escaped(self):
        try:
            self.app.config['GOOGLE_SITE_VERIFICATION'] = 'real-token"><script>'
            page = self.client.get('/').text
            self.assertIn('content="real-token&#34;&gt;&lt;script&gt;"', page)
        finally:
            self.app.config['GOOGLE_SITE_VERIFICATION'] = ''
