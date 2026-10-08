// Local-only real browser checks. All inquiries use a unique disposable database.
const {chromium, webkit} = require('../.performance-verification/node_modules/playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');

(async () => {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, '.performance-verification');
  fs.mkdirSync(output, {recursive: true});
  const database = path.join(output, `masterment-${randomUUID()}.sqlite3`);
  const server = spawn(process.env.PYTHON || path.join(root, '.venv/Scripts/python.exe'), ['-c',
    'import os; from app import create_app; app=create_app({"DATABASE_PATH":os.environ["TEST_DATABASE"],"DATABASE_URL":"","CHAT_RATE_LIMIT":1000}); app.run(host="127.0.0.1",port=5062,use_reloader=False)'],
    {cwd: root, windowsHide: true, stdio: 'ignore', env: {...process.env,
      APP_ENV: 'development', OPENAI_API_KEY: '', TEST_DATABASE: database}});
  const results = [];
  let browser;
  try {
    let started = false;
    for (let n = 0; n < 60; n++) {
      try {if ((await fetch('http://127.0.0.1:5062/health')).ok) {started = true; break;}} catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.ok(started, 'Local test server started');
    for (const [name, engine, options] of [
      ['desktop-chrome', chromium, {viewport: {width: 1440, height: 1000}}],
      ['mobile-webkit', webkit, {viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true}],
    ]) {
      browser = await engine.launch(name.includes('chrome') ? {headless: true,
        executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'} : {headless: true});
      const context = await browser.newContext(options);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      // Avoid heavy portfolio downloads in this chat-focused test.
      await page.route('**/*.mp4*', route => route.fulfill({status: 204, body: ''}));
      await page.goto('http://127.0.0.1:5062/', {waitUntil: 'domcontentloaded'});
      assert.match(await page.title(), /Masterment LLC/);
      assert.equal(await page.locator('link[rel=canonical]').getAttribute('href'), 'https://masterment.services/');
      await page.locator('.chat-toggle').click();
      let firstSession = true;
      await page.route('**/api/chat/session', route => {
        if (firstSession) {firstSession = false; return route.abort();}
        return route.continue();
      });
      await page.locator('#chat-input').fill('I want a music video.');
      await page.locator('#chat-form button').click();
      await page.waitForFunction(() => document.querySelector('#typing').textContent.includes('couldn’t send'));
      assert.equal(await page.locator('#chat-input').isEnabled(), true);
      async function send(text) {
        await page.locator('#chat-input').fill(text);
        const [response] = await Promise.all([
          page.waitForResponse(r => new URL(r.url()).pathname === '/api/chat' && r.request().method() === 'POST'),
          page.locator('#chat-form button').click(),
        ]);
        assert.equal(response.status(), 200);
        const data = await response.json();
        await page.waitForFunction(() => !document.querySelector('#chat-input').disabled);
        return data;
      }
      await send('I want a music video.');
      const dark = await send('Dark.');
      assert.match(dark.captured.description, /Dark/);
      assert.doesNotMatch(dark.reply, /look, feel/);
      await send('October 20');
      const location = await send('Boston');
      assert.equal(location.captured.location, 'Boston');
      const contact = await send('My name is Browser Test. browser-test@example.invalid.');
      assert.equal(contact.captured.email, 'browser-test@example.invalid');
      await send('Show me portfolio examples.');
      assert.equal(await page.locator('#messages a[href^="https://www.youtube.com/watch"]').count(), 3);
      assert.equal(await page.locator('.message.user').count(), 6);
      await page.reload({waitUntil: 'domcontentloaded'});
      await page.waitForFunction(() => document.querySelectorAll('.message.user').length === 6);
      await page.locator('.chat-toggle').click();
      assert.equal(await page.locator('#messages a[href^="https://www.youtube.com/watch"]').count(), 3);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.ok(await page.locator('#messages').evaluate(el => el.scrollTop > 0));
      assert.equal(errors.length, 0, errors.join('; '));
      await page.screenshot({path: path.join(output, `masterment-${name}.png`)});
      results.push({engine: name, sessionRecovery: true, shortAnswers: true, leadCapture: true,
        portfolioLinks: true, historyRestoration: true, mobileOverflow: false, pageErrors: 0});
      await browser.close(); browser = null;
    }
    console.log(JSON.stringify(results));
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
