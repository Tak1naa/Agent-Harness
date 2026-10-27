// 测试真实客户端会话逻辑；仅用轻量DOM和延迟API替身隔离浏览器。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const session=id=>({id,title:id,status:'completed',events:[],changes:[],partial:'',requests:0,usage:{prompt_tokens:0,completion_tokens:0}});
function setup(){
 const elements=new Map();
 function node(key){if(!elements.has(key))elements.set(key,{value:'',innerHTML:'',textContent:'',scrollHeight:0,scrollTop:0,clientHeight:0,classList:{add(){},remove(){},toggle(){}},addEventListener(){},setAttribute(){},focus(){}});return elements.get(key);}
 const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener(){}},window:{innerWidth:1440},localStorage:{setItem(){},getItem(){return null;}},AbortSignal:{timeout(){}},fetch:()=>new Promise(()=>{}),setTimeout:()=>1,clearTimeout(){},console});
 vm.runInContext(fs.readFileSync('safety_harness/web_assets/client.js','utf8')+'\nthis.hooks={state,openSession,newSession,send,decide};',context);
 const h=context.hooks;h.state.info={key_configured:true};h.state.session=session('A');
 context.harnessApi=async(path)=>path==='/api/client/sessions'?[]:session(path.split('/').pop());
 vm.runInContext('api=(path,body)=>harnessApi(path,body)',context);
 return {h,node,context};
}
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}

test('会话往返切换恢复各自草稿与文件引用',async()=>{
 const {h,node}=setup();node('#prompt').value='A draft';h.state.attachment=['README.md'];
 await h.openSession('B');assert.equal(node('#prompt').value,'');assert.equal(h.state.attachment.length,0);
 node('#prompt').value='B draft';h.state.attachment=['docs/b.md'];
 await h.openSession('A');assert.equal(node('#prompt').value,'A draft');assert.equal(h.state.attachment[0],'README.md');
 await h.openSession('B');assert.equal(node('#prompt').value,'B draft');assert.equal(h.state.attachment[0],'docs/b.md');
});

test('新会话不携带原会话草稿',async()=>{
 const {h,node,context}=setup();node('#prompt').value='original';h.state.attachment=['README.md'];
 context.harnessApi=async path=>path==='/api/client/sessions'?[]:session(path.endsWith('/create')?'NEW':path.split('/').pop());
 await h.newSession();assert.equal(h.state.session.id,'NEW');assert.equal(node('#prompt').value,'');assert.equal(h.state.attachment.length,0);
 await h.openSession('A');assert.equal(node('#prompt').value,'original');
});

test('延迟发送响应不能覆盖新会话或清空其草稿',async()=>{
 const {h,node,context}=setup(),pending=deferred();let submitted;
 context.harnessApi=async(path,body)=>{if(path.endsWith('/send')){submitted=body;return pending.promise;}return path==='/api/client/sessions'?[]:session(path.split('/').pop());};
 node('#prompt').value='A task';h.state.attachment=['README.md'];
 const sending=h.send();await h.openSession('B');node('#prompt').value='B unsent';
 pending.resolve({...session('A'),status:'running'});await sending;
 assert.equal(submitted.session_id,'A');assert.equal(submitted.attachments[0],'README.md');
 assert.equal(h.state.session.id,'B');assert.equal(node('#prompt').value,'B unsent');
});

test('延迟审批响应不能切回旧会话',async()=>{
 const {h,node,context}=setup(),pending=deferred();
 context.harnessApi=async path=>path.endsWith('/decide')?pending.promise:path==='/api/client/sessions'?[]:session(path.split('/').pop());
 const deciding=h.decide('change-1',false);await h.openSession('B');node('#prompt').value='B draft';
 pending.resolve(session('A'));await deciding;
 assert.equal(h.state.session.id,'B');assert.equal(node('#prompt').value,'B draft');
});

test('请求未返回时保留用户新输入',async()=>{
 const {h,node,context}=setup(),pending=deferred();
 context.harnessApi=async path=>path.endsWith('/send')?pending.promise:[];
 node('#prompt').value='submitted';const sending=h.send();node('#prompt').value='next draft';
 pending.resolve({...session('A'),status:'running'});await sending;
 assert.equal(node('#prompt').value,'next draft');
});
