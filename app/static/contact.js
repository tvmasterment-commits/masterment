(() => {
  const form = document.querySelector('#direct-contact');
  if (!form) return;
  const button = form.querySelector('button');
  const status = form.querySelector('.direct-contact-status');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (button.disabled || !form.reportValidity()) return;
    const fields = Object.fromEntries(new FormData(form));
    for (const [name, value] of Object.entries(fields)) {
      if (!value.trim()) {
        status.textContent = `Please enter your ${name}.`;
        form.elements.namedItem(name).focus();
        return;
      }
    }
    button.disabled = true;
    form.setAttribute('aria-busy', 'true');
    status.textContent = 'Sending…';
    try {
      const response = await fetch(form.action, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Unable to send. Please try again.');
      form.reset();
      status.textContent = result.message;
    } catch (error) {
      status.textContent = error.message === 'Failed to fetch'
        ? 'Connection unavailable. Please try again.' : error.message;
    } finally {
      button.disabled = false;
      form.removeAttribute('aria-busy');
    }
  });
})();
