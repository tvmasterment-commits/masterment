(() => {
  const videos = [...document.querySelectorAll('.reels-video, .project-video')];
  if (!videos.length) return;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const highlights = {'work-01': [20, 32], 'work-03': [25, 37]};
  const visible = new Set();
  const waiting = new Set();
  let starting = null;
  let timer = null;
  let suspended = false;
  const isProject = video => video.classList.contains('project-video');
  const allowed = video => visible.has(video) && !document.hidden && !suspended && !(isProject(video) && motion.matches);
  const poster = video => {
    const image = video.parentElement.querySelector('.portfolio-poster');
    if (image && !image.hasAttribute('src')) image.src = image.dataset.src;
    if (!video.poster) video.poster = video.dataset.poster;
  };
  const finish = video => {
    if (starting !== video) return;
    clearTimeout(timer);
    starting = null;
    pump();
  };
  const play = video => {
    if (!allowed(video)) return;
    video.play()?.then(() => { if (!allowed(video)) video.pause(); }).catch(() => finish(video));
  };
  const start = video => {
    starting = video;
    poster(video);
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.autoplay = false;
    video.preload = 'auto';
    const source = video.querySelector('source[data-src]');
    if (!source.hasAttribute('src')) { source.src = source.dataset.src; video.load(); }
    timer = setTimeout(() => finish(video), 8000);
    play(video);
  };
  function pump() {
    if (starting || document.hidden || suspended) return;
    const next = [...waiting].filter(allowed).sort((a,b) => Math.abs(a.getBoundingClientRect().top) - Math.abs(b.getBoundingClientRect().top))[0];
    if (next) { waiting.delete(next); start(next); }
  }
  const sync = video => {
    if (!allowed(video)) {
      waiting.delete(video);
      video.pause();
      finish(video);
      return;
    }
    if (video.currentSrc && video.readyState >= 2) play(video);
    else if (starting !== video) waiting.add(video);
    pump();
  };
  videos.forEach(video => {
    video.autoplay = false;
    video.addEventListener('loadedmetadata', () => {
      const id = video.querySelector('source').dataset.src.match(/work-0[13]/)?.[0];
      const range = highlights[id];
      if (range) {
        const start = range[0] < video.duration ? range[0] : 0;
        video.dataset.highlightStart = String(start);
        video.dataset.highlightEnd = String(Math.min(range[1], video.duration));
        video.currentTime = start;
      } else if (video.dataset.resumeAt) video.currentTime = Math.min(Number(video.dataset.resumeAt), Math.max(0,video.duration - .1));
    });
    video.addEventListener('canplay', () => play(video));
    video.addEventListener('playing', () => {
      if (!allowed(video)) { video.pause(); return; }
      video.parentElement.classList.add('portfolio-playing');
      finish(video);
    });
    video.addEventListener('timeupdate', () => {
      if (!isProject(video)) return;
      const end = Number(video.dataset.highlightEnd);
      if (end && video.currentTime >= end) { video.currentTime = Number(video.dataset.highlightStart); play(video); }
    });
    video.addEventListener('error', () => {
      video.parentElement.classList.remove('portfolio-playing');
      const fallback = video.parentElement.querySelector('.project-video-fallback');
      if (fallback) fallback.hidden = false;
      finish(video);
    });
  });
  const update = () => {
    videos.forEach(video => {
      const bounds = video.getBoundingClientRect();
      if (bounds.bottom >= -600 && bounds.top <= innerHeight + 600) poster(video);
      if (bounds.bottom > 0 && bounds.top < innerHeight) visible.add(video);
      else visible.delete(video);
    });
    videos.forEach(video => {
      const bounds = video.getBoundingClientRect();
      if (bounds.bottom < -600 || bounds.top > innerHeight + 600) {
        const source = video.querySelector('source');
        if (source.hasAttribute('src')) {
          video.dataset.resumeAt = String(video.currentTime);
          video.pause();
          source.removeAttribute('src');
          video.load(); // Cancel distant buffering; the separate poster remains visible.
          video.parentElement.classList.remove('portfolio-playing');
        }
      }
      sync(video);
    });
  };
  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; update(); });
  };
  if ('IntersectionObserver' in window) {
    const preparation = new IntersectionObserver(schedule, {rootMargin:'600px 0px'});
    const playback = new IntersectionObserver(schedule);
    videos.forEach(video => { preparation.observe(video); playback.observe(video); });
  }
  // Also handles browsers without IntersectionObserver and cancellation far offscreen.
  addEventListener('scroll',schedule,{passive:true});
  addEventListener('resize',schedule,{passive:true});
  document.addEventListener('visibilitychange',schedule);
  motion.addEventListener?.('change',schedule);
  addEventListener('pagehide',() => {suspended=true; videos.forEach(video=>video.pause());});
  addEventListener('pageshow',() => {suspended=false;schedule();});
  update();
})();
