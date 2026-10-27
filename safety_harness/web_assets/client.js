/* 会话驱动的客户端：界面内容只来自本地Agent API，工具结果与修改审批可追溯。 */
const $=s=>document.querySelector(s);
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={info:null,session:null,files:[],attachment:[],preview:null,panel:'files',poll:null,version:0,drafts:{},sending:false};
const stateNames={idle:'等待任务',running:'Agent 正在执行',completed:'任务完成',blocked:'任务已阻塞',failed:'任务未完成',cancelled:'任务已停止',limited:'达到本轮调用上限',interrupted:'上次任务已中断',awaiting_approval:'等待确认修改',stopping:'正在停止'};
const toolNames={list_files:'浏览项目文件',read_file:'读取文件',analyze_python:'静态分析',run_security_case:'隔离配对测试',benchmark_summary:'读取评测统计',propose_edit:'准备文件修改'};
const stamp=t=>new Date(t).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false});
function notice(text){$('#client-notice').textContent=text;$('#client-notice').hidden=!text;}
async function api(path,body){
 const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Harness-CSRF':state.info?.csrf||''},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(path==='/api/environment'?70000:15000)});
 let data;try{data=await response.json();}catch{throw new Error('客户端服务未返回有效数据，请确认服务仍在运行。');}
 if(!response.ok)throw new Error(data.error||`请求失败（${response.status}）`);return data;
}
function on(selector,type,fn){$(selector).addEventListener(type,e=>Promise.resolve(fn(e)).catch(err=>notice(err.message)));}
function inline(text){return escapeHTML(text).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');}
function markdown(text){
 const blocks=String(text).split(/```(?:[a-zA-Z0-9_+-]*)\n?/);return blocks.map((part,i)=>{
  if(i%2)return `<pre><code>${escapeHTML(part.replace(/\n$/,''))}</code></pre>`;
  return part.split(/\n\n+/).filter(Boolean).map(p=>{
   if(/^###? /.test(p))return p.split('\n').map(l=>l.startsWith('### ')?`<h3>${inline(l.slice(4))}</h3>`:l.startsWith('## ')?`<h2>${inline(l.slice(3))}</h2>`:`<p>${inline(l)}</p>`).join('');
   if(p.split('\n').every(l=>/^[-*] /.test(l)))return `<ul>${p.split('\n').map(l=>`<li>${inline(l.slice(2))}</li>`).join('')}</ul>`;
   return `<p>${p.split('\n').map(inline).join('<br>')}</p>`;
  }).join('');
 }).join('');
}
function toolHTML(ev,compact=false){
 const path=ev.args?.path||ev.args?.case_id||'';
 const label={running:'执行中',completed:'已返回',failed:'失败',interrupted:'已中断'}[ev.status]||ev.status;
 return `<details class="tool-message ${ev.status}" data-event="${escapeHTML(ev.id)}"><summary><span>${escapeHTML(toolNames[ev.name]||ev.name)}</span>${path?`<span class="tool-path">${escapeHTML(path)}</span>`:''}<span class="tool-state">${label}</span></summary><pre class="tool-result">${escapeHTML(JSON.stringify({参数:ev.args,...(ev.result?{返回:ev.result}:{状态:'等待工具返回'})},null,2))}</pre></details>`;
}
function renderMessages(force=false){
 const scroll=$('#chat-scroll'),nearBottom=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<100,oldTop=scroll.scrollTop;
 const open=new Set([...document.querySelectorAll('#messages details[open]')].map(e=>e.dataset.event));
 const s=state.session,events=s?.events||[];
 $('#welcome').hidden=events.length>0;
 $('#messages').innerHTML=events.map(ev=>{
  if(ev.type==='tool')return toolHTML(ev);
  if(ev.type==='notice'||ev.type==='error')return `<div class="message notice ${ev.type==='error'?'error':''}">${escapeHTML(ev.text)}</div>`;
  return `<article class="message ${ev.type}"><div class="message-label">${ev.type==='user'?'你':'Harness'}<span class="message-time">${stamp(ev.at)}</span></div><div class="message-body">${ev.type==='user'?escapeHTML(ev.text):markdown(ev.text)}</div>${ev.attachments?.length?`<p class="message-label">引用：${ev.attachments.map(escapeHTML).join(' · ')}</p>`:''}</article>`;
 }).join('')+(s?.partial?`<article class="message assistant"><div class="message-label">Harness · 正在输出</div><div class="message-body streaming">${markdown(s.partial)}</div></article>`:'');
 document.querySelectorAll('#messages details').forEach(e=>{e.open=open.has(e.dataset.event);});
 if(force||nearBottom)scroll.scrollTop=scroll.scrollHeight;else scroll.scrollTop=oldTop;
}
function renderSession(force=false){
 const s=state.session,running=s&&['running','stopping'].includes(s.status),pending=s?.changes.some(c=>c.status==='pending');
 $('#session-title').textContent=s?.title||'新会话';
 $('#session-subtitle').textContent=state.info?.workspace||'Agent-Harness';
 $('#send-message').hidden=Boolean(running);$('#stop-agent').hidden=!running;
 $('#send-message').disabled=!state.info?.key_configured||pending;
 $('#stop-agent').disabled=s?.status==='stopping';
 $('#prompt').disabled=Boolean(pending);
 $('#prompt').placeholder=pending?'请先审查右侧的修改提案，再继续任务。':'描述任务，或从右侧引用一个文件…';
 $('#agent-status').textContent=s?`${stateNames[s.status]||s.status} · ${s.requests} 次模型请求 · ${s.usage.prompt_tokens+s.usage.completion_tokens} Token`:(state.info?.key_configured?'项目已连接 · 修改需确认':'未配置密钥 · 请查看运行设置');
 $('#change-count').textContent=String(s?.changes.filter(c=>c.status==='pending').length||0);
 renderMessages(force);renderChanges();renderActivity();
}
let sessionListVersion=0;
async function refreshSessions(){
 const request=++sessionListVersion;
 const sessions=await api('/api/client/sessions');
 if(request!==sessionListVersion)return sessions;
 $('#sessions').innerHTML=sessions.length?sessions.map(s=>`<button class="session-item ${state.session?.id===s.id?'selected':''}" data-session="${s.id}"><strong>${escapeHTML(s.title)}</strong><small>${stateNames[s.status]||s.status} · ${stamp(s.updated_at)}</small></button>`).join(''):'<p class="rail-empty">还没有会话<br>创建一项任务，从这里开始。</p>';
 return sessions;
}
function schedulePoll(sid){
 clearTimeout(state.poll);state.poll=setTimeout(async()=>{
  if(state.session?.id!==sid)return;
  try{const s=await api(`/api/client/sessions/${sid}`);if(state.session?.id!==sid)return;state.session=s;renderSession();
   if(['running','stopping'].includes(s.status))schedulePoll(sid);else{await refreshSessions();if(s.status==='awaiting_approval')showPanel('changes');}
  }catch(e){notice(`进度读取中断：${e.message}。可重新打开此会话恢复查看。`);}
 },750);
}
function saveDraft(){state.drafts[state.session?.id||'welcome']={text:$('#prompt').value,attachments:[...state.attachment]};}
function restoreDraft(sid){const d=state.drafts[sid]||{text:'',attachments:[]};$('#prompt').value=d.text;state.attachment=[...d.attachments];renderAttachments();}
async function openSession(sid){
 saveDraft();clearTimeout(state.poll);const v=++state.version;
 const s=await api(`/api/client/sessions/${sid}`);if(v!==state.version)return;
 state.session=s;restoreDraft(sid);localStorage.setItem('harness-client-session',s.id);renderSession(true);await refreshSessions();
 if(v!==state.version)return;
 $('.client-shell').classList.remove('nav-open');
 if(['running','stopping'].includes(s.status))schedulePoll(s.id);
 if(s.status==='awaiting_approval')showPanel('changes');
}
async function newSession(){
 const version=state.version;const s=await api('/api/client/actions/create',{});if(version!==state.version){await refreshSessions();return;}
 await openSession(s.id);if(state.session?.id===s.id){$('#prompt').focus();notice('');}
}
async function send(){
 const text=$('#prompt').value.trim();if(!text)return;
 if(state.sending||state.session&&['running','stopping','awaiting_approval'].includes(state.session.status))return;
 const version=state.version,originalId=state.session?.id,attachments=[...state.attachment],draftText=$('#prompt').value;
 let sid=originalId;state.sending=true;
 $('#send-message').disabled=true;notice('');
 try{
  if(!sid)sid=(await api('/api/client/actions/create',{})).id;
  const s=await api('/api/client/actions/send',{session_id:sid,text,attachments});
  const draft=state.drafts[originalId||'welcome'];
  if(draft?.text===draftText&&JSON.stringify(draft.attachments)===JSON.stringify(attachments))delete state.drafts[originalId||'welcome'];
  if(version===state.version&&state.session?.id===originalId){
   state.session=s;localStorage.setItem('harness-client-session',s.id);
   if($('#prompt').value===draftText&&JSON.stringify(state.attachment)===JSON.stringify(attachments)){$('#prompt').value='';state.attachment=[];renderAttachments();}
   renderSession(true);schedulePoll(s.id);
  }
  await refreshSessions();
 }catch(e){if(version===state.version)throw e;notice('上一会话发送失败：'+e.message);}
 finally{state.sending=false;renderSession();}
}
function showPanel(panel){
 state.panel=panel;$('.client-shell').classList.remove('inspector-hidden');$('.client-shell').classList.add('inspector-open');
 for(const p of ['files','changes','activity'])$('#panel-'+p).hidden=p!==panel;
 document.querySelectorAll('.inspector-tab').forEach(b=>{b.classList.toggle('selected',b.dataset.panel===panel);b.setAttribute('aria-pressed',String(b.dataset.panel===panel));});
}
function renderFiles(){
 const query=$('#file-search').value.toLowerCase().trim();const groups={};
 for(const path of state.files.filter(f=>f.toLowerCase().includes(query))){const slash=path.indexOf('/');const folder=slash<0?'项目根目录':path.slice(0,slash);(groups[folder]??=[]).push(path);}
 $('#file-tree').innerHTML=Object.entries(groups).map(([folder,files])=>`<details class="folder" ${query||['项目根目录','safety_harness'].includes(folder)?'open':''}><summary>${escapeHTML(folder)} <small>${files.length}</small></summary>${files.map(path=>`<button class="file-item ${state.preview?.path===path?'selected':''}" data-path="${escapeHTML(path)}" title="${escapeHTML(path)}"><span class="file-ext">${escapeHTML(path.split('.').pop())}</span><span class="file-name">${escapeHTML(folder==='项目根目录'?path:path.slice(folder.length+1))}</span></button>`).join('')}</details>`).join('')||'<p class="inspector-empty">没有匹配的项目文件。</p>';
}
async function previewFile(path){
 const d=await api('/api/client/file?path='+encodeURIComponent(path));state.preview=d;
 $('#file-preview').hidden=false;$('#preview-path').textContent=d.path;$('#preview-source').textContent=d.content;renderFiles();
}
function renderAttachments(){
 $('#attachments').innerHTML=state.attachment.map(p=>`<div class="attachment"><span>${escapeHTML(p)}</span><button type="button" data-remove="${escapeHTML(p)}" aria-label="移除引用 ${escapeHTML(p)}">移除</button></div>`).join('');
}
function attachPreview(){
 if(!state.preview)return;if(state.attachment.length>=4&&!state.attachment.includes(state.preview.path)){notice('一次最多引用4个文件。');return;}
 if(!state.attachment.includes(state.preview.path))state.attachment.push(state.preview.path);renderAttachments();$('#prompt').focus();
}
function renderChanges(){
 const changes=state.session?.changes||[];
 $('#changes').innerHTML=changes.length?changes.map(c=>`<article class="change"><div class="change-title"><span>${escapeHTML(c.path)}</span><small>${{pending:'待确认',applied:'已应用',rejected:'已拒绝'}[c.status]}</small></div><p>${escapeHTML(c.reason)}</p><div class="diff" tabindex="0" aria-label="文件修改差异">${c.diff.split('\n').map(l=>`<span class="diff-line ${l.startsWith('@@')?'hunk':l.startsWith('+')&&!l.startsWith('+++')?'add':l.startsWith('-')&&!l.startsWith('---')?'remove':''}">${escapeHTML(l)||' '}</span>`).join('')}</div>${c.status==='pending'?`<div class="change-actions"><button class="button primary" data-change="${c.id}" data-approve="yes">应用修改</button><button class="button" data-change="${c.id}" data-approve="no">拒绝</button></div>`:''}</article>`).join(''):'<p class="inspector-empty">暂无修改提案。<br>Agent 提议修改后，可在这里查看差异并确认应用。</p>';
}
function renderActivity(){
 const tools=state.session?.events.filter(e=>e.type==='tool')||[];
 const open=new Set([...document.querySelectorAll('#activities details[open]')].map(e=>e.dataset.event));
 $('#activities').innerHTML=tools.length?tools.map(e=>toolHTML(e,true)).join(''):'<p class="inspector-empty">工具调用将在这里显示。<br>展开后可查看参数和真实返回结果。</p>';
 document.querySelectorAll('#activities details').forEach(e=>e.open=open.has(e.dataset.event));
}
async function decide(id,approve){
 const sid=state.session.id,version=state.version;
 const s=await api('/api/client/actions/decide',{session_id:sid,change_id:id,approve});
 if(version===state.version&&state.session?.id===sid){state.session=s;renderSession();}
 await refreshSessions();
 if(approve){const info=await api('/api/client/info');state.files=info.files;renderFiles();if(state.preview)await previewFile(state.preview.path);}
}
async function showSettings(){
 state.info=await api('/api/client/info');const i=state.info;
 $('#settings-facts').innerHTML=[['后端',i.backend],['模型',i.model],['项目',i.root],['密钥',i.key_configured?'已配置（不显示内容）':'未配置'],['预算',`已预留 ¥${i.reserved_cny.toFixed(2)} / 总上限 ¥${i.budget_cny}`],['每轮限制','最多6次请求，每次2048输出Token']].map(([k,v])=>`<div><dt>${k}</dt><dd>${escapeHTML(v)}</dd></div>`).join('');
 $('#settings-panel').hidden=false;
}
function toggleInspector(){
 const shell=$('.client-shell');
 if(window.innerWidth<=1180){shell.classList.toggle('inspector-open');shell.classList.remove('inspector-hidden');}
 else shell.classList.toggle('inspector-hidden');
}
function hideInspector(){const shell=$('.client-shell');shell.classList.remove('inspector-open');shell.classList.add('inspector-hidden');}
// 绑定真实交互；没有演示用的假会话、假终端或假工具输出。
on('#new-session','click',newSession);on('#refresh-sessions','click',refreshSessions);
on('#sessions','click',e=>{const b=e.target.closest('[data-session]');if(b)return openSession(b.dataset.session);});
on('#composer','submit',e=>{e.preventDefault();return send();});
on('#prompt','keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();return send();}});
on('#stop-agent','click',async()=>{const sid=state.session.id,version=state.version;await api('/api/client/actions/stop',{session_id:sid});if(version===state.version&&state.session?.id===sid){state.session.status='stopping';renderSession();schedulePoll(sid);}});
on('#welcome','click',e=>{const b=e.target.closest('[data-prompt]');if(b){$('#prompt').value=b.dataset.prompt;$('#prompt').focus();}});
on('#file-search','input',renderFiles);on('#file-tree','click',e=>{const b=e.target.closest('[data-path]');if(b)return previewFile(b.dataset.path);});
on('#reference-file','click',attachPreview);on('#close-preview','click',()=>{$('#file-preview').hidden=true;});
on('#attach-file','click',()=>{showPanel('files');$('#file-search').focus();});
on('#attachments','click',e=>{const b=e.target.closest('[data-remove]');if(b){state.attachment=state.attachment.filter(x=>x!==b.dataset.remove);renderAttachments();}});
on('#changes','click',e=>{const b=e.target.closest('[data-change]');if(b)return decide(b.dataset.change,b.dataset.approve==='yes');});
document.querySelectorAll('.inspector-tab').forEach(b=>b.addEventListener('click',()=>showPanel(b.dataset.panel)));
on('#toggle-inspector','click',toggleInspector);on('#close-inspector','click',hideInspector);
on('#open-nav','click',()=>$('.client-shell').classList.add('nav-open'));on('#close-nav','click',()=>$('.client-shell').classList.remove('nav-open'));
on('#settings-button','click',showSettings);on('#close-settings','click',()=>{$('#settings-panel').hidden=true;});
on('#check-runtime','click',async()=>{const b=$('#check-runtime');b.disabled=true;$('#runtime-result').textContent='正在核验隔离引擎…';try{const r=await api('/api/environment');$('#runtime-result').textContent=r.status==='ready'?`Rootless Podman 已就绪 · 镜像 ${r.image_id.slice(0,12)}`:`隔离执行不可用：${r.message}`;}finally{b.disabled=false;}});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();newSession().catch(err=>notice(err.message));}});
async function init(){
 state.info=await api('/api/client/info');state.files=state.info.files;
 $('#project-name').textContent=state.info.workspace;$('#backend-label').textContent=state.info.backend;$('#connection-dot').classList.add('connected');
 renderFiles();const sessions=await refreshSessions();const saved=localStorage.getItem('harness-client-session');
 if(saved&&sessions.some(s=>s.id===saved))await openSession(saved);else renderSession();
}
init().catch(e=>{notice(e.message);$('#agent-status').textContent='未连接，请启动本地客户端服务后刷新。';});
