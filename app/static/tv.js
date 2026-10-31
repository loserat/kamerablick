const $=s=>document.querySelector(s);
const sections=['pairing','home','viewing','sleeping'];
let access='',current='home',lastState=null,busy=false,refreshing=false,noticeTimer,powerPending=false;
let receiverToken='';const remote=new TVRemote.Receiver(crypto.randomUUID());
function notice(message){$('#notice').textContent=message;$('#notice').hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>$('#notice').hidden=true,7000)}
function controls(){const dialog=document.querySelector('dialog[open]');const scope=dialog||$('#'+current);return [...scope.querySelectorAll('[data-nav]')].filter(e=>!e.disabled&&!e.hidden&&e.getClientRects().length)}
function focus(id){const list=controls();const target=list.find(e=>e.dataset.nav===id)||list[0];if(target)target.focus({preventScroll:true})}
function show(name){if(current===name&&!$('#'+name).hidden)return;current=name;for(const id of sections)$('#'+id).hidden=id!==name;requestAnimationFrame(()=>focus())}
function resetAccess(){access='';receiverToken='';localStorage.removeItem('oma-tv-access');localStorage.removeItem('oma-tv-receiver');remote.reset();for(const dialog of document.querySelectorAll('dialog[open]'))dialog.close();show('pairing')}
async function request(path,body){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),20000);try{const response=await fetch('/api/tv/'+path,{signal:controller.signal,method:body?'POST':'GET',headers:{'Content-Type':'application/json',Authorization:'Bearer '+access},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok){if(response.status===401)resetAccess();throw Error(data.error||'Das hat gerade nicht geklappt. Bitte noch einmal versuchen.')}return data}catch(e){if(e.name==='AbortError'||e instanceof TypeError)throw Error('Die Verbindung ist gerade unterbrochen. Bitte kurz warten.');throw e}finally{clearTimeout(timer)}}
function render(state){lastState=state;const health=TelemetryView.view(state.telemetry);$('#demo-badge').hidden=!state.demo;$('#camera-name').textContent=state.camera_name;$('#watch').disabled=!state.ready||busy;$('#camera-state').textContent=state.demo?'Vorschau':state.telemetry?.enabled?health.camera:state.ready?'Bereit':'Nicht bereit';$('#connection-hint').textContent=state.demo?'Vorschau: Hier kannst du die Tasten ausprobieren.':!state.available?'Die Verbindung zur Kameraanzeige fehlt. Bitte um Hilfe bitten.':!state.ready?'Die Kamera muss noch eingerichtet werden. Bitte um Hilfe bitten.':'Die Kameraansicht ist bereit.';$('#viewing-title').textContent=state.camera_name;$('#viewing-label').textContent=state.demo?'VORSCHAU · KEIN ECHTES KAMERABILD':'KAMERAANSICHT';$('#viewing-description').textContent=state.demo?'Später siehst du hier das echte Kamerabild auf dem Fernseher.':state.playback_progress?'Die Kameraansicht ist geöffnet.':'Die Kamera wird verbunden. Bitte einen Moment warten.';$('#remaining').textContent=state.active&&state.remaining_seconds?'Automatisch aus in etwa '+Math.ceil(state.remaining_seconds/60)+' Min.':'';$('#tv-motion').hidden=!state.telemetry?.enabled;$('#tv-motion').textContent='Letzte Bewegung: '+health.records.last_motion.label+(state.telemetry?.events_fresh?'':' · Verbindung nicht aktuell');if(current!=='sleeping'){if(state.active)show('viewing');else if(current==='viewing')show('home')}if(document.activeElement?.disabled)focus()}
async function refresh(){if(!access||refreshing||busy||powerPending)return;refreshing=true;try{render(await request('status'))}catch(e){$('#connection-hint').textContent=e.message;$('#watch').disabled=true;$('#camera-state').textContent='Verbindung fehlt';$('#tv-motion').textContent='Die Anzeige ist gerade nicht aktuell.';if(document.activeElement===$('#watch'))focus();if(current==='viewing')notice(e.message)}finally{refreshing=false}}
async function action(command){if(busy||!access)return;busy=true;const button=document.activeElement;if(button?.tagName==='BUTTON')button.setAttribute('aria-busy','true');try{await request('action',{action:command});if(command==='off'){show('sleeping');$('#sleep-message').textContent=lastState?.demo?'Vorschau: Der Fernseher würde jetzt ausgeschaltet.':'Standby wurde angefordert. Der TV-Zustand ist nicht bestätigt.'}else if(command==='menu')show('home');else show('viewing');render(await request('status'))}catch(e){notice(e.message)}finally{busy=false;if(button)button.removeAttribute('aria-busy');if(lastState)$('#watch').disabled=!lastState.ready;focus()}}
function openDialog(id,initial){const dialog=$('#'+id);dialog.showModal();requestAnimationFrame(()=>focus(initial))}
function closeDialog(id,returnTo){$('#'+id).close();focus(returnTo)}
function back(){if(busy)return;if($('#power-dialog').open){closeDialog('power-dialog','power');return}if($('#help-dialog').open){closeDialog('help-dialog','help');return}if(current==='viewing'){action('menu');return}if(current==='sleeping')show('home');else focus('watch')}
$('#watch').onclick=()=>action('on');
$('#help').onclick=()=>openDialog('help-dialog','close-help');
$('#close-help').onclick=()=>closeDialog('help-dialog','help');
$('#power').onclick=()=>openDialog('power-dialog','cancel-power');
$('#cancel-power').onclick=()=>closeDialog('power-dialog','power');
$('#confirm-power').onclick=()=>{closeDialog('power-dialog','power');powerPending=true;action('off').finally(()=>powerPending=false)};
$('#back-to-menu').onclick=()=>action('menu');$('#wake').onclick=()=>show('home');
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('cancel',e=>{e.preventDefault();back()});
function handleKey(key,repeat=false){
  const arrows=['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'];
  const ok=['Enter','Select','Accept'];const backKeys=['Escape','Backspace','BrowserBack','GoBack'];
  if(![...arrows,...ok,...backKeys].includes(key)||repeat||busy)return;
  if(backKeys.includes(key)){back();return}
  const list=controls();if(!list.length)return;
  const selected=list.find(b=>b===document.activeElement);
  if(ok.includes(key)){(selected||list[0]).click();return}
  const items=list.map(b=>{const r=b.getBoundingClientRect();return {id:b.dataset.nav,x:r.x+r.width/2,y:r.y+r.height/2}});
  focus(TVNavigation.next(items,selected?.dataset.nav,key));
}
document.addEventListener('keydown',e=>{
  if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter','Select','Accept','Escape','Backspace','BrowserBack','GoBack'].includes(e.key))return;
  e.preventDefault();handleKey(e.key,e.repeat);
});
async function pollRemote(){
  if(!access||!receiverToken||document.hidden){remote.reset();setTimeout(pollRemote,300);return}
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),1500);
  try{
    const response=await fetch('/api/tv/input',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json',Authorization:'Bearer '+receiverToken},body:JSON.stringify(remote.request())});
    if(response.status===401){receiverToken='';localStorage.removeItem('oma-tv-receiver');notice('Fernbedienungszugang zurückgesetzt. TV-Anwendung bitte neu starten.');return}
    if(!response.ok)throw Error('Tastenempfang unterbrochen');
    const keys=remote.accept(await response.json());
    for(const key of keys){handleKey(key);await new Promise(requestAnimationFrame)}
  }catch(e){remote.reset()}finally{clearTimeout(timer);setTimeout(pollRemote,300)}
}
function clock(){$('#clock').textContent=new Intl.DateTimeFormat('de-DE',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Berlin'}).format(new Date())}clock();setInterval(clock,30000);
async function init(){
  const params=new URLSearchParams(location.hash.slice(1));
  access=params.get('access')||localStorage.getItem('oma-tv-access')||'';
  receiverToken=params.get('receiver')||localStorage.getItem('oma-tv-receiver')||'';
  if(params.has('access')||params.has('receiver'))history.replaceState(null,'','/tv');
  if(!access){show('pairing');return}
  localStorage.setItem('oma-tv-access',access);
  if(receiverToken)localStorage.setItem('oma-tv-receiver',receiverToken);
  show('home');focus();await refresh();if(current==='home'&&lastState?.ready)focus('watch');
}
init().catch(()=>{resetAccess();notice('Bitte die TV-Ansicht erneut über das Dashboard öffnen.')});
setInterval(refresh,2000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
setTimeout(pollRemote,300);
