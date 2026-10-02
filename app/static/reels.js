(() => {
  const videos = [...document.querySelectorAll('.reels-video')];
  if (!videos.length) return;
  const nearby = new Set();
  const prepare = (video) => {
    if (video.dataset.poster && !video.poster) video.poster = video.dataset.poster;
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    const source = video.querySelector('source[data-src]');
    if (source && !source.hasAttribute('src')) {
      video.preload = 'metadata';
      source.src = source.dataset.src;
      video.load();
    }
  };
  const shouldPlay = (video) => nearby.has(video) && !document.hidden;
  const sync = (video) => {
    if (!shouldPlay(video)) {
      video.autoplay = false;
      video.pause();
      return;
    }
    // Set the Safari properties before assigning a source or requesting playback.
    video.muted = true;
    video.defaultMuted = true;
    video.playsInline = true;
    video.autoplay = true;
    prepare(video);
    const playback = video.play();
    playback?.then(() => {
      // A pending play request may resolve after the Reel leaves the viewport.
      if (!shouldPlay(video)) video.pause();
    }).catch(() => {});
  };
  videos.forEach((video) => {
    video.autoplay = false;
    video.addEventListener('canplay', () => sync(video));
    video.addEventListener('playing', () => {
      if (!shouldPlay(video)) video.pause();
    });
  });
  const setNear = (video, isNear) => {
    if (isNear) nearby.add(video);
    else nearby.delete(video);
    sync(video);
  };
  if ('IntersectionObserver' in window) {
    const preparation = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        prepare(entry.target);
        preparation.unobserve(entry.target);
      });
    }, { rootMargin: '120px 0px', threshold: 0 });
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => setNear(entry.target, entry.isIntersecting));
    }, { threshold: 0 });
    videos.forEach((video) => { preparation.observe(video); observer.observe(video); });
  } else {
    let scheduled = false;
    const check = () => {
      scheduled = false;
      videos.forEach((video) => {
        const rect = video.getBoundingClientRect();
        if (rect.bottom >= -120 && rect.top <= window.innerHeight + 120) prepare(video);
        setNear(video, rect.bottom > 0 && rect.top < window.innerHeight);
      });
    };
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      window.requestAnimationFrame(check);
    };
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule, { passive: true });
    check();
  }
  document.addEventListener('visibilitychange', () => videos.forEach(sync));
  window.addEventListener('pagehide', () => videos.forEach((video) => video.pause()));
  window.addEventListener('pageshow', () => videos.forEach(sync));
})();
