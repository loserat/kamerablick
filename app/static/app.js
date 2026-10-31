let token=sessionStorage.getItem('oma-token')||'', latest=null, selectedCamera='', candidatePin='', candidateHost='', snapshotUrl='', noticeTimer, polling=false;
const $=s=>document.querySelector(s);
const pages={overview:['Alles im Blick.','Kamerabild einschalten und entspannt nachsehen.'],camera:['Deine Kamera. Einfach verbunden.','Protect verbinden, Kamera auswählen, fertig.'],settings:['So passt es für euch.','Taster und Abschaltung einmal in Ruhe einstellen.'],maintenance:['Gut betreut. Auch von unterwegs.','Verbindung und Versionen im Blick behalten.']};
function page(){const name=location.hash.slice(1);return pages[name]?name:'overview'}
function navigate(){const active=page();for(const e of document.querySelectorAll('.page'))e.hidden=e.id!==active;for(const a of document.querySelectorAll('nav a')){a.classList.toggle('active',a.dataset.page===active);if(a.dataset.page===active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')}$('#page-title').textContent=pages[active][0];$('#page-description').textContent=pages[active][1]}
window.addEventListener('hashchange',()=>{navigate();window.scrollTo(0,0)});navigate();
function notify(message){$('#notice').textContent=message;$('#notice').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('#notice').hidden=true,6500)}
function loggedOut(){token='';sessionStorage.removeItem('oma-token');$('#login').hidden=false;$('#content').hidden=true;$('#logout').hidden=true;$('#mode').textContent='Anmeldung erforderlich';latest=null;clearSnapshot();$('#protect-key').value='';$('#protect-password').value='';$('#protect-user').value='';$('#camera-picker').hidden=true;$('#connect-form').hidden=false;candidatePin='';$('#cert-box').hidden=true;$('#trust-cert').checked=false}
async function api(path,body){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000);let r;try{r=await fetch('/api/'+path,{signal:controller.signal,method:body?'POST':'GET',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:body?JSON.stringify(body):undefined})}catch{throw Error('Dashboard nicht erreichbar oder Zeitüberschreitung. Verbindung prüfen.')}finally{clearTimeout(timer)}const type=r.headers.get('Content-Type')||'';if(r.ok&&type.startsWith('image/'))return r.blob();const data=await r.json();if(!r.ok){if(data.reauth)loggedOut();const e=Error(data.error||'Anfrage fehlgeschlagen.');e.data=data;throw e}return data}
async function busy(button,fn){const original=button.textContent;button.disabled=true;button.textContent='Einen Moment …';try{await fn()}catch(e){notify(e.message)}finally{button.disabled=false;button.textContent=original}}
function render(d,fill){latest=d;renderMaintenance(d.maintenance);renderCEC(d);renderTelemetry(d.telemetry);$('#login').hidden=true;$('#content').hidden=false;$('#logout').hidden=false;$('#mode').textContent=d.home_test?'● Heimtest':d.demo?'● Demomodus':'● Pi-Betrieb';$('#test-banner-title').textContent=d.home_test?'Dein NVR. In Ruhe zu Hause testen.':'Du siehst die Vorschau.';$('#test-banner-copy').textContent=d.home_test?'Der NVR-Zugang und echte Standbilder werden geprüft. TV und GPIO bleiben in diesem Modus simuliert.':'Du kannst die Bedienung ausprobieren. Mit Fernseher und Taster ist sie noch nicht verbunden.';$('#demo-banner').hidden=!d.demo;$('#demo-cameras').hidden=!d.demo||d.home_test;$('#test-protect').disabled=!d.protect.configured||d.config.camera_source!=='protect';$('#tv-state').textContent=d.state.tv;$('#tv-summary').textContent=!d.demo&&!d.agent_available?'Unbekannt':d.state.active?'Kameraansicht aktiv':'Kameraansicht aus';$('#tv-detail').textContent=d.demo?'Simuliert · kein TV verbunden':!d.agent_available?'Pi-Dienst nicht erreichbar':d.state.active?(d.state.player_health?.progress_fresh?'Wiedergabezeit wird aktualisiert':d.state.player_health?.state==='stalled'?'Wiedergabe stockt · neuer Versuch folgt':'Wiedergabefortschritt wird geprüft'):'CEC-Befehle · TV-Zustand nicht ausgelesen';$('#camera-label').textContent=d.config.camera_name;$('#screen-camera').textContent=d.config.camera_name;const configured=d.config.has_stream||d.config.camera_source==='demo';$('#camera-summary').textContent=configured?d.config.camera_name:'Noch nicht eingerichtet';$('#camera-detail').textContent=d.config.camera_source==='protect'?'UniFi Protect · '+({high:'Hohe',medium:'Mittlere',low:'Niedrige'}[d.config.quality]||'')+' Qualität':d.config.camera_source==='demo'?'Beispielkamera · kein echtes Kamerabild':d.config.has_stream?'Manuell verbundener Videostream':'In wenigen Schritten verbinden.';$('#setup-callout').hidden=configured;$('#timeout-label').textContent=d.config.auto_off_minutes?d.config.auto_off_minutes+' Minuten':'Deaktiviert';const remaining=d.state.remaining_seconds;$('#countdown').textContent=d.state.active&&remaining?'Noch etwa '+Math.ceil(remaining/60)+' Min. bis Standby.':'Nach der eingestellten Zeit in Standby.';$('#diagnostic').textContent=d.state.message||'';$('#version').textContent=d.version;$('#agent-status').textContent=d.demo?'Demomodus':d.agent_available?'Erreichbar':'Nicht erreichbar';$('#integration-status').textContent=d.protect.configured?'Eingerichtet':'Nicht eingerichtet';$('#integration-host').textContent=d.protect.host||'Lokale Protect-Verbindung';$('#protect-status').textContent=d.protect.configured?'Zugang gespeichert':'Nicht eingerichtet';for(const b of document.querySelectorAll('[data-action="on"]'))b.disabled=!d.demo&&(!d.agent_available||!d.config.has_stream);if(fill){for(const [k,v]of Object.entries(d.config)){const e=$('#settings-form').elements[k];if(e){if(e.tagName==='SELECT'&&!Array.from(e.options).some(o=>o.value===String(v)))e.add(new Option(v+' Minuten',v));e.value=v}}$('#manual-form').elements.camera_name.value=d.config.camera_name;$('#manual-form').elements.stream_url.placeholder=d.config.has_stream?'Gespeichert · neue Adresse zum Ersetzen':'rtsps://…';$('#protect-host').value=d.protect.host;$('#protect-auth').value=d.protect.auth_mode||'local';$('#protect-user').value=d.protect.username||'';updateAuthFields();updateAuthFields()}}
async function load(fill=false){const d=await api('status');render(d,fill)}
$('#login-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{const d=await api('login',{password:$('#password').value});token=d.token;sessionStorage.setItem('oma-token',token);$('#password').value='';$('#notice').hidden=true;await load(true)})};
$('#logout').onclick=()=>busy($('#logout'),async()=>{await api('logout',{});loggedOut()});
$('#settings-form').addEventListener('input',()=>$('#save-state').textContent='Ungespeicherte Änderungen');
$('#settings-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{notify((await api('config',Object.fromEntries(new FormData(e.target)))).message);$('#save-state').textContent='Alle Einstellungen gespeichert.';await load(true)})};
$('#manual-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{notify((await api('config',Object.fromEntries(new FormData(e.target)))).message);e.target.elements.stream_url.value='';await load(true);location.hash='overview'})};
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>busy(b,async()=>{notify((await api('action',{action:b.dataset.action})).message);await load()}));
async function checkUpdates(){if($('#check-update').disabled)return;lastReleaseCheck=Date.now();return busy($('#check-update'),async()=>{try{const d=await api('update');updateRelease=d;updateSupport=d.maintenance;$('#update-result').textContent=d.available?'Installiert: '+d.current+' · Verfügbar: '+d.version+'.':'Du nutzt die aktuelle veröffentlichte Version '+d.current+'.';$('#update-release-notes').textContent=d.notes||'Keine zusätzlichen Versionshinweise.';$('#update-release').hidden=false;renderMaintenance(updateSupport)}catch(error){$('#update-result').textContent=error.message;throw error}})}
$('#check-update').onclick=checkUpdates;
function clearSnapshot(){if(snapshotUrl)URL.revokeObjectURL(snapshotUrl);snapshotUrl='';$('#snapshot').hidden=true;$('#snapshot').removeAttribute('src')}
function resetRepair(){$('#stream-repair').hidden=true;$('#enable-stream').checked=false;$('#selection-message').textContent='';$('#done-link').hidden=true}
function showCameras(d){$('#protect-key').value='';$('#protect-password').value='';$('#connect-form').hidden=true;$('#camera-picker').hidden=false;$('#step-connect').classList.remove('current');$('#step-camera').classList.add('current');$('#step-done').classList.remove('current');$('#camera-list').replaceChildren();selectedCamera='';clearSnapshot();resetRepair();$('#snapshot-button').disabled=d.demo;$('#select-camera').disabled=true;$('#selection-message').textContent=d.demo?'Beispielkameras – keine echte Verbindung zu Protect.':d.cameras.length?'':'Keine Kameras gefunden. Berechtigungen und Protect prüfen.';for(const camera of d.cameras){const label=document.createElement('label');label.className='camera-option';const radio=document.createElement('input');radio.type='radio';radio.name='camera';radio.value=camera.id;radio.disabled=camera.state!=='CONNECTED';const info=document.createElement('span');const title=document.createElement('strong');title.textContent=camera.name;const sub=document.createElement('small');sub.textContent=camera.model+' · '+(camera.state==='CONNECTED'?'Erreichbar':'Nicht verbunden');info.append(title,sub);label.append(radio,info);radio.onchange=()=>{selectedCamera=camera.id;clearSnapshot();resetRepair();$('#select-camera').disabled=false};$('#camera-list').append(label)}}
$('#protect-host').addEventListener('input',()=>{candidatePin='';candidateHost='';$('#cert-box').hidden=true;$('#trust-cert').checked=false;updateAuthFields()});
$('#connect-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{const host=$('#protect-host').value;const body={host,auth_mode:$('#protect-auth').value,username:$('#protect-user').value,password:$('#protect-password').value,api_key:$('#protect-key').value};if(candidatePin&&candidateHost===host&&$('#trust-cert').checked)body.fingerprint=candidatePin;$('#connect-message').textContent='Verbindung wird geprüft …';try{const d=await api('protect/connect',body);showCameras(d);$('#connect-message').textContent=''}catch(e){$('#connect-message').textContent=e.message;if(e.data?.fingerprint){candidatePin=e.data.fingerprint;candidateHost=host;$('#cert-value').textContent=candidatePin.match(/.{1,2}/g).join(':');$('#cert-box').hidden=false;$('#trust-cert').checked=false}throw e}})};
$('#demo-cameras').onclick=()=>busy($('#demo-cameras'),async()=>showCameras(await api('protect/connect',{demo:true})));
$('#reconnect').onclick=()=>{$('#camera-picker').hidden=true;$('#connect-form').hidden=false;$('#step-connect').classList.add('current');$('#step-camera').classList.remove('current');$('#step-done').classList.remove('current');clearSnapshot()};
$('#quality').onchange=resetRepair;
$('#snapshot-button').onclick=()=>busy($('#snapshot-button'),async()=>{if(!selectedCamera)throw Error('Bitte zuerst eine Kamera auswählen.');const blob=await api('protect/snapshot',{camera_id:selectedCamera});clearSnapshot();snapshotUrl=URL.createObjectURL(blob);$('#snapshot').src=snapshotUrl;$('#snapshot').hidden=false});
$('#select-camera').onclick=()=>busy($('#select-camera'),async()=>{if(!selectedCamera)throw Error('Bitte zuerst eine Kamera auswählen.');try{const d=await api('protect/select',{camera_id:selectedCamera,quality:$('#quality').value,enable_stream:$('#enable-stream').checked});$('#selection-message').textContent=d.message;$('#done-link').hidden=false;$('#step-camera').classList.remove('current');$('#step-done').classList.add('current');$('#stream-repair').hidden=true;notify(d.message);await load(true)}catch(e){$('#selection-message').textContent=e.message;if(e.data?.needs_stream)$('#stream-repair').hidden=false;throw e}});
queueMicrotask(()=>{if(token)load(true).catch(e=>notify(e.message))});
setInterval(async()=>{if(!token||polling||document.hidden)return;polling=true;try{await load()}catch(e){$('#diagnostic').textContent=e.message;renderTelemetry({...latest?.telemetry,camera_fresh:false,events_fresh:false,last_error:'Dashboard-Verbindung unterbrochen. Werte sind nicht aktuell.'})}finally{polling=false}},5000);

$('#open-tv').onclick=()=>busy($('#open-tv'),async()=>{const d=await api('tv/pair',{});location.href='/tv#access='+encodeURIComponent(d.token)});
$('#reset-tv').onclick=()=>busy($('#reset-tv'),async()=>notify((await api('tv/revoke',{})).message));

function renderTelemetry(data){const v=TelemetryView.view(data);$('#health-camera').textContent=v.camera;$('#event-connection').textContent=v.connection;$('#health-motion').textContent=v.motion;$('#health-note').textContent=v.warning;for(const [field,id]of [['last_motion','last-motion'],['last_person','last-person'],['last_vehicle','last-vehicle']]){$('#'+id).textContent=v.records[field].label;$('#'+id+'-detail').textContent=v.records[field].detail}}

function renderCEC(d){
  const c=d.state.cec;
  $('#cec-status').textContent=d.demo?'Vorschau · kein CEC-Adapter verbunden.':!d.agent_available?'Pi-Dienst nicht erreichbar.':c?.message||'CEC-Empfang noch nicht verfügbar.';
  const last=c?.last_key;const at=last?.at?new Date(last.at):null;
  $('#cec-key').textContent=last?'Letzte Taste: '+last.key+' ('+last.code+')'+(at&&!Number.isNaN(at.getTime())?' · '+at.toLocaleString('de-DE',{timeZone:'Europe/Berlin'}):'')+(last.supported?'':' · ohne Aktion'):'Noch keine Taste empfangen. Am TV Pfeile, OK und Zurück drücken.';
  $('#cec-receiver').textContent=c?.receiver_active?'Lokale TV-Ansicht empfängt Tasten.':'Lokaler TV-Empfänger nicht verbunden. Auf dem Pi die TV-Anwendung starten.';
}

function sameConsole(){try{const host=$('#protect-host').value.trim();return new URL(host.includes('://')?host:'https://'+host).origin===latest?.protect.host}catch{return false}}
function updateAuthFields(){
  const local=$('#protect-auth').value==='local';
  $('#local-login-fields').hidden=!local;$('#local-login-note').hidden=!local;
  $('#key-options-title').textContent=local?'Zusätzlicher API-Schlüssel für Streams und Ereignisse':'Mit Protect-API-Schlüssel anmelden';
  if(!local)$('#protect-key-options').open=true;
  const saved=latest?.protect;const same=sameConsole()&&saved?.auth_mode===$('#protect-auth').value&&(!local||$('#protect-user').value.trim()===saved.username);
  $('#protect-user').required=local;
  $('#protect-password').required=local&&!(same&&saved?.has_password&&$('#protect-user').value.trim()===saved.username);
  $('#protect-key').required=!local&&!(same&&saved?.has_api_key);
  $('#password-hint').textContent=same&&saved?.has_password?'Passwort gespeichert. Leer lassen, um es erneut zu verwenden.':'Das Passwort bleibt nur im lokalen Kamerablick-Datenverzeichnis.';
  $('#key-hint').textContent=same&&saved?.has_api_key?'API-Schlüssel gespeichert. Leer lassen, um ihn erneut zu verwenden.':local?'Optional für den lokalen Login. Für neue Stream-Schnittstellen und laufende Ereignisse benötigt.':'Dein Protect-API-Schlüssel. Bleibt lokal und wird nicht an GitHub gesendet.';
  $('#connect-button').textContent=local?'Am NVR anmelden →':'Protect verbinden →';
}
$('#protect-auth').onchange=()=>{$('#protect-key').value='';$('#protect-password').value='';updateAuthFields()};
$('#protect-user').addEventListener('input',updateAuthFields);
$('#open-manual').onclick=()=>{const manual=$('#manual-camera');manual.open=true;manual.scrollIntoView({behavior:'smooth',block:'center'});$('#manual-form').elements.camera_name.focus()};
$('#test-protect').onclick=()=>busy($('#test-protect'),async()=>{const result=$('#protect-test-result');result.textContent='NVR, Kamera und Standbild werden geprüft …';try{const d=await api('protect/test',{});result.textContent=d.camera_name+' · '+d.camera_count+' Kamera(s) · '+d.elapsed_ms+' ms. '+d.message}catch(error){result.textContent=error.message;throw error}});
updateAuthFields();

let updateRelease=null,updateSupport=null,updateWatching=false,completedUpdateJob='',lastReleaseCheck=0,lastRenderedAppVersion='';
let updateWatch=null;
try{const saved=JSON.parse(sessionStorage.getItem('kamerablick-update-watch')||'null');if(saved&&typeof saved.watch==='string'&&saved.watch.length>=32&&saved.watch.length<=128)updateWatch=saved}catch{}
function renderMaintenance(support){
  if(latest?.version&&lastRenderedAppVersion!==latest.version){lastRenderedAppVersion=latest.version;updateRelease=null;lastReleaseCheck=0;$('#update-result').textContent='Installiert: '+latest.version+'.';$('#update-release').hidden=true}
  updateSupport=support||updateSupport;
  if(!updateSupport)return;
  const job=updateSupport.job;
  $('#maintenance-support').textContent=updateSupport.message||'';
  renderLastUpdate(job);
  $('#update-setup-help').hidden=!!(updateSupport.available&&updateSupport.persistent)||!!latest?.demo;
  $('#install-update').hidden=!updateRelease?.available;
  $('#install-update').disabled=!(updateRelease?.available&&updateSupport.available&&updateSupport.persistent&&!job?.busy);
  if(job)renderUpdateJob(job);
  if(token&&page()==='maintenance'&&Date.now()-lastReleaseCheck>300000)queueMicrotask(checkUpdates);
}
function renderUpdateJob(job){
  renderLastUpdate(job);
  $('#update-job').hidden=false;
  $('#update-job-title').textContent=job.phase==='complete'?'Neue Version ist bereit.':job.phase==='rolled_back'?'Vorherige Version wieder aktiv.':job.phase==='failed'||job.phase==='recovery_failed'?'Aktualisierung benötigt Aufmerksamkeit.':'Kamerablick wird aktualisiert.';
  $('#update-job-message').textContent=job.message;
  $('#update-progress-bar').hidden=!job.busy;
  $('#update-job-note').textContent=job.busy?'Du kannst den Browser schließen. Der Auftrag läuft auf dem Pi weiter.':'Bei einem Neustart bitte erneut am Dashboard anmelden. Kamera, Taster und TV anschließend prüfen.';
  if(!job.busy&&(updateWatch||completedUpdateJob!==job.id)){completedUpdateJob=job.id;sessionStorage.removeItem('kamerablick-update-watch');updateWatch=null;updateRelease=null;$('#install-update').hidden=true}
}
function renderLastUpdate(job){
  const outcomes={complete:'Erfolgreich abgeschlossen',rolled_back:'Vorherige Version wiederhergestellt',failed:'Update nicht übernommen',recovery_failed:'Wiederherstellung benötigt Hilfe'};
  const outcome=outcomes[job?.phase];
  $('#last-update').hidden=!outcome;
  if(!outcome)return;
  const date=new Date(Number(job.updated_at)*1000);
  const when=Number.isFinite(job.updated_at)&&job.updated_at>0&&!Number.isNaN(date.getTime())?date.toLocaleString('de-DE',{timeZone:'Europe/Berlin'}):'Zeitpunkt nicht verfügbar';
  const versions=job.previous_version&&job.version?job.previous_version+' → '+job.version:job.version||'Versionswechsel';
  $('#last-update-result').textContent=versions+' · '+outcome+' · '+when;
}
async function watchUpdate(){
  if(updateWatching||!updateWatch)return;
  updateWatching=true;
  $('#update-job').hidden=false;
  try{
    const response=await fetch('/api/update/progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({watch:updateWatch.watch}),signal:AbortSignal.timeout(7000)});
    if(response.status===401){sessionStorage.removeItem('kamerablick-update-watch');updateWatch=null;$('#update-job-message').textContent='Statusfreigabe abgelaufen. Bitte erneut am Dashboard anmelden.';$('#update-progress-bar').hidden=true;return}
    if(!response.ok)throw Error('Wartungsstatus noch nicht erreichbar');
    const data=await response.json();if(data.job)renderUpdateJob(data.job);
  }catch{
    $('#update-job-message').textContent='Verbindung wird wiederhergestellt. Die Anwendung startet möglicherweise neu; der Auftrag läuft auf dem Pi weiter.';
    $('#update-job-note').textContent='Diese Seite geöffnet lassen oder später erneut am Dashboard anmelden.';
  }finally{updateWatching=false;if(updateWatch)setTimeout(watchUpdate,2000)}
}
$('#install-update').onclick=()=>{if(!updateRelease||$('#install-update').disabled)return;$('#update-confirm-version').textContent=updateRelease.current+' → '+updateRelease.version;$('#update-confirm-error').textContent='';$('#update-confirm').showModal();$('#cancel-update').focus()};
$('#cancel-update').onclick=()=>$('#update-confirm').close();
$('#confirm-update').onclick=()=>busy($('#confirm-update'),async()=>{$('#cancel-update').disabled=true;try{if(!updateRelease)throw Error('Bitte die Version erneut prüfen.');const data=await api('update/install',{version:updateRelease.version,confirm:true});updateWatch={watch:data.watch};sessionStorage.setItem('kamerablick-update-watch',JSON.stringify(updateWatch));$('#update-confirm').close();renderUpdateJob(data.job);$('#install-update').disabled=true;watchUpdate()}catch(error){$('#update-confirm-error').textContent=error.message;throw error}finally{$('#cancel-update').disabled=false}});
$('#update-confirm').addEventListener('cancel',event=>{if($('#confirm-update').disabled)event.preventDefault()});
if(updateWatch)watchUpdate();

window.addEventListener('hashchange',()=>{if(token&&page()==='maintenance'&&Date.now()-lastReleaseCheck>300000)checkUpdates()});
setInterval(()=>{if(token&&page()==='maintenance'&&!document.hidden&&Date.now()-lastReleaseCheck>300000)checkUpdates()},30000);
