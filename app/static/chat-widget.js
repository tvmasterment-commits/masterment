(() => {
  const widget = document.querySelector('#chat-widget');
  if (!widget) return;
  const panel = widget.querySelector('#chat-panel');
  const toggle = widget.querySelector('.chat-toggle');
  const close = widget.querySelector('.chat-close');
  const messages = widget.querySelector('#messages');
  const viewport = window.visualViewport;

  function syncViewport() {
    const height = viewport?.height || window.innerHeight;
    const bottom = Math.max(0, window.innerHeight - height - (viewport?.offsetTop || 0));
    widget.style.setProperty('--chat-viewport-height', `${height}px`);
    widget.style.setProperty('--chat-keyboard-offset', `${bottom}px`);
    widget.classList.toggle('chat-compact', height < 540);
  }

  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Minimize Masterment chat' : 'Open Masterment chat');
    syncViewport();
    if (open) {
      messages.scrollTop = messages.scrollHeight;
      panel.focus({preventScroll: true});
    } else {
      toggle.focus({preventScroll: true});
    }
  }

  toggle.addEventListener('click', () => setOpen(panel.hidden));
  close.addEventListener('click', () => setOpen(false));
  widget.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) {
      event.preventDefault();
      setOpen(false);
    }
  });
  window.addEventListener('resize', syncViewport, {passive: true});
  viewport?.addEventListener('resize', syncViewport, {passive: true});
  viewport?.addEventListener('scroll', syncViewport, {passive: true});
  syncViewport();
})();
