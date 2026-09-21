const $ = (id) => document.getElementById(id);
let settings = null;
let lastKnownCount = 0;
let currentView = 'all';
try { currentView = localStorage.getItem('ps.view') === 'saved' ? 'saved' : 'all'; } catch {}

function toast(message){
  const el=document.createElement('div');el.className='toast';el.textContent=message;document.body.appendChild(el);setTimeout(()=>el.remove(),3000);
}
function esc(s=''){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function dateText(s){if(!s)return '—';try{return new Date(s).toLocaleString()}catch{return s}}

async function loadSettings(){
  settings=await fetch('/api/settings').then(r=>r.json());
  document.querySelectorAll('input[name="categories"]').forEach(x=>x.checked=settings.categories.includes(x.value));
  const suggested=[...document.querySelectorAll('input[name="suggested_tags"]')];
  suggested.forEach(x=>x.checked=settings.tags.includes(x.value));
  const suggestedVals=new Set(suggested.map(x=>x.value));
  $('customTags').value=settings.tags.filter(t=>!suggestedVals.has(t)).join(', ');
  $('matchMode').value=settings.match_mode;$('intervalMinutes').value=String(settings.interval_minutes);
  $('maxResults').value=settings.max_results;$('summaryLength').value=settings.summary_length;$('viewMode').value=settings.view_mode;
  $('llmEnabled').checked=settings.llm_enabled;$('llmBaseUrl').value=settings.llm_base_url;$('llmModel').value=settings.llm_model;
  $('llmApiKey').value=settings.llm_api_key||'';$('llmTemperature').value=settings.llm_temperature;
  $('browserNotifications').checked=settings.browser_notifications;$('emailEnabled').checked=settings.email_enabled;
  $('smtpHost').value=settings.smtp_host;$('smtpPort').value=settings.smtp_port;$('smtpUsername').value=settings.smtp_username;
  $('smtpPassword').value=settings.smtp_password;$('smtpFrom').value=settings.smtp_from;$('smtpTo').value=settings.smtp_to;
  $('smtpStarttls').checked=settings.smtp_starttls;$('webhookEnabled').checked=settings.webhook_enabled;$('webhookUrl').value=settings.webhook_url;
}

function gatherSettings(){
  const categories=[...document.querySelectorAll('input[name="categories"]:checked')].map(x=>x.value);
  const selected=[...document.querySelectorAll('input[name="suggested_tags"]:checked')].map(x=>x.value);
  const custom=$('customTags').value.split(',').map(x=>x.trim()).filter(Boolean);
  const tags=[...new Set([...selected,...custom])];
  return {categories,tags,match_mode:$('matchMode').value,interval_minutes:Number($('intervalMinutes').value),max_results:Number($('maxResults').value),summary_length:$('summaryLength').value,view_mode:$('viewMode').value,llm_enabled:$('llmEnabled').checked,llm_base_url:$('llmBaseUrl').value.trim(),llm_model:$('llmModel').value.trim(),llm_api_key:$('llmApiKey').value,llm_temperature:Number($('llmTemperature').value),browser_notifications:$('browserNotifications').checked,email_enabled:$('emailEnabled').checked,smtp_host:$('smtpHost').value.trim(),smtp_port:Number($('smtpPort').value),smtp_username:$('smtpUsername').value.trim(),smtp_password:$('smtpPassword').value,smtp_from:$('smtpFrom').value.trim(),smtp_to:$('smtpTo').value.trim(),smtp_starttls:$('smtpStarttls').checked,webhook_enabled:$('webhookEnabled').checked,webhook_url:$('webhookUrl').value.trim()};
}

async function saveSettings(e){
  e.preventDefault();
  const resp=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(gatherSettings())});
  if(!resp.ok){toast((await resp.json()).detail||'Could not save settings');return;}
  settings=await resp.json();$('settingsDialog').close();toast('Settings saved');await loadPapers();
  if(settings.browser_notifications && 'Notification' in window && Notification.permission==='default') Notification.requestPermission();
}

