const $ = (id) => document.getElementById(id);
let settings = null;
let lastKnownCount = 0;
let currentView = 'all';
let currentSort = 'newest';
let currentQuery = '';
let knownTags = [];
const VIEWS=['all','saved','liked','disliked'];
const LAYOUTS=['cards2','cards3','table'];
try { const v=localStorage.getItem('ps.view'); if(VIEWS.includes(v)) currentView=v; } catch {}
try { const s=localStorage.getItem('ps.sort'); if(s==='score'||s==='newest') currentSort=s; } catch {}

function toast(message){
  const el=document.createElement('div');el.className='toast';el.textContent=message;document.body.appendChild(el);setTimeout(()=>el.remove(),3000);
}
function esc(s=''){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
function dateText(s){if(!s)return '—';try{return new Date(s).toLocaleString()}catch{return s}}
function truncate(s,n){s=String(s||'');return s.length>n?s.slice(0,n-1).trimEnd()+'…':s;}
function pct(x){return `${Math.round(Math.max(0,Math.min(1,Number(x)))*100)} %`;}
function sizeText(bytes){if(!bytes)return '';return bytes>1048576?`${(bytes/1048576).toFixed(1)} MB`:`${Math.round(bytes/1024)} kB`;}
async function postJSON(url,body,method='POST'){
  return fetch(url,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
}

/* ------------------------------------------------------------------ settings */

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
  $('embeddingsEnabled').checked=settings.embeddings_enabled!==false;$('embeddingModel').value=settings.embedding_model||'';
  $('libraryAutoDownload').checked=settings.library_auto_download!==false;
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
  return {categories,tags,match_mode:$('matchMode').value,interval_minutes:Number($('intervalMinutes').value),max_results:Number($('maxResults').value),summary_length:$('summaryLength').value,view_mode:$('viewMode').value,
    llm_enabled:$('llmEnabled').checked,llm_base_url:$('llmBaseUrl').value.trim(),llm_model:$('llmModel').value.trim(),llm_api_key:$('llmApiKey').value,llm_temperature:Number($('llmTemperature').value),
    embeddings_enabled:$('embeddingsEnabled').checked,embedding_model:$('embeddingModel').value.trim(),library_auto_download:$('libraryAutoDownload').checked,
    browser_notifications:$('browserNotifications').checked,email_enabled:$('emailEnabled').checked,smtp_host:$('smtpHost').value.trim(),smtp_port:Number($('smtpPort').value),smtp_username:$('smtpUsername').value.trim(),smtp_password:$('smtpPassword').value,smtp_from:$('smtpFrom').value.trim(),smtp_to:$('smtpTo').value.trim(),smtp_starttls:$('smtpStarttls').checked,webhook_enabled:$('webhookEnabled').checked,webhook_url:$('webhookUrl').value.trim()};
}

async function saveSettings(e){
  e.preventDefault();
  const resp=await postJSON('/api/settings',gatherSettings());
  if(!resp.ok){toast((await resp.json()).detail||'Could not save settings');return;}
  settings=await resp.json();$('settingsDialog').close();toast('Settings saved');await loadPapers();
  if(settings.browser_notifications && 'Notification' in window && Notification.permission==='default') Notification.requestPermission();
}

async function rebuildEmbeddings(){
  const btn=$('rebuildEmbeddings');btn.disabled=true;
  const resp=await postJSON('/api/embeddings/rebuild');
  btn.disabled=false;
  if(!resp.ok){toast((await resp.json()).detail||'Could not start');return;}
  toast('Embedding rebuild started in the background');
}

/* ------------------------------------------------------------------ icons + small controls */

const BOOKMARK='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
const THUMB_UP='<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M7 10v11H3V10h4zm2 0l4.2-7.3a1.5 1.5 0 0 1 2.7 1l-1.2 5.3H20a2 2 0 0 1 2 2.4l-1.4 7a2 2 0 0 1-2 1.6H9V10z" fill="currentColor"/></svg>';
const THUMB_DOWN='<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M17 14V3h4v11h-4zm-2 0l-4.2 7.3a1.5 1.5 0 0 1-2.7-1l1.2-5.3H4a2 2 0 0 1-2-2.4l1.4-7A2 2 0 0 1 5.4 3H15v11z" fill="currentColor"/></svg>';

function saveButton(id,saved){
  const label=saved?'Saved – remove from Read later':'Save to Read later';
  return `<button type="button" class="save-btn${saved?' saved':''}" data-id="${esc(id)}" data-saved="${saved?1:0}" title="${label}" aria-label="${label}" aria-pressed="${saved?'true':'false'}">${BOOKMARK}<span>${saved?'Saved':'Read later'}</span></button>`;
}

function reactionBar(id,reaction,compact=false){
  const up=reaction==='like',down=reaction==='dislike';
  return `<div class="reactions${compact?' compact':''}" data-id="${esc(id)}">
    <button type="button" class="react-btn like${up?' active':''}" data-reaction="like" aria-pressed="${up}" title="${up?'Remove like':'Like: useful for my research'}">${THUMB_UP}<span>${up?'Liked':'Like'}</span></button>
    <button type="button" class="react-btn dislike${down?' active':''}" data-reaction="dislike" aria-pressed="${down}" title="${down?'Remove not interested':'Not interested'}">${THUMB_DOWN}<span>Not interested</span></button>
  </div>`;
}

function layout(){const v=settings?.view_mode;return LAYOUTS.includes(v)?v:'cards3';}
function paperClasses(p,base){
  return [base,p.saved?'is-saved':'',p.reaction==='like'?'is-liked':'',p.reaction==='dislike'?'is-disliked':''].filter(Boolean).join(' ');
}

function tagBadges(p){
  const matched=(p.matched_tags||[]).map(t=>`<span class="badge">${esc(t)}</span>`);
  const user=(p.user_tags||[]).map(t=>`<span class="badge user" title="Your tag">${esc(t)}</span>`);
  const score=p.score!==null&&p.score!==undefined?`<span class="badge score" title="Match with what you liked (embedding similarity)">match ${pct(p.score)}</span>`:'';
  const sim=p.similarity!==undefined?`<span class="badge score" title="Similarity to your query">${pct(p.similarity)}</span>`:'';
  return matched.join('')+user.join('')+score+sim;
}

function snippetBlock(p){
  if(!p.snippet)return '';
  const safe=esc(p.snippet).replace(/&lt;mark&gt;/g,'<mark>').replace(/&lt;\/mark&gt;/g,'</mark>');
  return `<p class="snippet">${safe}</p>`;
}

function llmBlock(p){
  return `${p.summary?`<p><span class="label">Summary.</span> ${esc(p.summary)}</p>`:''}
    ${p.why_relevant?`<p><span class="label">Why it matters.</span> ${esc(p.why_relevant)}</p>`:''}
    ${p.key_contribution?`<p><span class="label">Key contribution.</span> ${esc(p.key_contribution)}</p>`:''}
    ${p.limitations?`<p><span class="label">Limitations / uncertainty.</span> ${esc(p.limitations)}</p>`:''}
    ${p.related_to?`<p><span class="label">Related.</span> ${esc(p.related_to)}</p>`:''}`;
}

function abstractBlock(p,open=false){
  return `<details class="abstract"${open?' open':''}><summary>Abstract</summary><p>${esc(p.abstract)}</p></details>`;
}

function notesPreview(p){
  return p.notes?`<div class="notes-preview"><span class="label">Notes.</span> ${esc(p.notes)}</div>`:'';
}

function toolsBlock(p){
  const pdf=p.has_pdf
    ?`<a class="tool-btn pdf-ok" href="/library/${encodeURIComponent(p.arxiv_id)}.pdf" target="_blank" rel="noreferrer" title="Open the PDF stored in your library${p.pdf_size?` (${sizeText(p.pdf_size)})`:''}">📄 PDF in library</a><button type="button" class="tool-btn pdf-remove" data-id="${esc(p.arxiv_id)}" title="Remove PDF from library">✕</button>`
    :`<button type="button" class="tool-btn pdf-btn" data-id="${esc(p.arxiv_id)}" title="Download the PDF into data/library and index its text for search">⬇ Save PDF</button>`;
  return `<div class="tools">
    ${pdf}
    <button type="button" class="tool-btn similar-btn" data-id="${esc(p.arxiv_id)}" title="Find similar papers by meaning">≈ Similar</button>
    <button type="button" class="tool-btn notes-btn${p.notes||p.user_tags?.length?' has-notes':''}" data-id="${esc(p.arxiv_id)}" title="Your notes and tags">✎ Notes${p.user_tags?.length?` (${p.user_tags.length})`:''}</button>
  </div>
  <div class="panel similar-panel hidden"></div>
  <div class="panel notes-panel hidden">
    <label class="field">Notes<textarea class="notes-input" rows="4" placeholder="Why does this matter to you? What to check?">${esc(p.notes||'')}</textarea></label>
    <label class="field">Your tags<input class="tags-input" type="text" list="knownTags" value="${esc((p.user_tags||[]).join(', '))}" placeholder="comma-separated, e.g. thesis, replicate"></label>
    <div class="panel-actions"><button type="button" class="notes-cancel">Cancel</button><button type="button" class="primary notes-save" data-id="${esc(p.arxiv_id)}">Save notes</button></div>
  </div>`;
}

/* ------------------------------------------------------------------ renderers */

function renderPaper(p){
  const authors=(p.authors||[]).slice(0,4).join(', ')+(p.authors?.length>4?' et al.':'');
  return `<article class="${paperClasses(p,'paper')}" data-id="${esc(p.arxiv_id)}">
    <div class="card-head">
      <div class="meta">${esc(dateText(p.published))} · ${esc((p.categories||[]).join(', '))}</div>
      <div class="card-actions">${reactionBar(p.arxiv_id,p.reaction,true)}${saveButton(p.arxiv_id,p.saved)}</div>
    </div>
    <h3>${esc(p.title)}</h3><div class="meta">${esc(authors)}</div><div class="tags">${tagBadges(p)}</div>
    ${snippetBlock(p)}
    ${abstractBlock(p)}
    ${llmBlock(p)}
    ${notesPreview(p)}
    <div class="links"><a href="${esc(p.abs_url)}" target="_blank" rel="noreferrer">arXiv</a>${p.pdf_url?`<a href="${esc(p.pdf_url)}" target="_blank" rel="noreferrer">PDF</a>`:''}${reactionBar(p.arxiv_id,p.reaction)}</div>
    ${toolsBlock(p)}
  </article>`;
}

function renderRow(p){
  const authors=(p.authors||[]).slice(0,3).join(', ')+(p.authors?.length>3?' et al.':'');
  return `<tr class="${paperClasses(p,'row')}" data-id="${esc(p.arxiv_id)}">
    <td class="col-date">${esc(dateText(p.published).split(',')[0])}</td>
    <td class="col-title"><button type="button" class="row-toggle" aria-expanded="false" title="Show abstract, summary, notes and tools">${esc(p.title)}</button><div class="row-sub">${esc(authors)} · ${esc((p.categories||[]).join(', '))}</div>${snippetBlock(p)}</td>
    <td class="col-tags">${tagBadges(p)}</td>
    <td class="col-summary">${esc(truncate(p.key_contribution||p.summary||p.abstract,160))}</td>
    <td class="col-actions"><a href="${esc(p.abs_url)}" target="_blank" rel="noreferrer" title="Open on arXiv">arXiv</a>${saveButton(p.arxiv_id,p.saved)}${reactionBar(p.arxiv_id,p.reaction)}</td>
  </tr>
  <tr class="row-details hidden" data-for="${esc(p.arxiv_id)}"><td colspan="5">
    ${abstractBlock(p,true)}
    ${llmBlock(p)}
    ${notesPreview(p)}
    <div class="links"><a href="${esc(p.abs_url)}" target="_blank" rel="noreferrer">arXiv</a>${p.pdf_url?`<a href="${esc(p.pdf_url)}" target="_blank" rel="noreferrer">PDF</a>`:''}</div>
    ${toolsBlock(p)}
  </td></tr>`;
}

function renderTable(papers){
  return `<table class="paper-table"><thead><tr><th>Date</th><th>Paper</th><th>Tags</th><th>Key contribution</th><th></th></tr></thead><tbody>${papers.map(renderRow).join('')}</tbody></table>`;
}

function updateCounts(c){
  if(!c)return;
  $('savedCount').textContent=c.saved;$('likedCount').textContent=c.liked;$('dislikedCount').textContent=c.disliked;
}

/* ------------------------------------------------------------------ list loading */

async function fetchList(){
  if(currentQuery){
    const mode=$('searchMode').value;
    const data=await fetch(`/api/search?q=${encodeURIComponent(currentQuery)}&mode=${mode}&view=${currentView}&limit=100`).then(r=>r.json());
    const note=$('searchNote');
    if(data.results.length===0)note.textContent=`No results for “${currentQuery}”.`;
    else if((mode==='semantic'||mode==='hybrid')&&!data.semantic_available)note.textContent=`${data.results.length} result(s), text only – embeddings unavailable (check the LLM server in Settings).`;
    else note.textContent=`${data.results.length} result(s) · ${mode} search`;
    note.classList.remove('hidden');
    return data.results;
  }
  $('searchNote').classList.add('hidden');
  return fetch(`/api/papers?limit=200&view=${currentView}&sort=${currentSort}`).then(r=>r.json());
}

async function loadPapers(){
  const view=currentView;
  const papers=await fetchList();
  const mode=layout();
  $('papers').className=mode==='table'?'paper-list':`paper-grid ${mode}`;
  $('papers').innerHTML=mode==='table'?renderTable(papers):papers.map(renderPaper).join('');
  document.querySelectorAll('.layout-btn').forEach(b=>b.classList.toggle('active',b.dataset.layout===mode));
  const empty={all:'emptyState',saved:'emptySaved',liked:'emptyLiked',disliked:'emptyDisliked'};
  for(const [k,id] of Object.entries(empty)) $(id).classList.toggle('hidden',!!currentQuery||k!==view||papers.length!==0);
  if(view!=='all'||currentQuery){return;}
  if(lastKnownCount && papers.length>lastKnownCount && settings?.browser_notifications && 'Notification' in window && Notification.permission==='granted'){
    new Notification('Paper Sentinel',{body:`${papers.length-lastKnownCount} new relevant paper(s)`});
  }
  lastKnownCount=papers.length;
}

function replaceCard(card,paper){
  if(card.classList.contains('row')){
    const details=card.nextElementSibling,wasOpen=details?.classList.contains('row-details')&&!details.classList.contains('hidden');
    if(details?.classList.contains('row-details'))details.remove();
    card.outerHTML=renderRow(paper);
    if(wasOpen){const t=$('papers').querySelector(`.row[data-id="${CSS.escape(paper.arxiv_id)}"] .row-toggle`);if(t)toggleRow(t);}
  }else{
    card.outerHTML=renderPaper(paper);
  }
}

function removeCard(card,emptyId){
  if(card.classList.contains('row')){const d=card.nextElementSibling;if(d?.classList.contains('row-details'))d.remove();}
  card.remove();
  const left=$('papers').querySelector('.paper,.row');if(!left){$('papers').innerHTML='';if(!currentQuery)$(emptyId).classList.remove('hidden');}
}

function cardOf(el){return el.closest('.paper,.row-details');}
function itemOf(el){const c=cardOf(el);return c?.classList.contains('row-details')?c.previousElementSibling:c;}

/* ------------------------------------------------------------------ actions */

async function toggleSaved(btn){
  const id=btn.dataset.id,saved=btn.dataset.saved!=='1',card=itemOf(btn);
  card.querySelectorAll('.save-btn').forEach(b=>b.disabled=true);
  const resp=await postJSON(`/api/papers/${encodeURIComponent(id)}/saved`,{saved});
  if(!resp.ok){card.querySelectorAll('.save-btn').forEach(b=>b.disabled=false);toast('Could not update read-later shelf');return;}
  const paper=await resp.json();
  toast(saved?(settings?.library_auto_download&&!paper.has_pdf?'Saved for later · fetching PDF':'Saved for later'):'Removed from shelf');
  const count=$('savedCount');count.textContent=Math.max(0,Number(count.textContent||0)+(saved?1:-1));
  if(currentView==='saved'&&!saved){removeCard(card,'emptySaved');return;}
  replaceCard(card,paper);
}

async function setReaction(btn){
  const bar=btn.closest('.reactions'),id=bar.dataset.id,card=itemOf(btn);
  const current=card.classList.contains('is-liked')?'like':card.classList.contains('is-disliked')?'dislike':null;
  const reaction=btn.dataset.reaction===current?null:btn.dataset.reaction;
  card.querySelectorAll('.react-btn').forEach(b=>b.disabled=true);
  const resp=await postJSON(`/api/papers/${encodeURIComponent(id)}/reaction`,{reaction});
  if(!resp.ok){card.querySelectorAll('.react-btn').forEach(b=>b.disabled=false);toast('Could not save reaction');return;}
  const paper=await resp.json();
  toast(reaction==='like'?'Marked as liked · match scores will update':reaction==='dislike'?'Marked as not interested':'Reaction removed');
  const c={saved:Number($('savedCount').textContent||0),liked:Number($('likedCount').textContent||0),disliked:Number($('dislikedCount').textContent||0)};
  if(current==='like')c.liked--;if(current==='dislike')c.disliked--;if(reaction==='like')c.liked++;if(reaction==='dislike')c.disliked++;
  updateCounts(c);
  if((currentView==='liked'&&reaction!=='like')||(currentView==='disliked'&&reaction!=='dislike')){removeCard(card,currentView==='liked'?'emptyLiked':'emptyDisliked');return;}
  replaceCard(card,paper);
}

async function downloadPdf(btn){
  const id=btn.dataset.id,card=itemOf(btn);
  btn.disabled=true;btn.textContent='⏳ Downloading…';
  const resp=await postJSON(`/api/papers/${encodeURIComponent(id)}/pdf`);
  if(!resp.ok){btn.disabled=false;btn.textContent='⬇ Save PDF';toast((await resp.json()).detail||'PDF download failed');return;}
  toast('PDF saved to library and indexed for search');
  replaceCard(card,await resp.json());
}

async function removePdf(btn){
  const id=btn.dataset.id,card=itemOf(btn);
  if(!confirm('Remove this PDF from your library?'))return;
  const resp=await postJSON(`/api/papers/${encodeURIComponent(id)}/pdf`,undefined,'DELETE');
  if(!resp.ok){toast('Could not remove PDF');return;}
  toast('PDF removed');replaceCard(card,await resp.json());
}

async function showSimilar(btn){
  const id=btn.dataset.id,card=cardOf(btn),panel=card.querySelector('.similar-panel');
  if(!panel.classList.contains('hidden')){panel.classList.add('hidden');return;}
  panel.innerHTML='<div class="muted">Looking for similar papers…</div>';panel.classList.remove('hidden');
  const resp=await fetch(`/api/papers/${encodeURIComponent(id)}/similar?limit=6`);
  if(!resp.ok){panel.innerHTML=`<div class="status-error">${esc((await resp.json()).detail||'Similar papers unavailable')}</div>`;return;}
  const data=await resp.json();
  if(!data.results.length){panel.innerHTML='<div class="muted">No other embedded papers yet. Run a scan or rebuild embeddings in Settings.</div>';return;}
  panel.innerHTML=`<div class="panel-title">Similar papers</div><ul class="similar-list">${data.results.map(r=>`<li><span class="badge score">${pct(r.similarity)}</span> <a href="${esc(r.abs_url)}" target="_blank" rel="noreferrer">${esc(r.title)}</a>${r.saved?' <span class="mini">★ saved</span>':''}${r.reaction==='like'?' <span class="mini">👍</span>':''}</li>`).join('')}</ul>`;
}

async function toggleNotes(btn){
  const card=cardOf(btn),panel=card.querySelector('.notes-panel');
  const open=panel.classList.toggle('hidden');
  if(!open){
    if(!knownTags.length){try{knownTags=(await fetch('/api/tags').then(r=>r.json())).tags||[];}catch{}}
    $('knownTags').innerHTML=knownTags.map(t=>`<option value="${esc(t)}">`).join('');
    panel.querySelector('.notes-input').focus();
  }
}

async function saveNotes(btn){
  const id=btn.dataset.id,card=cardOf(btn),panel=card.querySelector('.notes-panel');
  const notes=panel.querySelector('.notes-input').value;
  const user_tags=panel.querySelector('.tags-input').value.split(',').map(t=>t.trim()).filter(Boolean);
  btn.disabled=true;
  const resp=await postJSON(`/api/papers/${encodeURIComponent(id)}/notes`,{notes,user_tags});
  btn.disabled=false;
  if(!resp.ok){toast('Could not save notes');return;}
  const paper=await resp.json();
  knownTags=[...new Set([...knownTags,...paper.user_tags])];
  toast('Notes saved');replaceCard(itemOf(btn),paper);
}

async function setLayout(mode){
  if(!LAYOUTS.includes(mode)||mode===layout())return;
  const resp=await postJSON('/api/settings/view-mode',{view_mode:mode});
  if(!resp.ok){toast('Could not change layout');return;}
  settings=await resp.json();await loadPapers();
}

function toggleRow(btn){
  const row=btn.closest('.row'),details=row.nextElementSibling;
  const open=details.classList.toggle('hidden');
  btn.setAttribute('aria-expanded',String(!open));row.classList.toggle('open',!open);
}

function setView(view){
  currentView=view;try{localStorage.setItem('ps.view',view)}catch{}
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===view));
  loadPapers();
}

