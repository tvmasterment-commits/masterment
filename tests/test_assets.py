import gzip
import html
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.assets import configure_assets
from flask import Flask, url_for


class AssetTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        with patch.dict(os.environ, {'APP_ENV': 'development'}):
            self.app = create_app({'TESTING': True, 'DATABASE_PATH': str(Path(self.directory.name) / 'test.db')})
        self.client = self.app.test_client()

    def test_versioned_assets_cache_and_unversioned_revalidate(self):
        page = self.client.get('/').get_data(as_text=True)
        url = html.unescape(re.search(r'href="([^"]*customer.css[^"]*)"', page)[1])
        for target, expected in [(url, 'public, max-age=31536000, immutable'), ('/static/customer.css', 'no-cache'), ('/static/customer.css?v=old', 'no-cache')]:
            with self.client.get(target) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['Cache-Control'], expected)

    def test_gzip_negotiation_and_conditional_requests(self):
        for target in ('/', '/static/customer.css', '/static/customer.js'):
            with self.client.get(target) as plain, self.client.get(target, headers={'Accept-Encoding': 'gzip'}) as zipped:
                self.assertEqual(gzip.decompress(zipped.data), plain.data)
                self.assertLess(len(zipped.data), len(plain.data))
                self.assertIn('Accept-Encoding', zipped.headers['Vary'])
                etag = zipped.headers['ETag']
            with self.client.get(target, headers={'Accept-Encoding': 'gzip', 'If-None-Match': etag}) as unchanged:
                self.assertEqual(unchanged.status_code, 304)
            with self.client.get(target, headers={'Accept-Encoding': 'gzip;q=0'}) as declined:
                self.assertNotIn('Content-Encoding', declined.headers)

    def test_video_ranges_are_preserved(self):
        with self.client.get('/static/videos/hero-showreel-web.mp4', headers={'Range': 'bytes=0-1023', 'Accept-Encoding': 'gzip'}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(len(response.data), 1024)
            self.assertNotIn('Content-Encoding', response.headers)

    def test_deployment_content_change_busts_cache(self):
        directory = Path(self.directory.name) / 'static'
        directory.mkdir()
        css = directory / 'site.css'
        versions = []
        for content in ('body {color: red}', 'body {color: blue}'):
            css.write_text(content)
            app = Flask('asset-fixture', static_folder=str(directory))
            configure_assets(app)
            with app.test_request_context('/'):
                versions.append(url_for('static', filename='site.css', v='legacy'))
        self.assertNotEqual(versions[0], versions[1])
        with app.test_client().get(versions[0]) as stale:
            self.assertEqual(stale.headers['Cache-Control'], 'no-cache')

    def test_deferred_media_paths_exist_with_exact_case(self):
        page = self.client.get('/').get_data(as_text=True)
        urls = re.findall(r'data-(?:src|poster|partner-src)="/static/([^?]+)', page)
        self.assertEqual(len(urls), 45)
        for filename in urls:
            path = Path(self.app.static_folder) / filename
            self.assertIn(path.name, [p.name for p in path.parent.iterdir()])