function renderPaper(p){
  const authors=(p.authors||[]).slice(0,4).join(', ')+(p.authors?.length>4?' et al.':'');
  const tags=(p.matched_tags||[]).map(t=>`<span class="badge">${esc(t)}</span>`).join('');
  return `<article class="paper">
    <div class="meta">${esc(dateText(p.published))} · ${esc((p.categories||[]).join(', '))}</div>
    <h3>${esc(p.title)}</h3><div class="meta">${esc(authors)}</div><div class="tags">${tags}</div>
    ${p.summary?`<p><span class="label">Summary.</span> ${esc(p.summary)}</p>`:''}
    ${p.why_relevant?`<p><span class="label">Why it matters.</span> ${esc(p.why_relevant)}</p>`:''}
    ${p.key_contribution?`<p><span class="label">Key contribution.</span> ${esc(p.key_contribution)}</p>`:''}
    ${p.limitations?`<p><span class="label">Limitations / uncertainty.</span> ${esc(p.limitations)}</p>`:''}
    ${p.related_to?`<p><span class="label">Related.</span> ${esc(p.related_to)}</p>`:''}
    <div class="links"><a href="${esc(p.abs_url)}" target="_blank" rel="noreferrer">arXiv</a>${p.pdf_url?`<a href="${esc(p.pdf_url)}" target="_blank" rel="noreferrer">PDF</a>`:''}
      <button type="button" class="save-btn${p.saved?' saved':''}" data-id="${esc(p.arxiv_id)}" data-saved="${p.saved?1:0}" title="${p.saved?'Remove from read-later shelf':'Save to read later'}">${p.saved?'★ Saved':'☆ Read later'}</button>
    </div>
  </article>`;
}

async function loadPapers(){
  const saved=currentView==='saved';
  const papers=await fetch(`/api/papers?limit=200${saved?'&saved=true':''}`).then(r=>r.json());
  $('papers').className='paper-grid '+((settings?.view_mode||'cards')==='compact'?'compact':'');
  $('papers').innerHTML=papers.map(renderPaper).join('');
  $('emptyState').classList.toggle('hidden',saved||papers.length!==0);
  $('emptySaved').classList.toggle('hidden',!saved||papers.length!==0);
  if(saved){$('savedCount').textContent=papers.length;return;}
  if(lastKnownCount && papers.length>lastKnownCount && settings?.browser_notifications && 'Notification' in window && Notification.permission==='granted'){
    new Notification('Paper Sentinel',{body:`${papers.length-lastKnownCount} new relevant paper(s)`});
  }
  lastKnownCount=papers.length;
}

async function toggleSaved(btn){
  const id=btn.dataset.id,saved=btn.dataset.saved!=='1';
  btn.disabled=true;
  const resp=await fetch(`/api/papers/${encodeURIComponent(id)}/saved`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({saved})});
  btn.disabled=false;
  if(!resp.ok){toast('Could not update read-later shelf');return;}
  toast(saved?'Saved for later':'Removed from shelf');
  const count=$('savedCount');count.textContent=Math.max(0,Number(count.textContent||0)+(saved?1:-1));
  if(currentView==='saved'&&!saved){btn.closest('.paper').remove();if(!$('papers').children.length)$('emptySaved').classList.remove('hidden');return;}
  btn.dataset.saved=saved?'1':'0';btn.classList.toggle('saved',saved);btn.textContent=saved?'★ Saved':'☆ Read later';btn.title=saved?'Remove from read-later shelf':'Save to read later';
}

function setView(view){
  currentView=view;try{localStorage.setItem('ps.view',view)}catch{}
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===view));
  loadPapers();
}

async function loadStatus(){
  const s=await fetch('/api/status').then(r=>r.json());
  const status=s.scan_status||'idle';
  $('scanStatus').textContent=`Status: ${status}`;if(s.saved_count!==undefined)$('savedCount').textContent=s.saved_count;$('scanStatus').className=status==='error'?'status-error':'';
  $('lastScan').textContent=`Last scan: ${s.last_scan?dateText(s.last_scan):'never'}`;
  const err=$('scanError');err.textContent=status==='error'&&s.last_error?`Last error: ${s.last_error}`:'';err.classList.toggle('hidden',!err.textContent);
  $('scanBtn').disabled=status==='running';
  if(status!=='running'&&currentView==='all') await loadPapers();
}

async function scanNow(){
  $('scanBtn').disabled=true;const r=await fetch('/api/scan',{method:'POST'}).then(r=>r.json());toast(r.status==='busy'?'Scan already running':'Scan started');setTimeout(loadStatus,1500);
}

$('settingsBtn').addEventListener('click',async()=>{await loadSettings();$('settingsDialog').showModal();});
$('closeSettings').addEventListener('click',()=>$('settingsDialog').close());$('cancelSettings').addEventListener('click',()=>$('settingsDialog').close());
$('settingsForm').addEventListener('submit',saveSettings);$('scanBtn').addEventListener('click',scanNow);
$('papers').addEventListener('click',e=>{const b=e.target.closest('.save-btn');if(b)toggleSaved(b);});
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>setView(t.dataset.view)));
document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===currentView));

(async()=>{await loadSettings();await loadPapers();await loadStatus();setInterval(loadStatus,5000);})();
