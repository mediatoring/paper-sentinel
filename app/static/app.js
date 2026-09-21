const $ = (id) => document.getElementById(id);
let settings = null;
let lastKnownCount = 0;
let currentView = 'inbox';
let currentSort = 'newest';
let currentQuery = '';
let knownTags = [];
let activeTags = [];
const expandedIds = new Set();
try { activeTags=JSON.parse(localStorage.getItem('ps.tags')||'[]'); if(!Array.isArray(activeTags)) activeTags=[]; } catch { activeTags=[]; }
const VIEWS=['inbox','saved','liked','disliked','all'];
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

// Custom chips: values typed into an input become toggleable chips next to the built-in ones.
function renderCustomChips(containerId,name,values){
  $(containerId).innerHTML=values.map(v=>`<label class="chip custom"><input type="checkbox" name="${name}" value="${esc(v)}" checked><span>${esc(v)}<b class="chip-remove" role="button" tabindex="0" title="Remove" aria-label="Remove ${esc(v)}">×</b></span></label>`).join('');
}
document.addEventListener('click',e=>{
  const x=e.target.closest('.chip-remove');if(!x)return;
  e.preventDefault();e.stopPropagation();x.closest('.chip').remove();
});
document.addEventListener('keydown',e=>{
  if((e.key==='Enter'||e.key===' ')&&e.target.classList?.contains('chip-remove')){e.preventDefault();e.target.closest('.chip').remove();}
});
function customChipValues(name,checkedOnly=true){
  return [...document.querySelectorAll(`input[name="${name}"]${checkedOnly?':checked':''}`)].map(x=>x.value);
}
function addCustomChips(containerId,name,inputId,builtinName){
  const input=$(inputId);
  const typed=input.value.split(',').map(x=>x.trim()).filter(Boolean);
  if(!typed.length)return;
  const builtin=new Map([...document.querySelectorAll(`input[name="${builtinName}"]`)].map(x=>[x.value.toLowerCase(),x]));
  const existing=customChipValues(name,false);
  const lower=new Set(existing.map(v=>v.toLowerCase()));
  const added=[];
  for(const v of typed){
    const b=builtin.get(v.toLowerCase());
    if(b){b.checked=true;continue;}
    if(lower.has(v.toLowerCase()))continue;
    lower.add(v.toLowerCase());added.push(v);
  }
  renderCustomChips(containerId,name,[...existing,...added]);
  input.value='';
}
function wireChipInput(inputId,containerId,name,builtinName){
  $(inputId).addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===','){e.preventDefault();addCustomChips(containerId,name,inputId,builtinName);}});
  $(inputId).addEventListener('blur',()=>addCustomChips(containerId,name,inputId,builtinName));
}

