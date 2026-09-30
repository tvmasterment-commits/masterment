(() => {
  const dialog = document.querySelector('#pricing-dialog');
  const triggers = document.querySelectorAll('.pricing-trigger, .services-pricing-trigger');
  if (!dialog || !triggers.length) return;
  let trigger = triggers[0];
  const scroller = dialog.querySelector('.pricing-scroll');
  let savedScroll = 0;
  let savedStyles;
  let afterClose;
  let previousSelection = '';

  function openPricing(event) {
    if (dialog.open) return;
    trigger = event.currentTarget;
    savedScroll = window.scrollY;
    savedStyles = ['position', 'top', 'width', 'overflow', 'paddingRight'].map(key => [key, document.body.style[key]]);
    const gutter = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.position = 'fixed';
    document.body.style.top = `-${savedScroll}px`;
    document.body.style.width = '100%';
    document.body.style.overflow = 'hidden';
    if (gutter) document.body.style.paddingRight = `${gutter}px`;
    dialog.showModal();
    scroller.scrollTop = 0;
    dialog.querySelector('.pricing-close').focus({preventScroll: true});
  }

  function closePricing(callback) {
    afterClose = typeof callback === 'function' ? callback : null;
    dialog.close();
  }

  dialog.addEventListener('close', () => {
    for (const [key, value] of savedStyles || []) document.body.style[key] = value;
    const behavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = 'auto';
    window.scrollTo(0, savedScroll);
    document.documentElement.style.scrollBehavior = behavior;
    trigger.focus({preventScroll: true});
    const callback = afterClose;
    afterClose = null;
    callback?.();
  });
  dialog.addEventListener('cancel', event => {
    event.preventDefault();
    closePricing();
  });
  dialog.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const controls = [...dialog.querySelectorAll('button, a[href], summary, [tabindex="0"]')]
      .filter(element => !element.disabled && element.getClientRects().length);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
  triggers.forEach(button => button.addEventListener('click', openPricing));
  dialog.querySelector('.pricing-close').addEventListener('click', () => closePricing());
  dialog.querySelectorAll('.pricing-index a').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    const section = dialog.querySelector(link.getAttribute('href'));
    scroller.scrollTo({top: section.offsetTop - scroller.offsetTop - 22, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  }));

  function startProject(button) {
    const message = document.querySelector('#contact-message');
    if (button?.dataset.pricingSelection && message) {
      const selection = `Selected service/package: ${button.dataset.pricingSelection}\nDisplayed price: ${button.dataset.pricingPrice}`;
      // Preserve a visitor's draft and replace only our own previous prefix.
      const draft = previousSelection && message.value.startsWith(previousSelection)
        ? message.value.slice(previousSelection.length).replace(/^\n\n/, '') : message.value;
      const combined = `${selection}\n\n${draft}`;
      if (combined.length <= message.maxLength) {
        message.value = combined;
        previousSelection = selection;
        message.dispatchEvent(new Event('input', {bubbles: true}));
      }
    }
    closePricing(() => {
      const menu = document.querySelector('#menu-toggle');
      if (menu?.getAttribute('aria-expanded') === 'true') menu.click();
      document.querySelector('#contact').scrollIntoView({behavior: 'instant', block: 'start'});
      (message || document.querySelector('#contact-name'))?.focus({preventScroll: true});
    });
  }
  dialog.querySelectorAll('[data-pricing-selection]').forEach(button => button.addEventListener('click', () => startProject(button)));
  dialog.querySelector('.pricing-project').addEventListener('click', event => {
    event.preventDefault();
    startProject();
  });
  dialog.querySelector('.pricing-ask').addEventListener('click', () => closePricing(() => {
    const toggle = document.querySelector('#chat-widget .chat-toggle');
    const panel = document.querySelector('#chat-panel');
    if (panel?.hidden) toggle?.click();
    else panel?.focus({preventScroll: true});
  }));
})();
