(() => {
  const form = document.querySelector('#chat-form');
  const input = document.querySelector('#chat-input');
  const messages = document.querySelector('#messages');
  const typing = document.querySelector('#typing');
  const sendButton = form.querySelector('button[type="submit"]');
  let conversationId = sessionStorage.getItem('masterment_conversation_id');

  function addMessage(role, text) {
    const article = document.createElement('article');
    article.className = `message ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    article.append(bubble);
    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  }

  if (conversationId) {
    fetch(`/api/conversations/${encodeURIComponent(conversationId)}`)
      .then((response) => response.ok ? response.json() : null)
      .then((data) => {
        if (!data) {
          sessionStorage.removeItem('masterment_conversation_id');
          conversationId = null;
          return;
        }
        for (const item of data.messages) addMessage(item.role, item.content);
      })
      .catch(() => {});
  }

  document.querySelectorAll('[data-prompt]').forEach((button) => {
    button.addEventListener('click', () => {
      if (input.disabled) return;
      input.value = button.dataset.prompt;
      form.requestSubmit();
    });
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text || input.disabled) return;
    addMessage('user', text);
    input.value = '';
    input.style.height = 'auto';
    input.disabled = true;
    sendButton.disabled = true;
    form.classList.add('is-sending');
    typing.classList.add('visible');
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text, conversation_id: conversationId})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Please try again.');
      conversationId = data.conversation_id;
      sessionStorage.setItem('masterment_conversation_id', conversationId);
      addMessage('assistant', data.reply);
    } catch (error) {
      addMessage('assistant', 'We couldn’t send that just now. Please try again in a moment.');
    } finally {
      typing.classList.remove('visible');
      input.disabled = false;
      sendButton.disabled = false;
      form.classList.remove('is-sending');
      if (!window.matchMedia('(pointer: coarse)').matches) input.focus({preventScroll: true});
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
})();
