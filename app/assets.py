"""Content-versioned static URLs; originals and unversioned URLs still revalidate."""
import hashlib
import gzip
from pathlib import Path

from flask import request


def configure_assets(app):
    # Compute once per process, never hash large videos during homepage requests.
    versions = {}
    compressed = {}
    for path in Path(app.static_folder).rglob('*'):
        if path.is_file():
            with path.open('rb') as source:
                versions[path.relative_to(app.static_folder).as_posix()] = hashlib.file_digest(source, 'sha256').hexdigest()[:16]
            if path.suffix in ('.css', '.js'):
                compressed[path.relative_to(app.static_folder).as_posix()] = gzip.compress(path.read_bytes(), mtime=0)

    @app.url_defaults
    def static_version(endpoint, values):
        if endpoint == 'static' and values.get('filename') in versions:
            values['v'] = versions[values['filename']]

    @app.after_request
    def static_cache(response):
        filename = (request.view_args or {}).get('filename')
        compressible = request.endpoint == 'main.home' or (request.endpoint == 'static' and filename in compressed)
        if compressible:
            response.vary.add('Accept-Encoding')
        if (compressible and request.method == 'GET' and response.status_code == 200
                and not request.headers.get('Range') and not response.headers.get('Content-Encoding')
                and request.accept_encodings.quality('gzip') > 0):
            response.direct_passthrough = False
            body = compressed[filename] if filename in compressed else gzip.compress(response.get_data(), mtime=0)
            original_body = response.response
            response.set_data(body)
            # send_file opened a file even when we use the precompressed copy.
            if hasattr(original_body, 'close'):
                original_body.close()
            response.headers['Content-Encoding'] = 'gzip'
            response.set_etag(hashlib.sha256(body).hexdigest())
            response.make_conditional(request)
        if request.endpoint == 'main.home':
            response.headers['Cache-Control'] = 'no-cache'
        if request.endpoint == 'static' and response.status_code in (200, 206, 304):
            version = versions.get(filename)
            if version and request.args.get('v') == version:
                response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
            else:
                response.headers['Cache-Control'] = 'no-cache'
        return response
