"""Checkpoint B: lossless stream remux and lightweight source-frame posters."""
from pathlib import Path
import subprocess
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[1]/'app/static'
encoder=imageio_ffmpeg.get_ffmpeg_exe()
target=ROOT/'videos/portfolio-web'
posters=ROOT/'images/posters/portfolio'
target.mkdir(exist_ok=True)
posters.mkdir(exist_ok=True)
files=list((ROOT/'videos/reels').iterdir())+list((ROOT/'videos/work').iterdir())
for source in files:
    if source.stem in {'reels-1','reels-2','reels-3','reels-5','reels-9','work-01','work-03'}:
        subprocess.run([encoder,'-hide_banner','-loglevel','error','-y','-i',str(source),'-map','0:v:0','-map','0:a?',
                        '-c','copy','-movflags','+faststart',str(target/(source.stem+'.mp4'))],check=True)
    second={'work-01':20,'work-03':25}.get(source.stem,0)
    width=1280 if source.stem.startswith('work') else 540
    subprocess.run([encoder,'-hide_banner','-loglevel','error','-y','-ss',str(second),'-i',str(source),'-frames:v','1',
                    '-vf',f'scale={width}:-2','-c:v','libwebp','-quality','88',str(posters/(source.stem+'.webp'))],check=True)
