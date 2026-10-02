const {chromium} = require('../.performance-verification/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const results=[];
  try {
    for (const [label,width,height] of [['mobile',390,844],['desktop',1440,1000],['fallback',390,844]]) {
      const context=await browser.newContext({viewport:{width,height}});
      const page=await context.newPage();
      const errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      page.on('response',r=>{if(r.status()>=400) errors.push(`${r.status()} ${r.url()}`);});
      if(label==='fallback') await page.addInitScript(()=>{delete window.IntersectionObserver;});
      await page.goto('http://127.0.0.1:5058/');
      await page.waitForTimeout(1200);
      assert.equal(await page.locator('.hero-video').evaluate(v=>!v.paused),true);
      assert.equal(await page.locator('.project-video source[src]').count(),0);
      assert.equal(await page.locator('.reels-video source[src]').count()<=3,true);
      assert.equal(await page.locator('.reels-video').evaluateAll(vs=>vs.every(v=>v.paused)),true);
      const videos=page.locator('.reels-video, .project-video');
      assert.equal(await videos.count(),11);
      for(let i=0;i<11;i++) {
        const video=videos.nth(i);
        await video.evaluate(v=>window.scrollTo({top:v.getBoundingClientRect().top+scrollY-100,behavior:'instant'}));
        await page.waitForFunction(i=>{const v=document.querySelectorAll('.reels-video,.project-video')[i];return !v.paused && v.readyState>=3 && v.currentTime>0;},i);
        assert.equal(await video.evaluate(v=>v.muted && v.playsInline && !!v.poster),true);
        if(await video.evaluate(v=>v.classList.contains('project-video'))) {
          assert.equal(await video.evaluate(v=>v.currentTime>=Number(v.dataset.highlightStart) && v.currentTime<Number(v.dataset.highlightEnd)+0.5),true);
          await video.evaluate(v=>{v.currentTime=Number(v.dataset.highlightEnd);});
          await page.waitForFunction(i=>{const v=document.querySelectorAll('.reels-video,.project-video')[i];return v.currentTime<Number(v.dataset.highlightStart)+2;},i);
        }
      }
      await page.locator('#about').scrollIntoViewIfNeeded();
      await page.waitForFunction(()=>[...document.querySelectorAll('.about-partner-frame img, .mobile-partner-logo img')].filter(i=>i.getBoundingClientRect().width && i.getBoundingClientRect().left<innerWidth && i.getBoundingClientRect().right>0).every(i=>i.complete && i.naturalWidth>0));
      await page.waitForTimeout(300);
      assert.equal(await videos.evaluateAll(vs=>vs.every(v=>v.paused)),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      await page.screenshot({path:path.resolve('.performance-verification',`verified-${label}-about.png`)});
      // The approved hover pause remains intact.
      if(width>760) {
        await page.locator('.about-partner-marquee').hover();
        assert.equal(await page.locator('.about-partner-track').evaluate(el=>getComputedStyle(el).animationPlayState),'paused');
      }
      await page.evaluate(()=>scrollTo({top:0,behavior:'instant'}));
      await page.waitForTimeout(300);
      assert.equal(await videos.evaluateAll(vs=>vs.every(v=>v.paused)),true);
      assert.deepEqual(errors,[]);
      results.push({label,media:11,errors,result:'passed'});
      await context.close();
    }
    const page=await browser.newPage({reducedMotion:'reduce'});
    await page.goto('http://127.0.0.1:5058/');
    assert.equal(await page.locator('.hero-video').evaluate(v=>v.paused),true);
    await page.locator('.project-video').first().scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    assert.equal(await page.locator('.project-video').evaluateAll(vs=>vs.every(v=>v.paused)),true);
    results.push({label:'reduced-motion',result:'passed'});
    fs.writeFileSync('.performance-verification/media-results.json',JSON.stringify(results,null,2));
    console.log(JSON.stringify(results));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