function setSort(sort){
  currentSort=sort;try{localStorage.setItem('ps.sort',sort)}catch{}
  loadPapers();
}

function runSearch(e){
  if(e)e.preventDefault();
  currentQuery=$('searchInput').value.trim();
  $('searchClear').classList.toggle('hidden',!currentQuery);
  loadPapers();
}

function clearSearch(){
  $('searchInput').value='';currentQuery='';$('searchClear').classList.add('hidden');loadPapers();
}

/* ------------------------------------------------------------------ status + scan */

async function loadStatus(){
  const s=await fetch('/api/status').then(r=>r.json());
  const status=s.scan_status||'idle';
  $('scanStatus').textContent=`Status: ${status}`;updateCounts(s.counts);$('scanStatus').className=status==='error'?'status-error':'';
  $('lastScan').textContent=`Last scan: ${s.last_scan?dateText(s.last_scan):'never'}`;
  if(s.library)$('libraryStat').textContent=`Library: ${s.library.embedded}/${s.library.total} embedded · ${s.library.pdfs} PDF${s.library.pdfs===1?'':'s'}`;
  const err=$('scanError');err.textContent=status==='error'&&s.last_error?`Last error: ${s.last_error}`:'';err.classList.toggle('hidden',!err.textContent);
  $('scanBtn').disabled=status==='running';
  if(status!=='running'&&currentView==='all'&&!currentQuery&&!document.querySelector('.notes-panel:not(.hidden)')) await loadPapers();
}

