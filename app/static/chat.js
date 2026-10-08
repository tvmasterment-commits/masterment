(() => {
  const form = document.querySelector('#chat-form');
  const input = document.querySelector('#chat-input');
  const messages = document.querySelector('#messages');
  const typing = document.querySelector('#typing');
  const typingText = typing.textContent;
  const sendButton = form.querySelector('button[type="submit"]');
  const memoryStorage = new Map();
  const storage = {
    getItem(key) {try {return sessionStorage.getItem(key) || memoryStorage.get(key) || null;} catch {return memoryStorage.get(key) || null;}},
    setItem(key, value) {memoryStorage.set(key, value); try {sessionStorage.setItem(key, value);} catch {}},
    removeItem(key) {memoryStorage.delete(key); try {sessionStorage.removeItem(key);} catch {}}
  };
  function requestId() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  async function fetchWithTimeout(url, options = {}, timeout = 10000) {
    if (typeof AbortController === 'undefined') return fetch(url, options);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {return await fetch(url, {...options, signal: controller.signal});}
    finally {clearTimeout(timer);}
  }
  let conversationId = storage.getItem('masterment_conversation_id');
  // Establish server-owned identity before concurrent first-turn/history requests.
  let ready = null;
  function ensureReady() {
    if (!ready) {
      ready = fetchWithTimeout('/api/chat/session', {cache: 'no-store'}).then(response => {
        if (!response.ok) throw new Error('Session unavailable');
      }).catch(error => {
        ready = null;
        throw error;
      });
    }
    return ready;
  }
  let pending = null;
  try { pending = JSON.parse(storage.getItem('masterment_pending_request')); } catch {}
  if (pending && (typeof pending.message !== 'string' || typeof pending.request_id !== 'string')) pending = null;

  const displayedMessages = new Set();
  function addMessage(role, text, id) {
    if (id && displayedMessages.has(id)) return;
    if (id) displayedMessages.add(id);
    const article = document.createElement('article');
    article.className = `message ${role}`;
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    // Links are restricted to public portfolio locations; all labels remain text.
    const links = /https:\/\/(?:www\.youtube\.com\/watch\?v=[A-Za-z0-9_-]{11}|youtube\.com\/@masterment|masterment\.services\/#work)(?![A-Za-z0-9_/?&=-])/g;
    let offset = 0;
    for (const match of text.matchAll(links)) {
      bubble.append(document.createTextNode(text.slice(offset, match.index)));
      const link = document.createElement('a');
      link.href = match[0]; link.textContent = match[0];
      link.target = '_blank'; link.rel = 'noopener noreferrer';
      bubble.append(link);
      offset = match.index + match[0].length;
    }
    if (offset) bubble.append(document.createTextNode(text.slice(offset)));
    else bubble.textContent = text;
    article.append(bubble);
    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  }

  let historyReady = Promise.resolve();
  let historyUnavailable = false;
  function restoreHistory() {
    return ensureReady().then(() => fetchWithTimeout(`/api/conversations/${encodeURIComponent(conversationId)}`, {cache: 'no-store'}))
      .then((response) => {
        if (response.status === 404) return null;
        if (!response.ok) throw new Error('History unavailable');
        return response.json();
      })
      .then((data) => {
        if (!data) {
          storage.removeItem('masterment_conversation_id');
          conversationId = null;
          pending = null;
          storage.removeItem('masterment_pending_request');
          return;
        }
        for (const item of data.messages) addMessage(item.role, item.content, item.id);
      })
      .then(() => {historyUnavailable = false;})
      .catch(() => {historyUnavailable = true;});
  }
  if (conversationId) historyReady = restoreHistory();

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
    let failed = false;
    try {
      await historyReady;
      await ensureReady();
      if (historyUnavailable && conversationId) await restoreHistory();
      const retry = pending && pending.message === text;
      if (!retry) {
        pending = {message: text, conversation_id: conversationId, request_id: requestId()};
        storage.setItem('masterment_pending_request', JSON.stringify(pending));
        addMessage('user', text);
      }
      input.value = '';
      input.style.height = 'auto';
      input.disabled = true;
      sendButton.disabled = true;
      form.classList.add('is-sending');
      typing.textContent = typingText;
      typing.classList.add('visible');
      const send = () => fetchWithTimeout('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(pending)
      }, 35000);
      let response = await send();
      let data = await response.json();
      for (let attempt = 0; response.status === 202 && attempt < 12; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 5000));
        response = await send();
        data = await response.json();
      }
      if (response.status === 202) throw new Error('Still processing');
      if (!response.ok) throw new Error(data.error || 'Please try again.');
      conversationId = data.conversation_id;
      storage.setItem('masterment_conversation_id', conversationId);
      if (!data.stale) addMessage('assistant', data.reply, data.assistant_message_id);
      pending = null;
      storage.removeItem('masterment_pending_request');
    } catch (error) {
      input.value = text;
      failed = true;
      typing.textContent = 'We couldn’t send that just now. Please try again in a moment.';
      typing.classList.add('visible');
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