async function loadSettings(){
  settings=await fetch('/api/settings').then(r=>r.json());
  const catInputs=[...document.querySelectorAll('input[name="categories"]')];
  catInputs.forEach(x=>x.checked=settings.categories.includes(x.value));
  const knownCats=new Set(catInputs.map(x=>x.value));
  renderCustomChips('customCategoryChips','custom_categories',settings.categories.filter(c=>!knownCats.has(c)));
  $('customCategories').value='';
  const suggested=[...document.querySelectorAll('input[name="suggested_tags"]')];
  suggested.forEach(x=>x.checked=settings.tags.includes(x.value));
  const suggestedVals=new Set(suggested.map(x=>x.value));
  renderCustomChips('customTagChips','custom_tags',settings.tags.filter(t=>!suggestedVals.has(t)));
  $('customTags').value='';
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
  addCustomChips('customCategoryChips','custom_categories','customCategories','categories');
  addCustomChips('customTagChips','custom_tags','customTags','suggested_tags');
  const checked=[...document.querySelectorAll('input[name="categories"]:checked')].map(x=>x.value);
  const categories=[...new Set([...checked,...customChipValues('custom_categories')])];
  const selected=[...document.querySelectorAll('input[name="suggested_tags"]:checked')].map(x=>x.value);
  const tags=[...new Set([...selected,...customChipValues('custom_tags')])];
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

const I={
  file:'<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M6 2h8l5 5v15H6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 2v5h5M9 13h6M9 17h6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  download:'<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v3h16v-3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  similar:'<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="9" cy="12" r="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="15" cy="12" r="5.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
  note:'<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path d="M4 20h4l11-11-4-4L4 16z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M13 7l4 4" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
  x:'<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  chev:'<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  clock:'<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
};
const CHECK='<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function readButton(id,read,compact=false){
  const label=read?'Mark as unread':'Mark as read (removes it from the inbox)';
  return `<button type="button" class="read-btn${read?' active':''}${compact?' compact':''}" data-id="${esc(id)}" data-read="${read?1:0}" title="${label}" aria-label="${label}" aria-pressed="${read?'true':'false'}">${CHECK}<span>${read?'Read':'Read'}</span></button>`;
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

const MATCH_TIP='Match = how close this paper is to the papers you liked (thumbs up). It is computed from embeddings: the topic vector of this paper compared with the average of your liked papers, pushed away from papers you marked Not interested. 100 % = same topic as your likes, 0 % = unrelated or close to your dislikes. It updates after every reaction. Choose Sort → Best match to rank by it.';
const SIM_TIP='Similarity by meaning (embeddings) to your search query or to the paper you asked for. Higher = closer topic.';

function tagBadges(p){
  const matched=(p.matched_tags||[]).map(t=>`<span class="badge">${esc(t)}</span>`);
  const user=(p.user_tags||[]).map(t=>`<span class="badge user" title="Your tag">${esc(t)}</span>`);
  const score=p.score!==null&&p.score!==undefined?`<span class="badge score tip" tabindex="0" data-tip="${esc(MATCH_TIP)}">match ${pct(p.score)}</span>`:'';
  const sim=p.similarity!==undefined?`<span class="badge score tip" tabindex="0" data-tip="${esc(SIM_TIP)}">${pct(p.similarity)}</span>`:'';
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
    ?`<a class="tool-btn pdf-ok" href="/library/${encodeURIComponent(p.arxiv_id)}.pdf" target="_blank" rel="noreferrer" title="Open the PDF stored in your library${p.pdf_size?` (${sizeText(p.pdf_size)})`:''}">${I.file}<span>PDF in library</span></a><button type="button" class="tool-btn pdf-remove" data-id="${esc(p.arxiv_id)}" title="Remove PDF from library" aria-label="Remove PDF from library">${I.x}</button>`
    :`<button type="button" class="tool-btn pdf-btn" data-id="${esc(p.arxiv_id)}" title="Download the PDF into data/library and index its text for search">${I.download}<span>Save PDF</span></button>`;
  return `<div class="tools">
    ${pdf}
    <button type="button" class="tool-btn similar-btn" data-id="${esc(p.arxiv_id)}" title="Find similar papers by meaning">${I.similar}<span>Similar</span></button>
    <button type="button" class="tool-btn notes-btn${p.notes||p.user_tags?.length?' has-notes':''}" data-id="${esc(p.arxiv_id)}" title="Your notes and tags">${I.note}<span>Notes${p.user_tags?.length?` (${p.user_tags.length})`:''}</span></button>
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
      <div class="card-actions">${reactionBar(p.arxiv_id,p.reaction,true)}${readButton(p.arxiv_id,!!p.read_at,true)}${saveButton(p.arxiv_id,p.saved)}</div>
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

// null = automatic (unhandled papers open, handled ones collapsed to their title); true/false = forced by the toggle
let expandAll=null;

function renderListItem(p){
  const authors=(p.authors||[]).join(', ');
  const hasAi=!!(p.summary||p.why_relevant||p.key_contribution||p.limitations||p.related_to);
  const handled=!!(p.saved||p.reaction||p.read_at);
  const open=expandedIds.has(p.arxiv_id)||(expandAll===null?!handled:expandAll);
  return `<article class="${paperClasses(p,'paper list-item')}${open?' open':''}" data-id="${esc(p.arxiv_id)}">
    <div class="list-head">
      <button type="button" class="list-toggle" aria-expanded="${open}" title="${open?'Collapse':'Expand'}">
        <span class="chev" aria-hidden="true">${I.chev}</span>
        <span class="list-title">${esc(p.title)}</span>
      </button>
      <div class="list-head-meta">
        ${p.reaction==='like'?`<span class="mini icon ok" title="Liked">${THUMB_UP}</span>`:''}${p.reaction==='dislike'?`<span class="mini icon" title="Not interested">${THUMB_DOWN}</span>`:''}${p.saved?`<span class="mini icon warn" title="Read later">${BOOKMARK}</span>`:''}${p.has_pdf?`<span class="mini icon" title="PDF in library">${I.file}</span>`:''}${p.read_at?`<span class="mini icon" title="Read">${CHECK}</span>`:''}
        ${p.score!==null&&p.score!==undefined?`<span class="badge score tip small" tabindex="0" data-tip="${esc(MATCH_TIP)}">${pct(p.score)}</span>`:''}
        <span class="meta">${esc(dateText(p.published).split(',')[0])}</span>
      </div>
    </div>
    <div class="list-body${open?'':' hidden'}">
      <div class="list-main">
        <div class="meta">${esc(dateText(p.published))} · ${esc((p.categories||[]).join(', '))}</div>
        <div class="meta authors">${esc(authors)}</div>
        <div class="tags">${tagBadges(p)}</div>
        ${snippetBlock(p)}
        <p class="abstract-full">${esc(p.abstract)}</p>
        ${hasAi?`<details class="ai-summary"><summary>AI summary</summary>${llmBlock(p)}</details>`:''}
        ${notesPreview(p)}
      </div>
      <aside class="list-side">
        ${saveButton(p.arxiv_id,p.saved)}
        ${reactionBar(p.arxiv_id,p.reaction)}
        ${readButton(p.arxiv_id,!!p.read_at)}
        <div class="links"><a href="${esc(p.abs_url)}" target="_blank" rel="noreferrer">arXiv</a>${p.pdf_url?`<a href="${esc(p.pdf_url)}" target="_blank" rel="noreferrer">PDF</a>`:''}</div>
      </aside>
      <div class="list-foot">${toolsBlock(p)}</div>
    </div>
  </article>`;
}

function toggleListItem(btn){
  const card=btn.closest('.list-item'),body=card.querySelector('.list-body'),id=card.dataset.id;
  const open=body.classList.toggle('hidden');
  card.classList.toggle('open',!open);btn.setAttribute('aria-expanded',String(!open));btn.title=open?'Expand':'Collapse';
  if(open)expandedIds.delete(id);else expandedIds.add(id);
}

function renderList(papers){
  return papers.map(renderListItem).join('');
}

function updateListBar(papers){
  const mode=layout();
  $('listBar').classList.toggle('hidden',papers.length===0);
  $('listInfo').textContent=`${papers.length} paper${papers.length===1?'':'s'}${mode==='table'?' · click a title to collapse or expand':''}${currentView==='inbox'?' · any action moves a paper out of the inbox':''}`;
  const anyClosed=[...document.querySelectorAll('#papers .list-item')].some(c=>!c.classList.contains('open'));
  $('expandAllBtn').classList.toggle('hidden',mode!=='table');$('expandAllBtn').textContent=anyClosed?'Expand all':'Collapse all';
  $('markAllRead').classList.toggle('hidden',currentView!=='inbox'||!!currentQuery);
}

function toggleExpandAll(){
  const anyClosed=[...document.querySelectorAll('#papers .list-item')].some(c=>!c.classList.contains('open'));
  expandAll=anyClosed;
  if(!expandAll)expandedIds.clear();
  document.querySelectorAll('#papers .list-item').forEach(card=>{
    card.querySelector('.list-body').classList.toggle('hidden',!expandAll);card.classList.toggle('open',expandAll);
    card.querySelector('.list-toggle').setAttribute('aria-expanded',String(expandAll));
    card.querySelectorAll('details.ai-summary').forEach(d=>d.open=expandAll);
  });
  const b=$('expandAllBtn');if(b)b.textContent=expandAll?'Collapse all':'Expand all';
  expandAll=null;
}

function updateCounts(c){
  if(!c)return;
  $('savedCount').textContent=c.saved;$('likedCount').textContent=c.liked;$('dislikedCount').textContent=c.disliked;
  if(c.inbox!==undefined)$('inboxCount').textContent=c.inbox;if(c.total!==undefined)$('totalCount').textContent=c.total;
}
function bumpInbox(delta){const el=$('inboxCount');el.textContent=Math.max(0,Number(el.textContent||0)+delta);}

/* ------------------------------------------------------------------ list loading */

async function fetchList(){
  if(currentQuery){
    const mode=$('searchMode').value;
    const data=await fetch(`/api/search?q=${encodeURIComponent(currentQuery)}&mode=${mode}&view=${currentView}&limit=100${tagParam()}`).then(r=>r.json());
    const note=$('searchNote');
    if(data.results.length===0)note.textContent=`No results for “${currentQuery}”.`;
    else if((mode==='semantic'||mode==='hybrid')&&!data.semantic_available)note.textContent=`${data.results.length} result(s), text only – embeddings unavailable (check the LLM server in Settings).`;
    else note.textContent=`${data.results.length} result(s) · ${mode} search`;
    note.classList.remove('hidden');
    return data.results;
  }
  $('searchNote').classList.add('hidden');
  return fetch(`/api/papers?limit=200&view=${currentView}&sort=${currentSort}${tagParam()}`).then(r=>r.json());
}

function tagParam(){return activeTags.length?`&tags=${encodeURIComponent(activeTags.join(','))}`:'';}

/* ------------------------------------------------------------------ tag filter chips */

let tagCountsKey='';
async function loadTagChips(force=false){
  const key=currentView;
  const data=await fetch(`/api/tag-counts?view=${key}`).then(r=>r.json()).catch(()=>null);
  if(!data)return;
  const sig=JSON.stringify([key,data]);
  if(!force&&sig===tagCountsKey)return;
  tagCountsKey=sig;
  const known=new Set([...data.matched,...data.user].map(t=>t.tag.toLowerCase()));
  activeTags=activeTags.filter(t=>known.has(t.toLowerCase()));
  const chip=(t,cls)=>`<label class="chip ${cls}${activeTags.some(a=>a.toLowerCase()===t.tag.toLowerCase())?' on':''}"><input type="checkbox" name="tag_filter" value="${esc(t.tag)}"${activeTags.some(a=>a.toLowerCase()===t.tag.toLowerCase())?' checked':''}><span>${esc(t.tag)} <em>${t.count}</em></span></label>`;
  $('tagChips').innerHTML=data.matched.map(t=>chip(t,'radar')).join('')+data.user.map(t=>chip(t,'mine')).join('');
  $('tagFilter').classList.toggle('hidden',!data.matched.length&&!data.user.length);
  $('tagClear').classList.toggle('hidden',!activeTags.length);
}

function onTagChipChange(e){
  const input=e.target;if(input.name!=='tag_filter')return;
  const v=input.value;
  activeTags=input.checked?[...activeTags.filter(t=>t.toLowerCase()!==v.toLowerCase()),v]:activeTags.filter(t=>t.toLowerCase()!==v.toLowerCase());
  try{localStorage.setItem('ps.tags',JSON.stringify(activeTags))}catch{}
  input.closest('.chip').classList.toggle('on',input.checked);
  $('tagClear').classList.toggle('hidden',!activeTags.length);
  loadPapers();
}

function clearTags(){
  activeTags=[];try{localStorage.setItem('ps.tags','[]')}catch{}
  document.querySelectorAll('input[name="tag_filter"]').forEach(i=>{i.checked=false;i.closest('.chip').classList.remove('on');});
  $('tagClear').classList.add('hidden');loadPapers();
}

async function loadPapers(){
  const view=currentView;
  const papers=await fetchList();
  const mode=layout();
  $('papers').className=mode==='table'?'paper-list':`paper-grid ${mode}`;
  $('papers').innerHTML=mode==='table'?renderList(papers):papers.map(renderPaper).join('');
  updateListBar(papers);
  document.querySelectorAll('.layout-btn').forEach(b=>b.classList.toggle('active',b.dataset.layout===mode));
  const empty={inbox:'emptyInbox',all:'emptyState',saved:'emptySaved',liked:'emptyLiked',disliked:'emptyDisliked'};
  for(const [k,id] of Object.entries(empty)) $(id).classList.toggle('hidden',!!currentQuery||activeTags.length>0||k!==view||papers.length!==0);
  if(activeTags.length&&!currentQuery&&!papers.length)$('papers').innerHTML=`<div class="empty">No papers tagged ${activeTags.map(t=>`<span class="badge">${esc(t)}</span>`).join(' ')} in this view.</div>`;
  if(view!=='inbox'||currentQuery||activeTags.length){return;}
  if(lastKnownCount && papers.length>lastKnownCount && settings?.browser_notifications && 'Notification' in window && Notification.permission==='granted'){
    new Notification('Paper Sentinel',{body:`${papers.length-lastKnownCount} new relevant paper(s)`});
  }
  lastKnownCount=papers.length;
}

function replaceCard(card,paper){
  const aiOpen=card.querySelector('details.ai-summary')?.open;
  if(card.classList.contains('list-item')&&card.classList.contains('open'))expandedIds.add(paper.arxiv_id);
  card.outerHTML=layout()==='table'?renderListItem(paper):renderPaper(paper);
  if(aiOpen){const d=$('papers').querySelector(`.paper[data-id="${CSS.escape(paper.arxiv_id)}"] details.ai-summary`);if(d)d.open=true;}
}

function removeCard(card,emptyId){
  card.classList.add('leaving');
  setTimeout(()=>{
    card.remove();
    const left=$('papers').querySelectorAll('.paper');
    updateListBar([...left]);
    if(!left.length){$('papers').innerHTML='';if(!currentQuery)$(emptyId).classList.remove('hidden');}
  },160);
}

function cardOf(el){return el.closest('.paper');}
function itemOf(el){return cardOf(el);}

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
  if(currentView==='inbox'&&saved){bumpInbox(-1);removeCard(card,'emptyInbox');return;}
  replaceCard(card,paper);
}

async function toggleRead(btn){
  const id=btn.dataset.id,read=btn.dataset.read!=='1',card=itemOf(btn);
  card.querySelectorAll('.read-btn').forEach(b=>b.disabled=true);
  const resp=await postJSON(`/api/papers/${encodeURIComponent(id)}/read`,{read});
  if(!resp.ok){card.querySelectorAll('.read-btn').forEach(b=>b.disabled=false);toast('Could not update');return;}
  const paper=await resp.json();
  toast(read?'Marked as read':'Marked as unread');
  if(currentView==='inbox'&&read){bumpInbox(-1);removeCard(card,'emptyInbox');return;}
  replaceCard(card,paper);
}

async function markAllRead(){
  const n=Number($('inboxCount').textContent||0);
  if(!confirm(`Mark ${activeTags.length?'the filtered':'all'} inbox papers as read? They stay available in the All tab.`))return;
  const resp=await postJSON('/api/papers/read-all',{tags:activeTags});
  if(!resp.ok){toast('Could not mark as read');return;}
  const data=await resp.json();toast(`${data.marked} paper(s) marked as read`);await loadStatus();await loadPapers();
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
  if(currentView==='inbox'&&reaction){bumpInbox(-1);removeCard(card,'emptyInbox');return;}
  replaceCard(card,paper);
}

async function downloadPdf(btn){
  const id=btn.dataset.id,card=itemOf(btn);
  btn.disabled=true;btn.innerHTML=`${I.clock}<span>Downloading…</span>`;
  const resp=await postJSON(`/api/papers/${encodeURIComponent(id)}/pdf`);
  if(!resp.ok){btn.disabled=false;btn.innerHTML=`${I.download}<span>Save PDF</span>`;toast((await resp.json()).detail||'PDF download failed');return;}
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
  panel.innerHTML=`<div class="panel-title">Similar papers</div><ul class="similar-list">${data.results.map(r=>`<li><span class="badge score">${pct(r.similarity)}</span> <a href="${esc(r.abs_url)}" target="_blank" rel="noreferrer">${esc(r.title)}</a>${r.saved?` <span class="mini icon warn" title="Read later">${BOOKMARK}</span>`:''}${r.reaction==='like'?` <span class="mini icon ok" title="Liked">${THUMB_UP}</span>`:''}</li>`).join('')}</ul>`;
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

function setView(view){
  currentView=view;try{localStorage.setItem('ps.view',view)}catch{}
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===view));
  loadTagChips();loadPapers();
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

/* ------------------------------------------------------------------ LLM server monitor */

let llmBusyUntil=0;
function renderLlm(llm){
  if(!llm)return;
  const stat=$('llmStat'),banner=$('llmBanner');
  const name=llm.hints?.name||'LLM';
  const show=(id,visible)=>$(id).classList.toggle('hidden',!visible);
  const busy=llm.action?.status==='running';
  let level,text,title='',body='',cmd='',sub='',bannerLevel='';
  if(!llm.enabled){
    level='off';text=`${name}: disabled (extractive summaries only)`;
  }else if(!llm.reachable){
    level='down';text=`${name}: offline`;
    title=`${name} is not running`;
    body=`${llm.error} Paper Sentinel falls back to extractive summaries and text-only search until it is back.`;
    cmd=llm.hints?.start||'';sub=llm.hints?.gui||'';bannerLevel='';
  }else{
    const chatMissing=llm.chat_available===false,chatCold=llm.chat_loaded===false;
    const embOn=llm.embeddings_enabled!==false;
    const embMissing=embOn&&(!llm.embedding_model||llm.embedding_available===false),embCold=embOn&&llm.embedding_loaded===false;
    if(chatMissing||embMissing){
      level='warn';text=`${name}: online, model missing`;
      title=chatMissing?`Chat model “${llm.chat_model}” is not available on ${name}`:`No embedding model available on ${name}`;
      body=chatMissing?`Available models: ${(llm.models||[]).slice(0,8).join(', ')||'none'}. Pick one in Settings or download it:`:`Semantic search, Similar and match scores need an embedding model. Download one and set it in Settings (or leave empty to auto-detect):`;
      cmd=chatMissing?llm.hints?.load_chat:llm.hints?.load_embedding;bannerLevel='warn';
    }else if(chatCold||embCold){
      level='warn';text=`${name}: online, ${chatCold&&embCold?'models':'model'} not loaded`;
      title=`${chatCold?llm.chat_model:llm.embedding_model}${chatCold&&embCold?` and ${llm.embedding_model}`:''} not loaded yet`;
      body=`${name} will usually load the model on the first request (this makes the first scan slow). To load it now:`;
      cmd=[chatCold?llm.hints?.load_chat:'',embCold?llm.hints?.load_embedding:''].filter(Boolean).join('\n');bannerLevel='warn';
    }else{
      level='ok';text=`${name}: online · ${llm.chat_model}${llm.embedding_model?` + ${llm.embedding_model}`:''}${llm.latency_ms!==null?` · ${llm.latency_ms} ms`:''}`;
    }
  }
  if(busy){text+=` · ${llm.action.detail||'working…'}`;}
  stat.className=`llm-stat ${level}`;stat.innerHTML=`<i class="dot"></i> ${esc(text)}`;stat.title=llm.base_url||'';
  const showBanner=!!title;
  banner.classList.toggle('hidden',!showBanner);
  if(!showBanner)return;
  banner.className=`llm-banner${bannerLevel?' '+bannerLevel:''}`;
  $('llmBannerTitle').textContent=title;$('llmBannerText').textContent=body;
  $('llmBannerCmd').querySelector('code').textContent=cmd;show('llmBannerCmd',!!cmd);
  const actionErr=llm.action?.status==='error'?` Last attempt: ${llm.action.detail}`:'';
  $('llmBannerSub').textContent=(sub+actionErr).trim();
  show('llmStartBtn',!llm.reachable&&llm.can_start);
  show('llmLoadChatBtn',llm.reachable&&llm.can_start&&llm.chat_loaded===false&&llm.chat_available!==false);
  show('llmLoadEmbedBtn',llm.reachable&&llm.can_start&&llm.embedding_loaded===false&&llm.embedding_available!==false);
  ['llmStartBtn','llmLoadChatBtn','llmLoadEmbedBtn'].forEach(id=>$(id).disabled=busy||Date.now()<llmBusyUntil);
}

async function llmAction(url,body,label){
  llmBusyUntil=Date.now()+4000;
  const resp=await postJSON(url,body);
  const data=await resp.json().catch(()=>({}));
  toast(resp.ok?`${label}: ${data.detail||'started'}`:(data.detail||`${label} failed`));
  setTimeout(loadStatus,1500);
}

async function recheckLlm(){
  const llm=await fetch('/api/llm/health?force=true').then(r=>r.json());renderLlm(llm);toast(llm.reachable?'LLM server reachable':'LLM server still offline');
}

async function loadStatus(){
  const s=await fetch('/api/status').then(r=>r.json());
  renderLlm(s.llm);
  const status=s.scan_status||'idle';
  $('scanStatus').textContent=`Status: ${status}`;updateCounts(s.counts);$('scanStatus').className=status==='error'?'status-error':'';
  $('lastScan').textContent=`Last scan: ${s.last_scan?dateText(s.last_scan):'never'}`;
  if(s.library)$('libraryStat').textContent=`Library: ${s.library.embedded}/${s.library.total} embedded · ${s.library.pdfs} PDF${s.library.pdfs===1?'':'s'}`;
  const err=$('scanError');err.textContent=status==='error'&&s.last_error?`Last error: ${s.last_error}`:'';err.classList.toggle('hidden',!err.textContent);
  $('scanBtn').disabled=status==='running';
  if(status!=='running'&&currentView==='inbox'&&!currentQuery&&!document.querySelector('.notes-panel:not(.hidden)')&&!document.querySelector('.paper.leaving')) await loadPapers();
  loadTagChips();
}

async function scanNow(){
  $('scanBtn').disabled=true;const r=await fetch('/api/scan',{method:'POST'}).then(r=>r.json());toast(r.status==='busy'?'Scan already running':'Scan started');setTimeout(loadStatus,1500);
}

/* ------------------------------------------------------------------ wiring */

$('settingsBtn').addEventListener('click',async()=>{await loadSettings();$('settingsDialog').showModal();});
$('closeSettings').addEventListener('click',()=>$('settingsDialog').close());$('cancelSettings').addEventListener('click',()=>$('settingsDialog').close());
$('settingsForm').addEventListener('submit',saveSettings);$('scanBtn').addEventListener('click',scanNow);
wireChipInput('customTags','customTagChips','custom_tags','suggested_tags');
wireChipInput('customCategories','customCategoryChips','custom_categories','categories');
$('rebuildEmbeddings').addEventListener('click',rebuildEmbeddings);
$('llmStartBtn').addEventListener('click',()=>llmAction('/api/llm/start',undefined,'Start server'));
$('llmLoadChatBtn').addEventListener('click',()=>llmAction('/api/llm/load',{kind:'chat'},'Load chat model'));
$('llmLoadEmbedBtn').addEventListener('click',()=>llmAction('/api/llm/load',{kind:'embedding'},'Load embedding model'));
$('llmRetryBtn').addEventListener('click',recheckLlm);
$('llmSettingsBtn').addEventListener('click',async()=>{await loadSettings();$('settingsDialog').showModal();});
$('llmCopyCmd').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('llmBannerCmd').querySelector('code').textContent);toast('Command copied');}catch{toast('Copy failed – select the text manually');}});
$('papers').addEventListener('click',e=>{
  const hit=(sel)=>e.target.closest(sel);
  let b;
  if((b=hit('.save-btn')))return toggleSaved(b);
  if((b=hit('.react-btn')))return setReaction(b);
  if((b=hit('.list-toggle')))return toggleListItem(b);
  if((b=hit('.read-btn')))return toggleRead(b);
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
$('expandAllBtn').addEventListener('click',toggleExpandAll);$('markAllRead').addEventListener('click',markAllRead);
$('tagChips').addEventListener('change',onTagChipChange);$('tagClear').addEventListener('click',clearTags);
$('searchForm').addEventListener('submit',runSearch);
$('searchClear').addEventListener('click',clearSearch);
$('searchMode').addEventListener('change',()=>{if(currentQuery)loadPapers();});
$('searchInput').addEventListener('keydown',e=>{if(e.key==='Escape')clearSearch();});
$('sortMode').value=currentSort;$('sortMode').addEventListener('change',e=>setSort(e.target.value));
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){e.preventDefault();$('searchInput').focus();}});

(async()=>{await loadSettings();await loadTagChips(true);await loadPapers();await loadStatus();setInterval(loadStatus,5000);
  if(location.hash==='#settings'){$('settingsDialog').showModal();}})();
