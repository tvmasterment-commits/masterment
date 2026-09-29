(() => {
  const videos = [...document.querySelectorAll('.reels-video')];
  if (!videos.length) return;
  const nearby = new Set();
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
    const source = video.querySelector('source[data-src]');
    if (source && !source.hasAttribute('src')) {
      source.src = source.dataset.src;
      video.load();
    }
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
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => setNear(entry.target, entry.isIntersecting));
    }, { rootMargin: '200px 0px', threshold: 0 });
    videos.forEach((video) => observer.observe(video));
  } else {
    let scheduled = false;
    const check = () => {
      scheduled = false;
      videos.forEach((video) => {
        const rect = video.getBoundingClientRect();
        setNear(video, rect.bottom >= -200 && rect.top <= window.innerHeight + 200);
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
