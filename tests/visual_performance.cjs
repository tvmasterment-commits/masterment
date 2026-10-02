// Requires reference.html and reference JS saved from the pre-change git revision.
const {chromium}=require('../.performance-verification/node_modules/playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const results=[];
 try {
  for(const [label,width,height] of [['mobile',390,844],['desktop',1440,1000]]) {
   const snapshots=[];
   for(const phase of ['reference','optimized']) {
    const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'});
    if(phase==='reference') {
     await page.route('http://127.0.0.1:5058/',route=>route.fulfill({contentType:'text/html',body:fs.readFileSync('.performance-verification/reference.html','utf8')}));
     for(const file of ['customer.js','reels.js']) await page.route(`**/static/${file}*`,route=>route.fulfill({contentType:'text/javascript',body:fs.readFileSync('.performance-verification/reference-'+file,'utf8')}));
    }
    // Isolate visual layout from moving footage. Actual playback has separate tests.
    await page.route('**/static/videos/**',route=>route.abort());
    await page.goto('http://127.0.0.1:5058/');
    await page.addStyleTag({content:'*,*::before,*::after {animation:none !important;transition:none !important;} video {visibility:hidden !important;} .project-video-fallback {visibility:hidden !important;}'});
    await page.waitForTimeout(700);
    await page.screenshot({path:`.performance-verification/${phase}-${label}-hero.png`});
    await page.locator('#about').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    await page.locator('#about').screenshot({path:`.performance-verification/${phase}-${label}-about.png`});
    const snapshot=await page.evaluate(()=>({
     text:document.body.innerText.replace(/This video is currently unavailable\./g,'').replace(/\s+/g,' ').trim(),
     boxes:['.site-header','.hero','.portfolio-grid','#services','#about','.about-logo','.about-partner-marquee','.about-partner-mobile','#contact','.chat-toggle'].map(s=>{const el=document.querySelector(s),r=el.getBoundingClientRect();return {s,x:r.x,y:r.y+scrollY,width:r.width,height:r.height};})
    }));
    snapshots.push(snapshot);
    await page.close();
   }
   assert.equal(snapshots[0].text,snapshots[1].text);
   for(let i=0;i<snapshots[0].boxes.length;i++) for(const dimension of ['x','y','width','height']) assert(Math.abs(snapshots[0].boxes[i][dimension]-snapshots[1].boxes[i][dimension])<1,`${label} ${snapshots[0].boxes[i].s} ${dimension}: ${snapshots[0].boxes[i][dimension]} vs ${snapshots[1].boxes[i][dimension]}`);
   results.push({label,result:'passed',geometry:snapshots[1].boxes});
  }
  fs.writeFileSync('.performance-verification/visual-results.json',JSON.stringify(results,null,2));
  console.log('Desktop/mobile text and geometry preserved. Screenshots saved.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
