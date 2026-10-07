(() => {
  const form = document.querySelector('#chat-form');
  const input = document.querySelector('#chat-input');
  const messages = document.querySelector('#messages');
  const typing = document.querySelector('#typing');
  const typingText = typing.textContent;
  const sendButton = form.querySelector('button[type="submit"]');
  let conversationId = sessionStorage.getItem('masterment_conversation_id');
  // Establish server-owned identity before concurrent first-turn/history requests.
  const ready = fetch('/api/chat/session', {cache: 'no-store'}).then(response => {
    if (!response.ok) throw new Error('Session unavailable');
  });
  let pending = null;
  try { pending = JSON.parse(sessionStorage.getItem('masterment_pending_request')); } catch {}

  const displayedMessages = new Set();
  function addMessage(role, text, id) {
    if (id && displayedMessages.has(id)) return;
    if (id) displayedMessages.add(id);
    const article = document.createElement('article');
    article.className = `message ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    article.append(bubble);
    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  }

  let historyReady = ready;
  if (conversationId) {
    historyReady = ready.then(() => fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {cache: 'no-store'}))
      .then((response) => {
        if (response.status === 404) return null;
        if (!response.ok) throw new Error('History unavailable');
        return response.json();
      })
      .then((data) => {
        if (!data) {
          sessionStorage.removeItem('masterment_conversation_id');
          conversationId = null;
          pending = null;
          sessionStorage.removeItem('masterment_pending_request');
          return;
        }
        for (const item of data.messages) addMessage(item.role, item.content, item.id);
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
    input.disabled = true;
    sendButton.disabled = true;
    await historyReady;
    const retry = pending && pending.message === text;
    if (!retry) {
      pending = {message: text, conversation_id: conversationId, request_id: crypto.randomUUID()};
      sessionStorage.setItem('masterment_pending_request', JSON.stringify(pending));
      addMessage('user', text);
    }
    input.value = '';
    input.style.height = 'auto';
    input.disabled = true;
    sendButton.disabled = true;
    form.classList.add('is-sending');
    typing.textContent = typingText;
    typing.classList.add('visible');
    let failed = false;
    try {
      await ready;
      const send = () => fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(pending)
      });
      let response = await send();
      let data = await response.json();
      for (let attempt = 0; response.status === 202 && attempt < 30; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        response = await send();
        data = await response.json();
      }
      if (response.status === 202) throw new Error('Still processing');
      if (!response.ok) throw new Error(data.error || 'Please try again.');
      conversationId = data.conversation_id;
      sessionStorage.setItem('masterment_conversation_id', conversationId);
      if (!data.stale) addMessage('assistant', data.reply, data.assistant_message_id);
      pending = null;
      sessionStorage.removeItem('masterment_pending_request');
    } catch (error) {
      input.value = text;
      failed = true;
      typing.textContent = 'We couldn’t send that just now. Please try again in a moment.';
    } finally {
      if (!failed) typing.classList.remove('visible');
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
