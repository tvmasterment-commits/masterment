// Local-only browser regression test. Requires Playwright as a development tool.
// NODE_PATH may point to an existing Playwright installation; no app dependency.
const {chromium} = require('playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, '.pricing-verification');
  fs.mkdirSync(output, {recursive: true});
  const database = path.join(output, 'browser.sqlite3');
  fs.rmSync(database, {force: true});
  const python = process.env.PYTHON || path.join(root, '.venv', 'Scripts', 'python.exe');
  const server = spawn(python, ['-c', 'import os; from app import create_app; app=create_app({"DATABASE_PATH":os.environ["TEST_DATABASE"],"CHAT_RATE_LIMIT":1000}); app.run(host="127.0.0.1",port=5057,use_reloader=False)'], {
    cwd: root, windowsHide: true, stdio: 'ignore', env: {...process.env, APP_ENV: 'development', OPENAI_API_KEY: '', TEST_DATABASE: database},
  });
  let browser;
  const errors = [];
  const results = [];
  try {
    for (let attempt = 0; attempt < 50; attempt++) {
      try { if ((await fetch('http://127.0.0.1:5057/health')).ok) break; } catch {}
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
    for (const [label, width, height] of [['desktop',1440,1000], ['tablet',820,1180], ['mobile',390,844], ['small-mobile',320,568]]) {
      const context = await browser.newContext({viewport: {width, height}, reducedMotion: 'reduce'});
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      // Avoid downloading portfolio media in the test; count attempts separately.
      let mediaRequests = 0;
      await page.route('**/static/videos/**', route => {mediaRequests++; return route.abort();});
      await page.goto('http://127.0.0.1:5057/', {waitUntil: 'domcontentloaded'});
      await page.waitForFunction(() => document.querySelector('.pricing-trigger') && document.querySelector('#chat-input'));
      const chatBefore = await page.locator('.chat-toggle').boundingBox();
      await page.locator('#services').scrollIntoViewIfNeeded();
      const heading = await page.locator('#services-title').boundingBox();
      const serviceList = await page.locator('#services .discipline-list').boundingBox();
      const serviceTrigger = await page.locator('.services-pricing-trigger').boundingBox();
      assert.equal(await page.locator('#services li').count(), 6);
      assert.equal(await page.locator('#pricing-dialog').count(), 1);
      if (width > 760) {
        const column = await page.locator('.disciplines-intro').boundingBox();
        assert(Math.abs(serviceTrigger.x + serviceTrigger.width / 2 - column.x - column.width / 2) < 1);
        assert(serviceTrigger.y >= heading.y + heading.height);
        assert(serviceTrigger.y < serviceList.y + serviceList.height);
        assert(serviceTrigger.x + serviceTrigger.width < serviceList.x);
      } else {
        assert(serviceTrigger.y >= serviceList.y + serviceList.height);
      }
      await page.screenshot({path: path.join(output, label + '-services.png')});
      assert.equal(await page.locator('.services-pricing-icon svg').count(), 1);
      const arrows = await page.locator('.action-arrow').evaluateAll(elements => elements.map(el => ({path: el.querySelector('path').getAttribute('d'), stroke: el.getAttribute('stroke-width')})));
      assert(arrows.length > 30);
      assert(arrows.every(icon => icon.path === arrows[0].path && icon.stroke === '1.6'));
      const publicCopy = await page.evaluate(() => {const copy = document.body.cloneNode(true); copy.querySelector('#chat-widget').remove(); return copy.textContent;});
      assert(!/[↗↖↘↙➡⬅⬆⬇⧉]/u.test(publicCopy));
      await page.locator('.services-pricing-trigger').click();
      assert.equal(await page.locator('#pricing-dialog').evaluate(el => el.open), true);
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => document.body.style.position !== 'fixed');
      assert.equal(await page.locator('.services-pricing-trigger').evaluate(el => el === document.activeElement), true);
      await page.evaluate(() => window.scrollTo({top: 0, behavior: 'instant'}));
      if (width <= 760) await page.locator('#menu-toggle').click();
      await page.locator('.pricing-trigger').click();
      await page.waitForFunction(() => document.querySelector('#pricing-dialog').open);
      assert.equal(await page.locator('.pricing-close').evaluate(el => el === document.activeElement), true);
      assert.equal(await page.evaluate(() => document.body.style.position), 'fixed');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.equal(await page.locator('.pricing-scroll').evaluate(el => el.scrollWidth <= el.clientWidth), true);
      await page.screenshot({path: path.join(output, label + '.png')});
      await page.locator('.pricing-details summary').first().click();
      assert.equal(await page.locator('.pricing-details').first().getAttribute('open'), '');
      await page.screenshot({path: path.join(output, label + '-details.png')});
      const mediaBefore = mediaRequests;
      await page.locator('.pricing-index a[href="#pricing-bots"]').click();
      await page.screenshot({path: path.join(output, label + '-bots.png')});
      assert.equal(mediaRequests, mediaBefore, 'Pricing browsing must not load portfolio videos');
      assert.equal(await page.locator('.pricing-scroll').evaluate(el => el.scrollWidth <= el.clientWidth), true);
      // Native dialog must trap keyboard focus in both directions.
      await page.locator('.pricing-close').focus();
      await page.keyboard.press('Shift+Tab');
      assert.equal(await page.evaluate(() => !!document.activeElement.closest('#pricing-dialog')), true);
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(() => !!document.activeElement.closest('#pricing-dialog')), true);
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => !document.querySelector('#pricing-dialog').open && document.body.style.position !== 'fixed');
      assert.equal(await page.locator('.pricing-trigger').evaluate(el => el === document.activeElement), true);
      assert.deepEqual(await page.locator('.chat-toggle').boundingBox(), chatBefore);
      await page.locator('.pricing-trigger').click();
      await page.locator('.pricing-close').click();
      await page.waitForFunction(() => !document.querySelector('#pricing-dialog').open);
      // Exercise restoration at a nonzero scroll position without changing the page.
      await page.evaluate(() => window.scrollTo({top: 150, behavior: 'instant'}));
      const savedScroll = await page.evaluate(() => scrollY);
      await page.locator('.pricing-trigger').evaluate(el => el.click());
      await page.keyboard.press('Escape');
      await page.waitForFunction(() => document.body.style.position !== 'fixed');
      assert.equal(await page.evaluate(() => scrollY), savedScroll);
      await page.locator('#contact-message').fill('Keep my project draft.');
      // Filling scrolls to contact; restore the trigger through the normal menu.
      await page.locator('.pricing-trigger').click();
      await page.getByRole('button', {name: 'Get started with Growth', exact: true}).click();
      await page.waitForFunction(() => !document.querySelector('#pricing-dialog').open && document.body.style.position !== 'fixed');
      const draft = await page.locator('#contact-message').inputValue();
      assert.match(draft, /Monthly Content.*Growth/);
      assert.match(draft, /\$650\/month/);
      assert.match(draft, /Keep my project draft/);
      assert.equal(await page.locator('#contact-message').evaluate(el => el === document.activeElement), true);
      // Re-selecting a package must replace our prefix, not the visitor's draft.
      if (width <= 760) await page.locator('#menu-toggle').click();
      await page.locator('.pricing-trigger').click();
      await page.getByRole('button', {name: 'Get started with Essential', exact: true}).click();
      await page.waitForFunction(() => document.body.style.position !== 'fixed');
      const replacement = await page.locator('#contact-message').inputValue();
      assert.match(replacement, /Essential/);
      assert.match(replacement, /Keep my project draft/);
      assert.doesNotMatch(replacement, /Growth/);
      if (width <= 760) await page.locator('#menu-toggle').click();
      await page.locator('.pricing-trigger').click();
      await page.locator('.pricing-ask').click();
      await page.waitForFunction(() => !document.querySelector('#chat-panel').hidden);
      assert.equal(await page.locator('.chat-toggle').getAttribute('aria-expanded'), 'true');
      // Ask Masterment must also preserve an already-open chat, not toggle it shut.
      // Existing mobile chat can cover the nav; exercise keyboard activation.
      await page.locator('.pricing-trigger').focus();
      await page.keyboard.press('Enter');
      await page.locator('.pricing-ask').click();
      await page.waitForFunction(() => !document.querySelector('#pricing-dialog').open && document.body.style.position !== 'fixed');
      assert.equal(await page.locator('#chat-panel').isVisible(), true);
      await page.locator('.chat-close').click();
      assert.equal(await page.locator('#chat-panel').isHidden(), true);
      // The bottom CTA must use the same contact form without changing its content.
      await page.locator('.pricing-trigger').click();
      await page.locator('.pricing-project').click();
      await page.waitForFunction(() => document.body.style.position !== 'fixed');
      assert.equal(await page.locator('#contact-message').inputValue(), replacement);
      // Real local submission through the existing client, then a real chat turn.
      await page.locator('#contact-name').fill('Local Pricing Test');
      await page.locator('#contact-email').fill('pricing-test@example.com');
      await page.locator('#direct-contact button').click();
      await page.getByText('Thank you. Your message has been received.', {exact: true}).waitFor();
      await page.locator('.chat-toggle').click();
      await page.locator('#chat-input').fill('How much is one Reel?');
      await page.locator('#chat-form button').click();
      await page.waitForFunction(() => document.querySelector('#messages').textContent.includes('$250'));
      results.push({label, width, height, result: 'passed'});
      await context.close();
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results));
  } finally {
    await browser?.close();
    server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
