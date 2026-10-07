const {chromium}=require('../.performance-verification/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const results=[];
 try {
  for(const mobile of [false,true]) {
   const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile});
   const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto('http://127.0.0.1:5058/',{waitUntil:'domcontentloaded'});
   assert.equal(await page.locator('.reels-video source[src],.project-video source[src]').count(),0);
   const videos=page.locator('.reels-video,.project-video');
   for(let i=0;i<11;i++) {
    const video=videos.nth(i);
    await video.evaluate(v=>scrollTo({top:v.getBoundingClientRect().top+scrollY-100,behavior:'instant'}));
    await page.waitForFunction(i=>{const v=document.querySelectorAll('.reels-video,.project-video')[i];return !v.paused&&v.readyState>=3&&v.currentTime>0;},i);
    const state=await video.evaluate(v=>({name:v.getAttribute('aria-label'),url:v.currentSrc,error:v.error?.code||0,time:v.currentTime,overlay:getComputedStyle(v.parentElement.querySelector('.portfolio-poster')).visibility}));
    const response=await page.request.get(state.url,{headers:{Range:'bytes=0-1023'}});
    assert.equal(response.status(),206);
    assert.match(response.headers()['content-type'],/^video\/mp4/);
    assert.match(response.headers()['content-range'],/^bytes 0-1023\//);
    assert.equal(state.error,0);
    assert.equal(state.overlay,'hidden');
    await video.click({force:true});
    await page.evaluate(()=>dispatchEvent(new Event('resize')));
    await page.waitForTimeout(150);
    assert.equal(await video.evaluate(v=>v.paused),true,'explicit pause must survive scheduler update');
    await video.locator('..').locator('.portfolio-play').click();
    await page.waitForFunction(i=>!document.querySelectorAll('.reels-video,.project-video')[i].paused,i);
    results.push({device:mobile?'mobile':'desktop',item:state.name,url:state.url,result:'play/pause/resume/206/MIME passed'});
   }
   // Race: cancel loading, return rapidly, and evaluate a second script instance.
   await page.evaluate(()=>{scrollTo(0,0);dispatchEvent(new Event('scroll'));});
   await page.waitForTimeout(100);
   await page.addScriptTag({path:'app/static/reels.js'});
   assert.equal(await page.locator('.portfolio-play').count(),11,'scheduler initializes once');
   await videos.first().evaluate(v=>scrollTo({top:v.getBoundingClientRect().top+scrollY-100,behavior:'instant'}));
   await page.waitForFunction(()=>{const v=document.querySelector('.reels-video');return !v.paused&&v.readyState>=3;});
   assert.deepEqual(errors,[]);
   await page.close();
  }
  for(const mobile of [false,true]) {
   const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile});
   await page.addInitScript(()=>{
    const native=HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play=function(){
     if(this.classList.contains('reels-video')&&!this.dataset.userActivated) return Promise.reject(new DOMException('Gesture required','NotAllowedError'));
     return native.call(this);
    };
   });
   await page.goto('http://127.0.0.1:5058/',{waitUntil:'domcontentloaded'});
   for(const number of [1,2,3,5,9]) {
    const video=page.locator(`.reels-video[aria-label="Masterment Reel ${number}"]`);
    await video.evaluate(v=>scrollTo({top:v.getBoundingClientRect().top+scrollY-100,behavior:'instant'}));
    const button=video.locator('..').locator('.portfolio-play');
    await button.waitFor({state:'visible'});
    if(mobile)await button.tap();else await button.click();
    await page.waitForFunction(n=>{const v=document.querySelector(`.reels-video[aria-label="Masterment Reel ${n}"]`);return !v.paused&&v.readyState>=3&&v.currentTime>0;},number);
    results.push({device:mobile?'mobile':'desktop',item:`Reel ${number}`,result:'forced autoplay rejection → trusted click/tap playback passed'});
   }
   await page.close();
  }
  const race=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  await race.addInitScript(()=>{
   const native=HTMLMediaElement.prototype.play;
   let held=false;
   HTMLMediaElement.prototype.play=function(){
    if(this.getAttribute('aria-label')==='Masterment Reel 1'&&!held){
     held=true;
     return new Promise((resolve,reject)=>{window.rejectOldPlay=()=>reject(new DOMException('Old request denied','NotAllowedError'));});
    }
    return native.call(this);
   };
  });
  await race.goto('http://127.0.0.1:5058/',{waitUntil:'domcontentloaded'});
  const first=race.locator('.reels-video').first();
  await first.evaluate(v=>scrollTo({top:v.getBoundingClientRect().top+scrollY-100,behavior:'instant'}));
  await race.waitForFunction(()=>!!window.rejectOldPlay);
  await race.evaluate(()=>scrollTo({top:document.body.scrollHeight,behavior:'instant'}));
  await race.waitForTimeout(200);
  await first.evaluate(v=>scrollTo({top:v.getBoundingClientRect().top+scrollY-100,behavior:'instant'}));
  await race.waitForFunction(()=>{const v=document.querySelector('.reels-video');return !v.paused&&v.readyState>=3;});
  await race.evaluate(()=>window.rejectOldPlay());
  await race.waitForTimeout(200);
  assert.equal(await first.evaluate(v=>v.paused),false);
  assert.equal(await first.locator('..').locator('.portfolio-play').isVisible(),false,'stale rejection must not alter current playback');
  results.push({device:'mobile',item:'Reel 1',result:'delayed stale rejection after unload/reload ignored'});
  await race.close();
  fs.writeFileSync('.performance-verification/reels-runtime-results.json',JSON.stringify(results,null,2));
  console.log(JSON.stringify(results));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
