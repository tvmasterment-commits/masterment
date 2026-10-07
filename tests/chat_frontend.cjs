const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const handlers = {};
const children = [];
const element = () => ({classList:{add(){},remove(){}},style:{},append(){},focus(){},addEventListener(){}});
const input = {...element(),value:'Dark cinematic R&B',disabled:false};
const button = element();
const form = {...element(),querySelector:()=>button,addEventListener:(name,fn)=>handlers[name]=fn};
const messages = {...element(),append:item=>children.push(item)};
const surfaces = {'#chat-form':form,'#chat-input':input,'#messages':messages,'#typing':element()};
const storage = new Map([['masterment_conversation_id','cid']]);
let restore;
let posts=0;
let failNext=false;
const payloads=[];
const history = new Promise(resolve=>restore=resolve);
const response = data => ({ok:true,status:200,json:async()=>data});
const context = {
 document:{querySelector:key=>surfaces[key],querySelectorAll:()=>[],createElement:()=>({...element(),append(bubble){this.text=bubble.textContent;}})},
 sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 crypto:{randomUUID:()=> 'request-1'},
 window:{matchMedia:()=>({matches:true})},setTimeout,
 fetch:async(url,options)=>{
  if(url==='/api/chat/session')return response({});
  if(url.startsWith('/api/conversations/'))return history;
  posts++;
  payloads.push(JSON.parse(options.body));
  if(failNext){failNext=false;throw new Error('Network failed');}
  return response({conversation_id:'cid',assistant_message_id:posts===1?4:6,reply:'Do you have a date in mind?'});
 }
};
vm.runInNewContext(fs.readFileSync('app/static/chat.js','utf8'),context);
(async()=>{
 const sending=handlers.submit({preventDefault(){}});
 await handlers.submit({preventDefault(){}}); // duplicate click while restoration waits
 assert.equal(posts,0);
 restore(response({messages:[{id:4,role:'assistant',content:'Do you have a date in mind?'}]}));
 await sending;
 assert.equal(posts,1);
 assert.equal(children.filter(c=>c.className==='message assistant').length,1);
 assert.equal(children.filter(c=>c.className==='message user').length,1);
 input.value='October 20';
 failNext=true;
 await handlers.submit({preventDefault(){}});
 assert.equal(children.filter(c=>c.className==='message assistant').length,1,'transport error is status, not an assistant turn');
 assert.equal(input.value,'October 20');
 await handlers.submit({preventDefault(){}});
 assert.deepEqual(payloads[1],payloads[2],'browser retry preserves the entire request identity');
 assert.equal(children.filter(c=>c.className==='message assistant').length,2);
 assert.equal(children.filter(c=>c.className==='message user').length,2);
 console.log('PASS: duplicate submit blocked; restoration completes before POST; same saved assistant rendered once');
 console.log('PASS: transport failure uses status; browser retry keeps request ID and renders one final reply');
})().catch(error=>{console.error(error);process.exitCode=1});
