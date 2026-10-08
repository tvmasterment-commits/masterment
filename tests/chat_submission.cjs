// Execute the actual chat script with controlled DOM/network failures, no production writes.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');

function element() {
  return {textContent: '', value: '', disabled: false, style: {}, children: [], handlers: {},
    classList: {add() {}, remove() {}},
    append(item) {this.children.push(item);}, focus() {},
    addEventListener(name, handler) {this.handlers[name] = handler;}};
}
async function scenario(storedConversation, privateStorage = false) {
  const form = element(), input = element(), messages = element(), typing = element(), button = element();
  form.querySelector = () => button;
  const store = new Map();
  if (storedConversation) store.set('masterment_conversation_id', 'existing-conversation');
  let sessions = 0, submissions = 0, failPost = true;
  const requests = [];
  const context = {
    document: {querySelector: selector => ({'#chat-form': form, '#chat-input': input,
      '#messages': messages, '#typing': typing})[selector], querySelectorAll: () => [], createElement: element,
      createTextNode: text => ({textContent: text})},
    sessionStorage: {getItem: key => {if (privateStorage) throw new Error('Storage blocked'); return store.get(key) || null;},
      setItem: (key, value) => {if (privateStorage) throw new Error('Storage blocked'); store.set(key, value);},
      removeItem: key => {if (privateStorage) throw new Error('Storage blocked'); store.delete(key);}},
    crypto: privateStorage ? {getRandomValues: bytes => require('node:crypto').randomFillSync(bytes)} : {randomUUID},
    window: {matchMedia: () => ({matches: false})}, setTimeout,
    fetch: async (url, options) => {
      if (url === '/api/chat/session') {
        sessions++;
        if (sessions === 1) throw new Error('Temporary session failure');
        return {ok: true};
      }
      if (url.startsWith('/api/conversations/')) return {ok: false, status: 503};
      submissions++;
      requests.push(JSON.parse(options.body));
      if (failPost) {failPost = false; throw new Error('Temporary submission failure');}
      return {ok: true, status: 200, json: async () => ({conversation_id: 'saved', reply: 'Photography inquiry saved.'})};
    },
  };
  vm.runInNewContext(fs.readFileSync('app/static/chat.js', 'utf8'), context);
  const submit = async () => {input.value = "I'm looking for photography.";
    await form.handlers.submit({preventDefault() {}});
    assert.equal(input.disabled, false); assert.equal(button.disabled, false);};
  if (!storedConversation) {
    await submit();
    assert.equal(submissions, 0);
    assert.equal(input.value, "I'm looking for photography.");
  }
  await submit();
  assert.equal(submissions, 1);
  await submit();
  assert.equal(submissions, 2);
  assert.equal(requests[0].request_id, requests[1].request_id);
  assert.equal(sessions, 2);
  assert.equal(store.get('masterment_pending_request'), undefined);
  if (!privateStorage) assert.equal(store.get('masterment_conversation_id'), 'saved');
  assert.match(requests[0].request_id, /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
  assert.equal(messages.children.filter(item => item.className === 'message user').length, 1);
  assert.equal(messages.children.filter(item => item.className === 'message assistant').length, 1);
}
(async () => {
  await scenario(false);
  await scenario(true);
  await scenario(false, true);
  console.log('PASS: session/history failures recover, controls unlock, and submission retries preserve request identity.');
})().catch(error => {console.error(error); process.exitCode = 1;});
