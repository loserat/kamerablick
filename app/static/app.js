let token=sessionStorage.getItem('oma-token')||'', latest=null, selectedCamera='', candidatePin='', candidateHost='', snapshotUrl='', noticeTimer, polling=false;
let overviewSnapshotUrl='', overviewCameraKey='', overviewRequest=0, previewBusy=false, protectTestKey='';
let camerasLoading=false,savedCamerasSignature='';
const $=s=>document.querySelector(s);
const pages={overview:['Übersicht',''],camera:['Kameras',''],settings:['Einstellungen',''],maintenance:['Wartung','']};
function page(){const name=location.hash.slice(1);return pages[name]?name:'overview'}
function navigate(){const active=page();for(const e of document.querySelectorAll('.page'))e.hidden=e.id!==active;for(const a of document.querySelectorAll('nav a')){a.classList.toggle('active',a.dataset.page===active);if(a.dataset.page===active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')}$('#page-title').textContent=pages[active][0];$('#page-description').textContent=pages[active][1];$('#page-description').hidden=!pages[active][1]}
window.addEventListener('hashchange',()=>{navigate();window.scrollTo(0,0)});navigate();
function notify(message){$('#notice').textContent=message;$('#notice').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('#notice').hidden=true,6500)}
function loggedOut(){$('#dashboard-password-form').reset();$('#dashboard-password-message').textContent='';document.body.classList.remove('signed-in');clearOverviewPreview();overviewCameraKey='';token='';sessionStorage.removeItem('oma-token');$('#login').hidden=false;$('#content').hidden=true;$('#logout').hidden=true;$('#mode').textContent='Anmeldung erforderlich';latest=null;clearSnapshot();$('#protect-key').value='';$('#protect-password').value='';$('#protect-user').value='';$('#camera-picker').hidden=true;$('#connect-form').hidden=false;candidatePin='';$('#cert-box').hidden=true;$('#trust-cert').checked=false}
async function api(path,body){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000);let r;try{r=await fetch('/api/'+path,{signal:controller.signal,method:body?'POST':'GET',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:body?JSON.stringify(body):undefined})}catch{throw Error('Dashboard nicht erreichbar oder Zeitüberschreitung. Verbindung prüfen.')}finally{clearTimeout(timer)}const type=r.headers.get('Content-Type')||'';if(r.ok&&type.startsWith('image/'))return r.blob();const data=await r.json();if(!r.ok){if(data.reauth)loggedOut();const e=Error(data.error||'Anfrage fehlgeschlagen.');e.data=data;throw e}return data}
async function busy(button,fn){button.disabled=true;button.setAttribute('aria-busy','true');try{await fn()}catch(e){notify(e.message)}finally{button.disabled=false;button.removeAttribute('aria-busy')}}
function render(d,fill){
  latest=d;
  document.body.classList.add('signed-in');
  renderMaintenance(d.maintenance);
  renderCEC(d);
  renderTelemetry(d.telemetry);
  $('#login').hidden=true;$('#content').hidden=false;$('#logout').hidden=false;
  $('#mode').textContent=d.home_test?'Lokaler Test':d.demo?'Demo':'Raspberry Pi';
  $('#test-banner-title').textContent=d.home_test?'Lokaler Test':'Demo';
  $('#test-banner-copy').textContent=d.home_test?'NVR und Standbilder sind echt. TV und Taster werden simuliert.':'Beispieldaten. TV und Taster werden simuliert.';
  $('#demo-banner').hidden=!d.demo;
  $('#demo-cameras').hidden=!d.demo||d.home_test;
  const canTest=d.protect.configured&&d.config.camera_source==='protect';
  $('#test-protect').disabled=!canTest;
  const testKey=[d.protect.host,d.config.camera_id,canTest].join('|');
  if(testKey!==protectTestKey){protectTestKey=testKey;$('#protect-test-result').textContent=canTest?'Gespeicherten Zugang und Kamera prüfen.':'Kamera verbinden, um den NVR zu prüfen.'}
  const configured=d.config.has_stream||d.config.camera_source==='demo';
  const quality={high:'Hoch',medium:'Mittel',low:'Niedrig'}[d.config.quality]||'';
  $('#camera-label').textContent=configured?d.config.camera_name:'Keine Kamera';
  $('#camera-detail').textContent=d.config.camera_source==='protect'?'UniFi Protect · '+quality:d.config.camera_source==='demo'?'Beispielkamera':d.config.has_stream?'Manueller Stream':'Nicht eingerichtet';
  $('#tv-summary').textContent=!d.demo&&!d.agent_available?'Nicht erreichbar':d.state.active?'Kameraansicht aktiv':'Kameraansicht aus';
  $('#tv-detail').textContent=d.demo?'Im Test simuliert.':!d.agent_available?'Pi-Dienst prüfen.':d.state.active?(d.state.player_health?.progress_fresh?'Videofortschritt erkannt.':d.state.player_health?.state==='stalled'?'Wiedergabe stockt. Neuer Versuch folgt.':'Wiedergabe wird geprüft.'):'TV-Zustand wird nicht ausgelesen.';
  $('#timeout-label').textContent=d.config.auto_off_minutes?d.config.auto_off_minutes+' Minuten':'Deaktiviert';
  $('#countdown').textContent=d.state.active&&d.state.remaining_seconds?'Noch ca. '+Math.ceil(d.state.remaining_seconds/60)+' Min.':d.config.auto_off_minutes?'Ab Start der Kameraansicht.':'';
  $('#diagnostic').textContent=d.state.message||'Keine weiteren Angaben.';
  $('#version').textContent=d.version;
  $('#agent-status').textContent=d.demo?'Simuliert':d.agent_available?'Erreichbar':'Nicht erreichbar';
  $('#integration-status').textContent=d.protect.configured?'Eingerichtet':'Nicht eingerichtet';
  $('#integration-host').textContent=d.protect.host||'';
  $('#protect-status').textContent=d.protect.configured?'Zugang gespeichert':'Nicht eingerichtet';
  for(const button of document.querySelectorAll('[data-action="on"]'))button.disabled=!d.demo&&(!d.agent_available||!d.config.has_stream);
  renderPreview(d);
  if(fill){
    for(const [key,value] of Object.entries(d.config)){
      const field=$('#settings-form').elements[key];
      if(!field)continue;
      if(field.tagName==='SELECT'&&!Array.from(field.options).some(option=>option.value===String(value)))field.add(new Option('Nach '+value+' Minuten',value));
      field.value=value;
    }
    $('#manual-form').elements.stream_url.placeholder='rtsps://…';
    $('#protect-host').value=d.protect.host;
    $('#protect-auth').value=d.protect.auth_mode||'local';
    $('#protect-user').value=d.protect.username||'';
    updateAuthFields();
  }
}
function clearOverviewPreview(){
  overviewRequest++;
  if(overviewSnapshotUrl)URL.revokeObjectURL(overviewSnapshotUrl);
  overviewSnapshotUrl='';
  $('#overview-snapshot').hidden=true;$('#overview-snapshot').removeAttribute('src');
  $('#preview-empty').hidden=false;$('#preview-time').textContent='Kein Standbild';
  $('#preview-button-label').textContent='Standbild laden';
}
function renderPreview(d){
  const key=[d.config.camera_source,d.config.camera_id,d.protect.host].join('|');
  if(key!==overviewCameraKey){clearOverviewPreview();overviewCameraKey=key}
  const ready=d.config.camera_source==='protect'&&d.protect.configured&&!!d.config.camera_id;
  $('#refresh-preview').disabled=!ready||previewBusy;
  $('#setup-callout').hidden=d.config.has_stream||d.config.camera_source==='demo';
  $('#screen-camera').textContent=ready?'Noch kein Standbild':d.config.camera_source==='demo'?'Beispielkamera':d.config.has_stream?'Manueller Stream':'Keine Kamera verbunden';
  $('#preview-note').textContent=ready?'Standbild bei Bedarf laden.':d.config.camera_source==='demo'?'Kein echtes Kamerabild.':d.config.has_stream?'Das Livebild wird auf dem Fernseher wiedergegeben.':'Verbinde eine Kamera, um sie hier anzuzeigen.';
}
$('#refresh-preview').onclick=async()=>{
  if(previewBusy||$('#refresh-preview').disabled)return;
  const requestId=++overviewRequest;
  const key=overviewCameraKey;
  previewBusy=true;$('#refresh-preview').disabled=true;$('#refresh-preview').setAttribute('aria-busy','true');
  let candidate='';
  try{
    const blob=await api('protect/preview',{});
    if(requestId!==overviewRequest||!latest)return;
    candidate=URL.createObjectURL(blob);
    const decoded=new Image();decoded.src=candidate;await decoded.decode();
    if(requestId!==overviewRequest||key!==overviewCameraKey||!latest)return;
    if(overviewSnapshotUrl)URL.revokeObjectURL(overviewSnapshotUrl);
    overviewSnapshotUrl=candidate;candidate='';
    $('#overview-snapshot').src=overviewSnapshotUrl;$('#overview-snapshot').alt='Standbild: '+latest.config.camera_name;
    $('#overview-snapshot').hidden=false;$('#preview-empty').hidden=true;
    $('#preview-time').textContent='Standbild · '+new Date().toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
    $('#preview-button-label').textContent='Aktualisieren';
  }catch(error){if(requestId===overviewRequest)notify(error.name==='EncodingError'?'Standbild konnte nicht angezeigt werden.':error.message)}
  finally{if(candidate)URL.revokeObjectURL(candidate);previewBusy=false;$('#refresh-preview').removeAttribute('aria-busy');if(latest)renderPreview(latest)}
};
async function load(fill=false){const d=await api('status');render(d,fill);if(fill||page()==='camera')refreshCameraList()}
async function refreshCameraList(){
  if(!token||camerasLoading)return;
  camerasLoading=true;
  try{
    const data=await api('cameras');
    const signature=JSON.stringify(data.cameras);
    if(signature!==savedCamerasSignature){
      savedCamerasSignature=signature;
      $('#saved-camera-list').replaceChildren();
      for(const camera of data.cameras){
        const row=document.createElement('div');row.className='saved-camera-row';
        const info=document.createElement('div');const name=document.createElement('strong');name.textContent=camera.name;
        const detail=document.createElement('small');detail.textContent=camera.selected?'Startkamera':!camera.available?'Nicht erreichbar':camera.manual?'Eigener Stream':camera.id.startsWith('demo:')?'Beispielkamera':'UniFi Protect';
        info.append(name,detail);row.append(info);
        const actions=document.createElement('div');actions.className='actions';
        if(!camera.selected){
          const choose=document.createElement('button');choose.className='secondary';choose.textContent=camera.manual?'Als Startkamera':'Für TV einrichten';choose.disabled=!camera.available;
          choose.onclick=()=>busy(choose,async()=>{notify((await api('cameras/select',{camera_id:camera.id,enable_stream:!camera.manual})).message);savedCamerasSignature='';await load(true)});
          actions.append(choose);
          if(camera.manual){
            const remove=document.createElement('button');remove.className='text-button';remove.textContent='Entfernen';
            remove.onclick=()=>{if(confirm('Kamera „'+camera.name+'“ entfernen?'))busy(remove,async()=>{notify((await api('cameras/remove',{camera_id:camera.id})).message);savedCamerasSignature='';await load(true)})};
            actions.append(remove);
          }
        }
        row.append(actions);$('#saved-camera-list').append(row);
      }
    }
    $('#saved-camera-message').textContent=data.cameras.length?'Die Kameras sind in der TV-Ansicht auswählbar.':'UniFi verbinden oder eine eigene Kamera hinzufügen.';
  }catch(error){$('#saved-camera-message').textContent=error.message}
  finally{camerasLoading=false}
}
window.addEventListener('hashchange',()=>{if(page()==='camera')refreshCameraList()});
$('#login-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{const d=await api('login',{password:$('#password').value});token=d.token;sessionStorage.setItem('oma-token',token);$('#password').value='';$('#notice').hidden=true;await load(true)})};
$('#logout').onclick=()=>busy($('#logout'),async()=>{await api('logout',{});loggedOut()});
$('#settings-form').addEventListener('input',()=>$('#save-state').textContent='Ungespeicherte Änderungen');
$('#settings-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{notify((await api('config',Object.fromEntries(new FormData(e.target)))).message);$('#save-state').textContent='Gespeichert.';await load(true)})};
$('#dashboard-password-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{const form=e.target;const body=Object.fromEntries(new FormData(form));const message=$('#dashboard-password-message');message.textContent='';if(body.new_password!==body.confirm_password){message.textContent='Die neuen Passwörter stimmen nicht überein.';return}try{const result=await api('password',body);form.reset();loggedOut();notify(result.message);$('#password').focus()}catch(error){message.textContent=error.message;throw error}})};
$('#manual-form').onsubmit=e=>{e.preventDefault();busy(e.submitter,async()=>{await api('config',Object.fromEntries(new FormData(e.target)));e.target.reset();savedCamerasSignature='';await load(true);notify('Kamera gespeichert.')})};
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>busy(b,async()=>{notify((await api('action',{action:b.dataset.action})).message);await load()}));
async function checkUpdates(){if($('#check-update').disabled)return;lastReleaseCheck=Date.now();$('#update-checked').hidden=true;return busy($('#check-update'),async()=>{try{const d=await api('update');updateRelease=d;updateSupport=d.maintenance;$('#update-result').textContent='Installiert: '+d.current+' · '+(d.available&&!latest?.demo?'Verfügbar: ':'GitHub: ')+d.version;$('#update-release-notes').textContent=d.notes||'Keine zusätzlichen Versionshinweise.';$('#update-release').hidden=false;renderMaintenance(updateSupport);$('#update-checked').textContent='Zuletzt geprüft: '+new Intl.DateTimeFormat('de-DE',{dateStyle:'short',timeStyle:'medium',timeZone:'Europe/Berlin'}).format(new Date());$('#update-checked').hidden=false}catch(error){$('#update-result').textContent=error.message;throw error}})}
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
$('#reset-tv').onclick=()=>{if(confirm('TV-Zugang zurücksetzen? Verbundene TV-Ansichten werden abgemeldet.'))busy($('#reset-tv'),async()=>notify((await api('tv/revoke',{})).message))};

function renderTelemetry(data){
  const view=TelemetryView.view(data);
  $('#health-camera').textContent=view.camera;$('#event-connection').textContent=view.connection;
  $('#health-motion').textContent=data?.enabled?view.motion:'Keine Statusdaten';
  $('#health-note').textContent=view.warning;
  $('#health-warning').hidden=!(data?.enabled&&(data.last_error||!data.camera_fresh||!data.events_fresh));
  $('#health-warning').textContent=view.warning;
  for(const [field,id] of [['last_motion','last-motion'],['last_person','last-person'],['last_vehicle','last-vehicle']]){
    $('#'+id).textContent=view.records[field].label;
    $('#'+id+'-detail').textContent=Number.isFinite(Date.parse(data?.[field]?.occurred_at))?view.records[field].detail:'';
  }
}

function renderCEC(d){
  const c=d.state.cec;
  $('#cec-status').textContent=d.demo?'Im Test simuliert.':!d.agent_available?'Pi-Dienst nicht erreichbar.':c?.message||'CEC-Empfang noch nicht verfügbar.';
  const last=c?.last_key;const at=last?.at?new Date(last.at):null;
  $('#cec-key').textContent=last?'Letzte Taste: '+last.key+' ('+last.code+')'+(at&&!Number.isNaN(at.getTime())?' · '+at.toLocaleString('de-DE',{timeZone:'Europe/Berlin'}):'')+(last.supported?'':' · ohne Aktion'):'Noch keine Taste empfangen.';
  $('#cec-receiver').textContent=c?.receiver_active?'TV-Ansicht empfängt Tasten.':'TV-Empfänger nicht verbunden.';
}

function sameConsole(){try{const host=$('#protect-host').value.trim();return new URL(host.includes('://')?host:'https://'+host).origin===latest?.protect.host}catch{return false}}
function updateAuthFields(){
  const local=$('#protect-auth').value==='local';
  $('#local-login-fields').hidden=!local;$('#local-login-note').hidden=!local;
  $('#key-options-title').textContent=local?'API-Schlüssel (optional)':'API-Schlüssel';
  if(!local)$('#protect-key-options').open=true;
  const saved=latest?.protect;const same=sameConsole()&&saved?.auth_mode===$('#protect-auth').value&&(!local||$('#protect-user').value.trim()===saved.username);
  $('#protect-user').required=local;
  $('#protect-password').required=local&&!(same&&saved?.has_password&&$('#protect-user').value.trim()===saved.username);
  $('#protect-key').required=!local&&!(same&&saved?.has_api_key);
  $('#password-hint').textContent=same&&saved?.has_password?'Gespeichert. Leer lassen, um es beizubehalten.':'';
  $('#key-hint').textContent=same&&saved?.has_api_key?'Gespeichert. Leer lassen, um ihn beizubehalten.':local?'Für Streams und Ereignisse je nach Protect-Version.':'In Protect unter Integrationen erstellen.';
  $('#connect-button').textContent='Verbinden';
}
$('#protect-auth').onchange=()=>{$('#protect-key').value='';$('#protect-password').value='';updateAuthFields()};
$('#protect-user').addEventListener('input',updateAuthFields);
$('#open-manual').onclick=()=>{const manual=$('#manual-camera');manual.open=true;manual.scrollIntoView({behavior:'smooth',block:'center'});$('#manual-form').elements.camera_name.focus()};
$('#test-protect').onclick=()=>busy($('#test-protect'),async()=>{const result=$('#protect-test-result');result.textContent='Verbindung wird geprüft …';try{const d=await api('protect/test',{});result.textContent=d.camera_name+' · '+d.camera_count+' Kamera(s) · '+d.elapsed_ms+' ms · Standbild und Streamadresse geprüft.'}catch(error){result.textContent=error.message;throw error}});
updateAuthFields();

let updateRelease=null,updateSupport=null,updateWatching=false,completedUpdateJob='',lastReleaseCheck=0,lastRenderedAppVersion='';
let updateWatch=null;
try{const saved=JSON.parse(sessionStorage.getItem('kamerablick-update-watch')||'null');if(saved&&typeof saved.watch==='string'&&saved.watch.length>=32&&saved.watch.length<=128)updateWatch=saved}catch{}
function renderMaintenance(support){
  if(latest?.version&&lastRenderedAppVersion!==latest.version){lastRenderedAppVersion=latest.version;updateRelease=null;lastReleaseCheck=0;$('#update-result').textContent='Installiert: '+latest.version+'.';$('#update-release').hidden=true;$('#update-checked').hidden=true}
  updateSupport=support||updateSupport;
  if(!updateSupport)return;
  const job=updateSupport.job;
  $('#maintenance-support').textContent=latest?.home_test?'Updates werden auf dem Raspberry Pi installiert.':updateSupport.message||'';
  renderLastUpdate(job);
  $('#update-setup-help').hidden=!!(updateSupport.available&&updateSupport.persistent)||!!latest?.demo;
  $('#install-update').hidden=!updateRelease?.available||!!latest?.demo;
  $('#install-update').disabled=!(updateRelease?.available&&updateSupport.available&&updateSupport.persistent&&!job?.busy);
  if(job)renderUpdateJob(job);
  if(token&&page()==='maintenance'&&Date.now()-lastReleaseCheck>300000)queueMicrotask(checkUpdates);
}
function renderUpdateJob(job){
  renderLastUpdate(job);
  $('#update-job').hidden=false;
  $('#update-job-title').textContent=job.phase==='complete'?'Update abgeschlossen.':job.phase==='rolled_back'?'Vorherige Version wieder aktiv.':job.phase==='failed'||job.phase==='recovery_failed'?'Update benötigt Aufmerksamkeit.':'Update läuft.';
  $('#update-job-message').textContent=job.message;
  $('#update-progress-bar').hidden=!job.busy;
  $('#update-job-note').textContent=job.busy?'Der Auftrag läuft auf dem Pi weiter.':'Bei Bedarf erneut anmelden. Kamera und TV am Gerät prüfen.';
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