async function scanNow(){
  $('scanBtn').disabled=true;const r=await fetch('/api/scan',{method:'POST'}).then(r=>r.json());toast(r.status==='busy'?'Scan already running':'Scan started');setTimeout(loadStatus,1500);
}

/* ------------------------------------------------------------------ wiring */

$('settingsBtn').addEventListener('click',async()=>{await loadSettings();$('settingsDialog').showModal();});
$('closeSettings').addEventListener('click',()=>$('settingsDialog').close());$('cancelSettings').addEventListener('click',()=>$('settingsDialog').close());
$('settingsForm').addEventListener('submit',saveSettings);$('scanBtn').addEventListener('click',scanNow);
$('rebuildEmbeddings').addEventListener('click',rebuildEmbeddings);
$('papers').addEventListener('click',e=>{
  const hit=(sel)=>e.target.closest(sel);
  let b;
  if((b=hit('.save-btn')))return toggleSaved(b);
  if((b=hit('.react-btn')))return setReaction(b);
  if((b=hit('.row-toggle')))return toggleRow(b);
  if((b=hit('.pdf-btn')))return downloadPdf(b);
  if((b=hit('.pdf-remove')))return removePdf(b);
  if((b=hit('.similar-btn')))return showSimilar(b);
  if((b=hit('.notes-btn')))return toggleNotes(b);
  if((b=hit('.notes-save')))return saveNotes(b);
  if((b=hit('.notes-cancel')))return cardOf(b).querySelector('.notes-panel').classList.add('hidden');
});
document.querySelectorAll('.layout-btn').forEach(b=>b.addEventListener('click',()=>setLayout(b.dataset.layout)));
document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>setView(t.dataset.view)));
document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===currentView));
$('searchForm').addEventListener('submit',runSearch);
$('searchClear').addEventListener('click',clearSearch);
$('searchMode').addEventListener('change',()=>{if(currentQuery)loadPapers();});
$('searchInput').addEventListener('keydown',e=>{if(e.key==='Escape')clearSearch();});
$('sortMode').value=currentSort;$('sortMode').addEventListener('change',e=>setSort(e.target.value));
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){e.preventDefault();$('searchInput').focus();}});

(async()=>{await loadSettings();await loadPapers();await loadStatus();setInterval(loadStatus,5000);})();
