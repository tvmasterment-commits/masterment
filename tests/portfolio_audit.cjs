// Local-only fixed-window portfolio audit. Run against an isolated server on 5058.
const {chromium}=require('../.performance-verification/node_modules/playwright');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const results=[];
 try {
  for(const mobile of [true,false]){
   const page=await browser.newPage({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile});
   const cdp=await page.context().newCDPSession(page);await cdp.send('Network.enable');
   await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});
   await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:mobile?150:20,downloadThroughput:mobile?200000:1250000,uploadThroughput:93750});
   if(mobile)await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
   const requests=[],ids=new Map();let bytes=0;
   cdp.on('Network.requestWillBeSent',e=>{if(/\/videos\/(reels|work|portfolio-web)\//.test(e.request.url)){requests.push(e.request.url);ids.set(e.requestId,true);}});
   cdp.on('Network.dataReceived',e=>{if(ids.has(e.requestId))bytes+=e.encodedDataLength;});
   await page.goto('http://127.0.0.1:5058/',{waitUntil:'domcontentloaded'});await page.waitForTimeout(4000);
   const initial={requests:requests.length,bytes};
   await page.locator('.reels-gallery').first().evaluate(el=>scrollTo({top:el.getBoundingClientRect().top+scrollY-150,behavior:'instant'}));
   const start=Date.now();let postersReadyMs=null,firstPlaybackMs=null;
   for(let i=0;i<40;i++){
    const state=await page.locator('.reels-video').evaluateAll(vs=>vs.slice(0,3).map(v=>({playing:!v.paused&&v.readyState>=3,poster:v.parentElement.querySelector('.portfolio-poster')?.complete&&v.parentElement.querySelector('.portfolio-poster')?.naturalWidth>0})));
    if(postersReadyMs===null && state.every(s=>s.poster))postersReadyMs=Date.now()-start;
    if(firstPlaybackMs===null && state.some(s=>s.playing))firstPlaybackMs=Date.now()-start;
    await page.waitForTimeout(250);
   }
   const state=await page.locator('video').evaluateAll(vs=>vs.map(v=>({class:v.className,ready:v.readyState,paused:v.paused,source:v.currentSrc,poster:v.poster})));
   await page.screenshot({path:`.performance-verification/portfolio-${process.argv[2]}-${mobile?'mobile':'desktop'}.png`});
   results.push({device:mobile?'mobile':'desktop',initial,afterScroll:{requests:requests.length,bytes,postersReadyMs,firstPlaybackMs},state});
   await page.close();
  }
  fs.writeFileSync(`.performance-verification/portfolio-${process.argv[2]}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results.map(({state,...r})=>r)));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
