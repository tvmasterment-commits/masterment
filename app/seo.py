"""Public search metadata, independent of request hosts and private CRM data."""
from flask import Blueprint, Response, current_app, request

bp = Blueprint('seo', __name__)
SITE_URL = 'https://masterment.services'
TITLE = 'Masterment LLC | Video Production Massachusetts & Rhode Island'
DESCRIPTION = ('Masterment LLC offers video production in Massachusetts and Rhode Island, '
               'plus photography, music video production and creative agency services for Boston projects.')
# Existing owner-maintained homepage footer is the source for these identities.
SOCIAL_PROFILES = [
    'https://youtube.com/@masterment',
    'https://www.instagram.com/master_ment/',
    'https://open.spotify.com/artist/1JDtKFhM3tOV4r0b9w0ApB',
    'https://music.apple.com/us/artist/masterment/1650869578',
]


@bp.app_context_processor
def metadata():
    return {'seo': {
        'title': TITLE, 'description': DESCRIPTION, 'canonical': SITE_URL + '/',
        'image': SITE_URL + '/static/images/posters/hero.webp',
        'verification': current_app.config.get('GOOGLE_SITE_VERIFICATION', ''),
        'organization': {
            '@context': 'https://schema.org', '@type': 'Organization',
            '@id': SITE_URL + '/#organization', 'name': 'Masterment LLC',
            'url': SITE_URL + '/',
            'logo': SITE_URL + '/static/images/masterment-logo-1254.webp',
            'description': DESCRIPTION, 'sameAs': SOCIAL_PROFILES,
        },
    }}


@bp.get('/sitemap.xml')
def sitemap():
    # Only the homepage is a public indexable page; anchors are not separate URLs.
    return Response('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    '<url><loc>' + SITE_URL + '/</loc></url></urlset>\n',
                    mimetype='application/xml')


@bp.get('/robots.txt')
def robots():
    # Private endpoints stay crawlable so crawlers can see the noindex header.
    return Response('User-agent: *\nAllow: /\n\nSitemap: ' + SITE_URL + '/sitemap.xml\n',
                    mimetype='text/plain')


@bp.after_app_request
def indexing_policy(response):
    if (request.path == '/admin' or request.path.startswith('/admin/')
            or request.path == '/api' or request.path.startswith('/api/')
            or request.path == '/health' or response.status_code >= 400):
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response
