// Development-only audit. Install playwright/lighthouse under .performance-verification.
const {chromium} = require('../.performance-verification/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const phase = process.argv[2] || 'before';
const output = path.resolve('.performance-verification', phase);
fs.mkdirSync(output, {recursive: true});
const url = 'http://127.0.0.1:5058/';
const executablePath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
(async () => {
  const browser = await chromium.launch({executablePath, headless: true});
  try {
    for (const mobile of (process.env.LIGHTHOUSE_ONLY ? [] : [true, false])) {
      const label = mobile ? 'mobile' : 'desktop';
      const context = await browser.newContext({viewport: mobile ? {width:390,height:844} : {width:1440,height:1000}, deviceScaleFactor:mobile?3:1, isMobile:mobile, hasTouch:mobile});
      const page = await context.newPage();
      const cdp = await context.newCDPSession(page);
      await cdp.send('Network.enable');
      await cdp.send('Network.setCacheDisabled', {cacheDisabled:true});
      if (mobile) {
        await cdp.send('Network.emulateNetworkConditions', {offline:false,latency:150,downloadThroughput:200000,uploadThroughput:93750});
        await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
      }
      let transfer = 0;
      const requests = [];
      cdp.on('Network.dataReceived', e => {transfer += e.encodedDataLength;});
      cdp.on('Network.requestWillBeSent', e => requests.push(e.request.url));
      await page.addInitScript(() => {
        window.audit = {lcp:0,cls:0,interactions:[]};
        new PerformanceObserver(list => list.getEntries().forEach(e => window.audit.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});
        new PerformanceObserver(list => list.getEntries().forEach(e => {if(!e.hadRecentInput) window.audit.cls+=e.value;})).observe({type:'layout-shift',buffered:true});
        new PerformanceObserver(list => list.getEntries().forEach(e => {if(e.interactionId) window.audit.interactions.push(e.duration);})).observe({type:'event',buffered:true,durationThreshold:16});
      });
      await page.goto(url, {waitUntil:'domcontentloaded'});
      await page.waitForTimeout(15000);
      const initial = await page.evaluate(() => ({...window.audit,fcp:performance.getEntriesByName('first-contentful-paint')[0]?.startTime,resources:performance.getEntriesByType('resource').map(e=>({url:e.name,size:e.transferSize,duration:e.duration})),videos:[...document.querySelectorAll('video')].map(v=>({label:v.className,source:v.currentSrc,ready:v.readyState,paused:v.paused}))}));
      initial.transferBytesAt15Seconds = transfer;
      initial.requestCountAt15Seconds = requests.length;
      initial.requests = [...requests];
      await page.screenshot({path:path.join(output, label+'.png')});
      // A repeatable lab interaction sample; not field INP.
      if(mobile) await page.locator('#menu-toggle').click();
      await page.locator('.pricing-trigger').click();
      await page.keyboard.press('Escape');
      await page.locator('.chat-toggle').click();
      await page.locator('.chat-close').click();
      await page.waitForTimeout(200);
      initial.labInteractionMaxMs = await page.evaluate(()=>Math.max(0,...window.audit.interactions));
      fs.writeFileSync(path.join(output,label+'-network.json'),JSON.stringify(initial,null,2));
      await context.close();
    }
  } finally { await browser.close(); }
  const {default:lighthouse} = await import(pathToFileURL(path.resolve('.performance-verification/node_modules/lighthouse/core/index.js')));
  const chromeLauncher = await import(pathToFileURL(path.resolve('.performance-verification/node_modules/chrome-launcher/dist/index.js')));
  const chrome = await chromeLauncher.launch({chromePath:executablePath,chromeFlags:['--headless','--no-first-run']});
  try {
    for (const desktop of (process.env.LIGHTHOUSE_ONLY ? [true] : [false,true])) {
      const config = desktop ? (await import(pathToFileURL(path.resolve('.performance-verification/node_modules/lighthouse/core/config/desktop-config.js')))).default : undefined;
      const result = await lighthouse(url,{port:chrome.port,onlyCategories:['performance'],output:'html'},config);
      const label = desktop?'desktop':'mobile';
      fs.writeFileSync(path.join(output,label+'-lighthouse.html'),result.report);
      fs.writeFileSync(path.join(output,label+'-lighthouse.json'),JSON.stringify(result.lhr,null,2));
      console.log(phase,label,result.lhr.categories.performance.score, Object.fromEntries(['first-contentful-paint','largest-contentful-paint','cumulative-layout-shift','total-byte-weight','network-requests'].map(k=>[k,result.lhr.audits[k]?.numericValue])));
    }
  } finally { await chrome.kill(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
