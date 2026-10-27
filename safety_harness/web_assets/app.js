/* 页面仅调用有边界的业务API；代码与模型输出始终按文本展示。 */
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = {path:'路径穿越', command:'命令注入', sql:'SQL 注入'};
const statuses = {queued:'等待执行', running:'运行中', completed:'已完成', blocked:'已阻塞', failed:'执行失败', interrupted:'已中断', violation:'触发违规', pass:'未触发违规', harness_error:'测试错误', invalid_harness:'测试格式无效', timeout:'执行超时'};
const kinds = {analyze:'静态分析', run:'配对复现', experiment:'A/B/C 对照实验'};
const state = {boot:null, report:null, case:null, source:'buggy.py', active:null, view:'overview', reportVersion:0, caseVersion:0};
const pct = n => n == null ? '—' : `${(n * 100).toFixed(1)}%`;
const stamp = s => new Date(s).toLocaleString('zh-CN', {hour12:false});
const status = s => statuses[s] || s || '未执行';
function notice(message, good=false) {
  $('#notice').textContent = message;
  $('#notice').className = good ? 'success' : '';
  $('#notice').hidden = !message;
}
async function api(path, options={}) {
  const response = await fetch(path, {...options, headers:{'Content-Type':'application/json', 'X-Harness-CSRF':state.boot?.csrf || '', ...options.headers}, signal:AbortSignal.timeout(path.includes('environment') ? 70000 : 15000)});
  let value;
  try { value = await response.json(); } catch { throw new Error('服务未返回有效结果。请确认工作台服务仍在运行。'); }
  if (!response.ok) throw new Error(value.error || `请求失败（HTTP ${response.status}）`);
  return value;
}
const listen = (selector, type, action) => $(selector).addEventListener(type, event => Promise.resolve(action(event)).catch(e => notice(e.message)));
function jsonDetails(value, label='查看原始 JSON 证据') {
  return `<details class="json-details"><summary>${esc(label)}</summary><pre>${esc(JSON.stringify(value,null,2))}</pre></details>`;
}
function changeView(view) {
  if (!['overview','workbench','experiments'].includes(view)) view = 'overview';
  state.view = view;
  document.querySelectorAll('.view').forEach(el => el.hidden = el.id !== `view-${view}`);
  document.querySelectorAll('.nav').forEach(el => {
    el.classList.toggle('active', el.dataset.view === view);
    if (el.dataset.view === view) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current');
  });
  $('#breadcrumb').textContent = {overview:'评测总览',workbench:'案例工作台',experiments:'实验任务'}[view];
  history.replaceState(null,'',`#${view}`);
  if (view === 'experiments' && state.boot) loadJobs().catch(e => notice(e.message));
}
function setBusy(busy) {
  ['#analyze-case','#run-case','#start-experiment'].forEach(s => $(s).disabled = busy || (s === '#start-experiment' && !state.boot?.key_configured));
}
async function bootstrap() {
  state.boot = await api('/api/bootstrap');
  $('#key-state').textContent = state.boot.key_configured ? '模型密钥已配置' : '模型密钥尚未配置';
  $('#budget-note').textContent = `共享账本已预留 ¥${state.boot.reserved_cny.toFixed(2)}。此处设置总上限，不是本轮新增额度；预留不等于实际账单。`;
  setBusy(Boolean(state.active));
}
async function loadReport(id) {
  const version = ++state.reportVersion;
  $('#overview-loading').hidden = false;
  $('#overview-data').hidden = true;
  $('#trial-detail').hidden = true;
  try {
    const report = await api(`/api/reports/${encodeURIComponent(id)}`);
    if (version !== state.reportVersion) return;
    state.report = report;
    const summary = report.summary;
    if (!summary) throw new Error('该批次缺少预算内统计，请检查评测文件。');
    $('#summary-strip').innerHTML = [
      ['完整试验',report.full_summary.records,'次'],['模型响应',report.api_responses,'份'],
      ['网络失败',report.ambiguous_requests,'次'],['证据一致性',report.verification.status === 'passed' ? '已核验' : '未通过','']
    ].map(([label,num,unit]) => `<div class="metric"><span>${label}</span><strong>${esc(num)}<small>${unit}</small></strong></div>`).join('');
    const labels = {A:'直接生成', B:'Bandit 告警引导', C:'告警 + AST 上下文'};
    $('#comparison').innerHTML = summary.groups.map(g => `<div class="chart-row"><div class="chart-label"><span>${g.group} · ${labels[g.group]}</span><strong>${pct(g.confirmed_rate)}<small>${g.confirmed}/${g.denominator}</small></strong></div><svg role="img" aria-label="${g.group}组配对复现率${pct(g.confirmed_rate)}" viewBox="0 0 100 3" preserveAspectRatio="none"><rect class="bar-track" width="100" height="3" rx="1.5"/><rect class="bar-${g.group}" width="${Math.max(0,Math.min(100,(g.confirmed_rate || 0)*100))}" height="3" rx="1.5"/></svg></div>`).join('');
    $('#comparison-note').textContent = report.excluded.length ? `上图使用预算内比较，剔除 ${report.excluded.length} 个超调用上限的匹配块；下方样本表仍保留全量结果。` : '所有匹配块均在调用上限内。一次复现需同时满足缺陷触发与修复版通过。';
    const groups = Object.fromEntries(summary.groups.map(g => [g.group,g]));
    $('#finding').textContent = groups.B?.confirmed_rate === groups.C?.confirmed_rate ? '本轮 B、C 复现率持平，尚未观察到 AST 上下文带来的额外收益。' : '不同信息条件下的复现率存在差异；小样本结果仅用于描述，不代表普遍提升。';
    $('#evidence-facts').innerHTML = `<div><dt>统计口径</dt><dd>预算内配对复现</dd></div><div><dt>成功响应费用上界</dt><dd>¥${report.cost_upper.toFixed(3)}</dd></div><div><dt>输入 / 输出 Token</dt><dd>${report.usage.prompt_tokens.toLocaleString()} / ${report.usage.completion_tokens.toLocaleString()}</dd></div><div><dt>费用限制</dt><dd>不含失败请求未知用量</dd></div>`;
    renderRows();
    const external = report.static;
    $('#external-result').hidden = !external;
    if (external) $('#external-result').innerHTML = `<div><h2>外部样本 · SecurityEval</h2><p>仅静态分析，未执行目标。风险线索覆盖不能解释为动态漏洞检出率。</p></div><div><div class="external-score"><span>Bandit 告警<small>至少一条静态告警</small></span><strong>${external.bandit_any_alert}<small>/ ${external.samples} 个样本</small></strong></div><div class="external-score"><span>Bandit + AST<small>至少一种风险线索</small></span><strong>${external.either_static_signal}<small>/ ${external.samples} 个样本</small></strong></div></div>`;
    $('#overview-loading').hidden = true;
    $('#overview-data').hidden = false;
  } catch(e) {
    if (version === state.reportVersion) $('#overview-loading').textContent = `${e.message} 可重新选择批次重试。`;
    throw e;
  }
}
function renderRows() {
  const type = $('#result-filter').value;
  const rows = state.report.cases.filter(row => type === 'all' || row.sample.startsWith(`${type}-`));
  $('#result-rows').innerHTML = rows.map(row => `<tr><td>${esc(row.sample)}</td><td>${names[row.sample.split('-')[0]]}</td>${['A','B','C'].map(g => {
    const items = row[g], hits = items.filter(i=>i.confirmed).length;
    return `<td><button class="result-link ${hits < items.length ? 'warn' : ''}" data-trial="${esc(row.sample)}" data-group="${g}">${hits}/${items.length} 复现</button></td>`;
  }).join('')}</tr>`).join('');
}
async function loadTrial(caseId, group, repeat=0) {
  const host = $('#trial-detail');
  const runId = state.report.id;
  host.hidden = false;
  host.textContent = '正在读取原始试验记录…';
  try {
    const d = await api(`/api/reports/${runId}/trial?case=${encodeURIComponent(caseId)}&group=${group}&repeat=${repeat}`);
    if (state.report.id !== runId) return;
    const repetitions = state.report.cases.find(r => r.sample===caseId)[group];
    host.innerHTML = `<div class="panel-heading"><h2>${esc(caseId)} · ${group} 组原始记录</h2><label>重复轮次 <select id="trial-repeat">${repetitions.map(r=>`<option value="${r.repeat}" ${r.repeat===Number(repeat)?'selected':''}>第 ${r.repeat+1} 次</option>`).join('')}</select></label></div><p class="muted">${d.record.confirmed?'配对复现成功':'未形成配对复现'} · 缺陷版：${status(d.record.buggy?.status)} · 修复版：${status(d.record.fixed?.status)}</p>${d.tests.map(t=>`<div class="test-evidence"><p>第 ${t.attempt} 次生成 · ${status(t.status)}</p><div class="code-panel"><pre>${esc(t.code)}</pre></div></div>`).join('')}${jsonDetails(d.record)}`;
    listen('#trial-repeat','change',e=>loadTrial(caseId,group,Number(e.target.value)));
  } catch(e) {host.textContent = e.message;}
  host.scrollIntoView({block:'start', behavior:'instant'});
}
function renderCases() {
  const query = $('#case-search').value.toLowerCase().trim(), type=$('#case-filter').value;
  const cases = state.boot.cases.filter(c=>(type==='all'||c.category===type) && `${c.id} ${names[c.category]}`.toLowerCase().includes(query));
  $('#case-list').innerHTML = cases.length ? cases.map(c=>`<button class="case-item ${state.case?.info.id===c.id?'active':''}" data-case="${esc(c.id)}"><strong>${esc(c.id)}</strong><small>${names[c.category]} · ${c.split==='dev'?'开发':'评测'}</small></button>`).join('') : '<p class="empty">没有匹配样本</p>';
}
function renderSource() {
  $('#source-code').textContent = state.case.files[state.source];
  $('#code-filename').textContent = state.source;
  document.querySelectorAll('.tab').forEach(t=>{t.classList.toggle('active',t.dataset.source===state.source);t.setAttribute('aria-pressed',String(t.dataset.source===state.source));});
  $('#analyze-case').textContent = state.source==='fixed.py' ? '分析修复版' : '分析缺陷版';
}
async function loadCase(id) {
  const version=++state.caseVersion;
  const data=await api(`/api/cases/${encodeURIComponent(id)}`);
  if(version!==state.caseVersion)return;
  state.case=data; state.source='buggy.py';
  $('#case-title').textContent=data.info.id;
  $('#case-meta').textContent=`${names[data.info.category]} · 人工构造配对样本`;
  $('#case-split').textContent=data.info.split==='dev'?'开发集':'评测集';
  $('#case-requirement').textContent=data.info.requirement;
  $('#harness-editor').value=data.files['reference.py'];
  $('#case-result').hidden=true; $('#case-job-status').hidden=true;
  renderCases();renderSource();
}
function renderAnalysis(result) {
  const findings=result.bandit.findings;
  const functions=result.files.flatMap(f=>f.functions).filter(f=>f.sensitive_calls.length);
  return `<h2>静态分析结果</h2><p class="muted">${findings.length} 条 Bandit 告警 · ${functions.length} 个含敏感调用的函数。告警仅提供线索。</p>${result.files.some(f=>f.errors.length)?'<p class="warning">源代码存在语法错误，分析不完整。</p>':''}${result.bandit.status!=='ok'?'<p class="warning">Bandit 执行异常，告警结果不完整。</p>':''}${findings.map(f=>`<div class="analysis-item"><strong>${esc(f.test_id)} · 第 ${f.line_number} 行 · ${esc(f.issue_severity)}</strong><p>${esc(f.issue_text)}</p></div>`).join('') || '<p class="muted">Bandit 未产生告警，不等于代码安全。</p>'}${functions.map(f=>`<div class="analysis-item"><strong>${esc(f.signature)}</strong><p>${f.sensitive_calls.map(c=>`${esc(c.call)} · ${names[c.category]} · 第${c.line}行`).join('；')}</p></div>`).join('')}${jsonDetails(result)}`;
}
function renderPair(result) {
  return `<h2>${result.confirmed?'已完成配对复现':'本次未形成配对复现'}</h2><p class="muted">${esc(result.note)}</p><div class="paired"><div>缺陷版<strong class="${result.buggy.status==='violation'?'warning':''}">${status(result.buggy.status)}</strong></div><div>修复版<strong class="${result.fixed.status==='pass'?'positive':'warning'}">${status(result.fixed.status)}</strong></div></div><p class="footnote">未触发仅表示本次测试未观察到规定的违规，不代表目标不存在漏洞。</p>${jsonDetails(result)}`;
}
function renderJobResult(job) {
  if (!job.result) return '';
  if(job.kind==='analyze')return renderAnalysis(job.result);
  if(job.kind==='run')return renderPair(job.result);
  const s=job.result;
  return `<h2>${job.status==='completed'?'本轮统计':'已完成部分的统计'}</h2><p class="muted">${s.records}/${job.total} 次试验完成 · ${s.complete_abc_blocks} 个完整 A/B/C 匹配块${job.status!=='completed'?'。未完成批次不能作为完整对比成绩。':''}</p><div class="table-scroll"><table><thead><tr><th>组别</th><th>配对复现</th><th>可运行</th><th>修复版有效判定</th><th>误报</th></tr></thead><tbody>${s.groups.map(g=>`<tr><td>${g.group}</td><td>${g.confirmed}/${g.denominator}</td><td>${g.runnable}/${g.denominator}</td><td>${g.negative_valid_evaluations}/${g.negative_denominator}</td><td>${g.false_positives}</td></tr>`).join('')}</tbody></table></div>${jsonDetails(s,'查看本轮统计 JSON')}`;
}
async function submitJob(params) {
  notice('');setBusy(true);
  try {
    const {id}=await api('/api/jobs',{method:'POST',body:JSON.stringify(params)});
    state.active=id;sessionStorage.setItem('harness-active-job',id);
    await pollJob(id);
  } catch(e) {setBusy(Boolean(state.active));throw e;}
}
async function pollJob(id) {
  try {
    const job=await api(`/api/jobs/${id}`);
    const active=['queued','running'].includes(job.status);
    if(job.kind!=='experiment' && job.params.case_id===state.case?.info.id) {
      const box=$('#case-job-status');box.hidden=false;box.className=`job-inline ${job.status==='blocked'?'blocked':''}`;
      box.textContent=`${kinds[job.kind]} · ${status(job.status)}。${job.message}`;
      if(job.result){$('#case-result').hidden=false;$('#case-result').innerHTML=renderJobResult(job);}
    }
    if(state.view==='experiments')await loadJobs();
    if(active){state.active=id;setBusy(true);setTimeout(()=>pollJob(id),1600);}
    else {
      state.active=null;sessionStorage.removeItem('harness-active-job');setBusy(false);
      notice(`${kinds[job.kind]}${status(job.status)}。${job.message}`,job.status==='completed');
      await bootstrap();
    }
  } catch(e) {
    state.active=null;setBusy(false);
    notice(`进度连接中断：${e.message}。任务可能仍在后台运行，请在“实验任务”中刷新查看。`);
  }
}
async function loadJobs() {
  const jobs=await api('/api/jobs');
  $('#jobs-count').textContent=`${jobs.length} 个任务`;
  $('#jobs-list').innerHTML=jobs.length?jobs.map(job=>`<div class="job-row"><div><strong>${kinds[job.kind]}${job.params.case_id?' · '+esc(job.params.case_id):' · '+(job.params.split==='dev'?'开发集':'评测集')}<span class="job-status ${['blocked','failed','interrupted'].includes(job.status)?'warning':''}">${status(job.status)}</span></strong><small>${stamp(job.created_at)} · ${esc(job.id.slice(0,8))}</small>${job.kind==='experiment'?`<progress max="${job.total}" value="${job.completed}" aria-label="已完成试验"></progress><span class="job-progress-label">${job.completed} / ${job.total} 次试验</span>`:''}<small>${esc(job.message)}</small></div><button class="button small" data-job="${job.id}">查看结果</button></div>`).join(''):'<p class="empty">暂无网页任务。可先在案例工作台运行一次分析或配对复现。</p>';
  const active=jobs.find(j=>['queued','running'].includes(j.status));
  if(active && !state.active){state.active=active.id;setBusy(true);setTimeout(()=>pollJob(active.id),1600);}
}
async function showJob(id) {
  const job=await api(`/api/jobs/${id}`);
  const box=$('#job-detail');box.hidden=false;
  box.innerHTML=`<div class="panel-heading"><h2>${kinds[job.kind]} · ${status(job.status)}</h2><span class="tag">${esc(job.id.slice(0,8))}</span></div><p class="muted">${esc(job.message)}</p>${renderJobResult(job) || '<p>尚无最终结果。运行中的试验进度见任务列表。</p>'}${jsonDetails({id:job.id,params:job.params,status:job.status,created_at:job.created_at,updated_at:job.updated_at},'查看任务配置')}`;
  box.scrollIntoView({block:'start',behavior:'instant'});
}
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>changeView(b.dataset.view)));
window.addEventListener('hashchange',()=>changeView(location.hash.slice(1)));
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>{state.source=b.dataset.source;if(state.case)renderSource();}));
listen('#run-select','change',e=>loadReport(e.target.value));
listen('#result-filter','change',renderRows);
listen('#result-rows','click',e=>{const b=e.target.closest('[data-trial]');if(b)return loadTrial(b.dataset.trial,b.dataset.group);});
listen('#case-search','input',renderCases);listen('#case-filter','change',renderCases);
listen('#case-list','click',e=>{const b=e.target.closest('[data-case]');if(b)return loadCase(b.dataset.case);});
listen('#reset-harness','click',()=>{$('#harness-editor').value=state.case.files['reference.py'];});
listen('#analyze-case','click',()=>submitJob({kind:'analyze',case_id:state.case.info.id,variant:state.source==='fixed.py'?'fixed':'buggy'}));
listen('#run-case','click',()=>submitJob({kind:'run',case_id:state.case.info.id,harness:$('#harness-editor').value}));
listen('#check-env','click',async()=>{
  const b=$('#check-env');b.disabled=true;b.textContent='正在检查…';
  try{const d=await api('/api/environment');notice(d.status==='ready'?`隔离环境已就绪：rootless Podman，镜像 ${d.image_id.slice(0,12)}。每次执行仍会重新验证隔离配置。`:`动态执行不可用：${d.message}`,d.status==='ready');}
  finally{b.disabled=false;b.textContent='检查运行环境';}
});
listen('#experiment-form','submit',e=>{e.preventDefault();return submitJob({kind:'experiment',split:$('#split-select').value,input_price:Number($('#input-price').value),output_price:Number($('#output-price').value),budget:Number($('#budget').value)});});
listen('#refresh-jobs','click',loadJobs);
listen('#jobs-list','click',e=>{const b=e.target.closest('[data-job]');if(b)return showJob(b.dataset.job);});
listen('#export-summary','click',()=>{
  if(!state.report)return;
  const blob=new Blob([JSON.stringify(state.report,null,2)],{type:'application/json'}), url=URL.createObjectURL(blob), a=document.createElement('a');
  a.href=url;a.download=`${state.report.id}-summary.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
async function init() {
  changeView(location.hash.slice(1));
  await bootstrap();
  $('#run-select').innerHTML=state.boot.runs.map(r=>`<option value="${r.id}">${esc(r.label)}</option>`).join('');
  renderCases();
  if(state.boot.runs.length)await loadReport(state.boot.runs[0].id);
  else{$('#overview-loading').textContent='本地没有历史评测统计。可前往实验任务启动开发集评测。';$('#run-select').disabled=true;}
  if(state.boot.cases.length)await loadCase(state.boot.cases[0].id);
  await loadJobs();
  const saved=sessionStorage.getItem('harness-active-job');
  if(saved && !state.active && /^[0-9a-f]{32}$/.test(saved)){state.active=saved;setBusy(true);await pollJob(saved);}
}
init().catch(e=>{notice(e.message);$('#overview-loading').textContent='工作台数据加载失败。请确认服务可用后刷新页面。';});
