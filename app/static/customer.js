(() => {
  // TEMPORARY preview ranges in seconds; replace these after selecting final highlights.
  const portfolioHighlights = {
    'work-01': {start: 20, end: 32},
    'work-02': {start: 15, end: 27},
    'work-03': {start: 25, end: 37},
  };
  const heroVideo = document.querySelector('.hero-video');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  // Edit partner names and paths here when the logo set changes.
  const partnerLogos = [
    {name: 'AweSound', path: '/static/images/partner-logos/partner-1.webp', width: 420, height: 151},
    {name: 'Outside Films', path: '/static/images/partner-logos/partner-2.webp', width: 419, height: 195},
    {name: 'Katxito Nation', path: '/static/images/partner-logos/partner-3.webp', width: 420, height: 195},
    {name: 'MB', path: '/static/images/partner-logos/partner-4.webp', width: 201, height: 195},
    {name: 'Dira Ricky', path: '/static/images/partner-logos/partner-5.webp', width: 420, height: 138},
    {name: 'Kriol Spirit', path: '/static/images/partner-logos/partner-6.webp', width: 420, height: 142},
    {name: 'ND', path: '/static/images/partner-logos/partner-7.webp', width: 292, height: 195},
    {name: 'CH Films', path: '/static/images/partner-logos/partner-8.webp', width: 340, height: 195},
    {name: 'Rootz Madrugz', path: '/static/images/partner-logos/partner-9.webp', width: 420, height: 166},
    {name: 'DJ Maks', path: '/static/images/partner-logos/partner-10.webp', width: 203, height: 195},
    {name: 'Partner 11', path: '/static/images/partner-logos/partner-11.webp', width: 366, height: 195},
    {name: 'Partner 12', path: '/static/images/partner-logos/partner-12.webp', width: 292, height: 195},
  ];
  if (heroVideo) {
    const syncHeroMotion = () => {
      if (reducedMotion.matches) {
        heroVideo.pause();
      } else if (heroVideo.paused) {
        heroVideo.play().catch(() => {});
      }
    };
    syncHeroMotion();
    reducedMotion.addEventListener?.('change', syncHeroMotion);
  }
  const toggle = document.querySelector('#menu-toggle');
  const nav = document.querySelector('#site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!open));
      toggle.setAttribute('aria-label', open ? 'Open navigation' : 'Close navigation');
      nav.classList.toggle('is-open', !open);
    });
    nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open navigation');
      nav.classList.remove('is-open');
    }));
  }

  const partnerMarquee = document.querySelector('.about-partner-marquee');
  const partnerTrack = partnerMarquee?.querySelector('.about-partner-track');
  if (partnerMarquee && partnerTrack && partnerLogos.length) {
    // Build fixed-size frames immediately; native lazy loading defers offscreen images.
    const sources = [...partnerMarquee.querySelectorAll('[data-partner-src]')];
    Promise.resolve(partnerLogos.map((logo, index) => ({...logo, src: sources[index]?.dataset.partnerSrc || logo.path}))).then((results) => {
      const availableLogos = results.filter(Boolean);
      if (!availableLogos.length) return;

      const makeSequence = (
        isAccessible,
        sequenceClass = 'about-partner-sequence',
        frameClass = 'about-partner-frame',
        logos = availableLogos,
      ) => {
        const sequence = document.createElement('div');
        sequence.className = sequenceClass;
        if (!isAccessible) sequence.setAttribute('aria-hidden', 'true');
        logos.forEach((logo) => {
          const frame = document.createElement('span');
          frame.className = frameClass;
          const image = document.createElement('img');
          image.loading = 'lazy';
          image.decoding = 'async';
          image.width = logo.width;
          image.height = logo.height;
          image.src = logo.src;
          image.alt = isAccessible ? logo.name : '';
          image.draggable = false;
          frame.append(image);
          sequence.append(frame);
        });
        return sequence;
      };

      const mobilePartners = document.createElement('div');
      mobilePartners.className = 'about-partner-mobile';
      mobilePartners.setAttribute('role', 'region');
      mobilePartners.setAttribute('aria-label', 'Partner logos');
      const halfway = Math.ceil(availableLogos.length / 2);
      const rowOneLogos = availableLogos.slice(0, halfway);
      const rotatedLogos = [...availableLogos.slice(halfway), ...availableLogos.slice(0, halfway)];
      const rowTwoLogos = rotatedLogos.slice(0, availableLogos.length - halfway);
      ['left', 'right'].forEach((direction, index) => {
        const marquee = document.createElement('div');
        marquee.className = 'mobile-marquee';
        if (index > 0) marquee.setAttribute('aria-hidden', 'true');
        const track = document.createElement('div');
        track.className = `mobile-marquee-track mobile-marquee-${direction}`;
        const rowLogos = index === 0 ? rowOneLogos : rowTwoLogos;
        track.append(
          makeSequence(index === 0, 'mobile-marquee-group', 'mobile-partner-logo', rowLogos),
          makeSequence(false, 'mobile-marquee-group', 'mobile-partner-logo', rowLogos),
        );
        marquee.append(track);
        mobilePartners.append(marquee);
      });
      partnerMarquee.insertAdjacentElement('afterend', mobilePartners);

      let lastWidth = 0;
      const rebuildTrack = () => {
        const viewportWidth = partnerMarquee.clientWidth;
        if (!viewportWidth || viewportWidth === lastWidth) return;
        lastWidth = viewportWidth;
        partnerTrack.replaceChildren();
        const firstSet = document.createElement('div');
        firstSet.className = 'about-partner-set';
        firstSet.append(makeSequence(true));
        partnerTrack.append(firstSet);
        const oneSequenceWidth = firstSet.getBoundingClientRect().width;
        const sequenceCount = Math.max(1, Math.ceil(viewportWidth / oneSequenceWidth));
        for (let index = 1; index < sequenceCount; index += 1) {
          firstSet.append(makeSequence(false));
        }
        const secondSet = firstSet.cloneNode(true);
        secondSet.setAttribute('aria-hidden', 'true');
        partnerTrack.append(secondSet);
        partnerTrack.style.setProperty('--about-partner-distance', `${firstSet.getBoundingClientRect().width}px`);
        partnerMarquee.hidden = false;
      };
      partnerMarquee.hidden = false;
      rebuildTrack();
      window.addEventListener('resize', rebuildTrack, {passive: true});
      if ('ResizeObserver' in window) new ResizeObserver(rebuildTrack).observe(partnerMarquee);
    });
  }

  const items = document.querySelectorAll('.reveal');
  const projectVideos = [...document.querySelectorAll('.project-video')];
  const nearbyProjectVideos = new Set();
  const projectHighlight = (video) => {
    const source = video.querySelector('source[data-src], source[src]');
    const filename = source?.dataset.src || source?.getAttribute('src') || '';
    const projectId = filename.match(/work-0[1-3]/)?.[0];
    return portfolioHighlights[projectId];
  };
  const seekProjectHighlight = (video) => {
    if (video.readyState < HTMLMediaElement.HAVE_METADATA || !Number.isFinite(video.duration)) return;
    const highlight = projectHighlight(video);
    if (!highlight || video.duration <= 0) return;
    let start = Math.min(Math.max(0, highlight.start), video.duration);
    let end = Math.min(Math.max(0, highlight.end), video.duration);
    if (end <= start) {
      start = 0;
      end = video.duration;
    }
    video.dataset.highlightStart = String(start);
    video.dataset.highlightEnd = String(end);
    if (video.currentTime < start || video.currentTime >= end) video.currentTime = start;
  };
  const loadProjectVideo = (video) => {
    if (video.dataset.poster && !video.poster) video.poster = video.dataset.poster;
    const source = video.querySelector('source[data-src]');
    if (source && !source.hasAttribute('src')) {
      video.preload = 'metadata';
      source.src = source.dataset.src;
      video.load();
    }
  };
  const setProjectVideoNear = (video, isNear) => {
    if (isNear) {
      nearbyProjectVideos.add(video);
      video.autoplay = !reducedMotion.matches && !document.hidden;
      loadProjectVideo(video);
      if (reducedMotion.matches || document.hidden || video.error) video.pause();
      else {
        seekProjectHighlight(video);
        video.play().catch(() => {});
      }
    } else {
      nearbyProjectVideos.delete(video);
      video.autoplay = false;
      video.pause();
    }
  };
  projectVideos.forEach((video) => {
    video.autoplay = false;
    video.addEventListener('playing', () => {
      if (!nearbyProjectVideos.has(video) || reducedMotion.matches || document.hidden) video.pause();
    });
    const art = video.closest('.portfolio-art');
    const fallback = art?.querySelector('.project-video-fallback');
    const showFallback = () => {
      art?.classList.add('video-unavailable');
      if (fallback) fallback.hidden = false;
    };
    video.addEventListener('error', showFallback, { once: true });
    video.addEventListener('loadedmetadata', () => {
      seekProjectHighlight(video);
      if (nearbyProjectVideos.has(video) && !reducedMotion.matches && !document.hidden && !video.error) video.play().catch(() => {});
    });
    video.addEventListener('timeupdate', () => {
      const end = Number(video.dataset.highlightEnd);
      if (!Number.isFinite(end) || video.currentTime < end) return;
      const start = Number(video.dataset.highlightStart);
      video.currentTime = start;
      if (nearbyProjectVideos.has(video) && !reducedMotion.matches && !document.hidden && !video.error) video.play().catch(() => {});
    });
    if (video.error) showFallback();
  });
  if ('IntersectionObserver' in window) {
    const preparation = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        loadProjectVideo(entry.target);
        preparation.unobserve(entry.target);
      });
    }, {rootMargin: '120px 0px'});
    const videoObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => setProjectVideoNear(entry.target, entry.isIntersecting));
    });
    projectVideos.forEach((video) => { preparation.observe(video); videoObserver.observe(video); });
  } else {
    let videoCheckPending = false;
    const checkProjectVideoProximity = () => {
      videoCheckPending = false;
      projectVideos.forEach((video) => {
        const bounds = video.getBoundingClientRect();
        if (bounds.bottom >= -120 && bounds.top <= window.innerHeight + 120) loadProjectVideo(video);
        setProjectVideoNear(video, bounds.bottom > 0 && bounds.top < window.innerHeight);
      });
    };
    const scheduleProjectVideoCheck = () => {
      if (!videoCheckPending) {
        videoCheckPending = true;
        window.requestAnimationFrame(checkProjectVideoProximity);
      }
    };
    window.addEventListener('scroll', scheduleProjectVideoCheck, {passive: true});
    window.addEventListener('resize', scheduleProjectVideoCheck, {passive: true});
    checkProjectVideoProximity();
  }
  reducedMotion.addEventListener?.('change', () => {
    projectVideos.forEach((video) => {
      if (nearbyProjectVideos.has(video)) setProjectVideoNear(video, true);
      else video.pause();
    });
  });
  document.addEventListener('visibilitychange', () => {
    projectVideos.forEach((video) => {
      if (nearbyProjectVideos.has(video)) setProjectVideoNear(video, true);
    });
  });
  window.addEventListener('pagehide', () => projectVideos.forEach((video) => video.pause()));
  window.addEventListener('pageshow', () => projectVideos.forEach((video) => {
    if (nearbyProjectVideos.has(video)) setProjectVideoNear(video, true);
  }));
  if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    items.forEach((item) => item.classList.add('is-visible'));
  } else {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, {threshold: 0.12});
    items.forEach((item) => observer.observe(item));
  }

  const navLinks = [...document.querySelectorAll('.site-nav a[href^="#"]')];
  const navTargets = navLinks
    .map((link) => ({link, section: document.querySelector(link.getAttribute('href'))}))
    .filter((item) => item.section);
  if ('IntersectionObserver' in window && navTargets.length) {
    const navObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        navTargets.forEach(({link, section}) => {
          if (section === entry.target) link.setAttribute('aria-current', 'location');
          else link.removeAttribute('aria-current');
        });
      });
    }, {rootMargin: '-36% 0px -58% 0px'});
    navTargets.forEach(({section}) => navObserver.observe(section));
  }
})();
