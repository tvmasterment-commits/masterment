"""Reproducible codec, decode and MP4 atom audit of deployed portfolio sources."""
import json
import struct
import subprocess
from pathlib import Path
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
ENCODER = imageio_ffmpeg.get_ffmpeg_exe()

def atoms(path):
    found = []
    with path.open('rb') as stream:
        while stream.tell() < path.stat().st_size:
            offset = stream.tell()
            header = stream.read(8)
            if len(header) != 8: break
            size, kind = struct.unpack('>I4s', header)
            if size == 1: size = struct.unpack('>Q', stream.read(8))[0]
            if size == 0: size = path.stat().st_size() - offset
            if size < 8: raise ValueError('Invalid atom')
            found.append({'type': kind.decode('ascii'), 'offset': offset, 'bytes': size})
            stream.seek(offset + size)
    return found

def audit():
    results = []
    for name in [f'reels-{i}' for i in range(1, 10)] + ['work-01', 'work-03']:
        directory = 'portfolio-web' if name in ['reels-1','reels-2','reels-3','reels-5','reels-9','work-01','work-03'] else 'reels'
        path = ROOT / 'app/static/videos' / directory / (name + '.mp4')
        probe = subprocess.run([ENCODER, '-hide_banner', '-i', str(path)], capture_output=True, text=True).stderr
        decode = subprocess.run([ENCODER, '-v', 'error', '-i', str(path), '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'], capture_output=True, text=True)
        info = atoms(path)
        atom_types = [a['type'] for a in info]
        result = {'name': name, 'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
                  'streams': [line.strip() for line in probe.splitlines() if 'Stream #' in line],
                  'atoms': info, 'faststart': atom_types.index('moov') < atom_types.index('mdat'),
                  'decode_ok': decode.returncode == 0 and not decode.stderr.strip(), 'decode_errors': decode.stderr[:1000]}
        original_dir = 'work' if name.startswith('work') else 'reels'
        extension = '.MP4' if name in ['reels-1','reels-2','reels-3','reels-5','reels-9'] else '.mp4'
        original = ROOT / 'app/static/videos' / original_dir / (name + extension)
        original_atoms = [a['type'] for a in atoms(original)]
        result['original_path'] = str(original.relative_to(ROOT))
        result['original_faststart'] = original_atoms.index('moov') < original_atoms.index('mdat')
        results.append(result)
    output = ROOT / '.performance-verification/portfolio-codecs.json'
    output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps([{k:r[k] for k in ('name','streams','faststart','decode_ok')} for r in results], indent=2))
    if not all(r['decode_ok'] and r['faststart'] for r in results): raise SystemExit(1)

if __name__ == '__main__': audit()
