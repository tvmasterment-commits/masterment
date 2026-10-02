"""Local asset build: pip install pillow imageio-ffmpeg (development only).

Originals are retained. Video dimensions, frame rate and full duration are retained.
"""
from pathlib import Path
import subprocess
from PIL import Image
import imageio_ffmpeg

root = Path(__file__).resolve().parents[1] / 'app' / 'static'
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

def run(*args):
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)], check=True)

logo = Image.open(root / 'images/masterment-logo.png')
for size in (336, 1254):
    image = logo.copy()
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    image.save(root / f'images/masterment-logo-{size}.webp', lossless=True, method=6)
for source in (root / 'images/partner-logos').glob('*.png'):
    image = Image.open(source)
    image.thumbnail((420, 195), Image.Resampling.LANCZOS)
    image.save(source.with_suffix('.webp'), lossless=True, method=6)

run('-i', root / 'videos/hero-showreel.mp4', '-map', '0:v:0', '-c:v', 'libx264',
    '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    root / 'videos/hero-showreel-web.mp4')
posters = root / 'images/posters'
posters.mkdir(exist_ok=True)
for source, second, width, name in [
    (root / 'videos/hero-showreel.mp4', 0, 1920, 'hero'),
    *[(p, 0, 720, p.stem) for p in (root / 'videos/reels').iterdir()],
    (root / 'videos/work/work-01.mp4', 20, 1280, 'work-01'),
    (root / 'videos/work/work-03.mp4', 25, 1280, 'work-03'),
]:
    run('-ss', second, '-i', source, '-frames:v', 1, '-vf', f'scale={width}:-2',
        '-c:v', 'libwebp', '-quality', '92', posters / f'{name}.webp')
