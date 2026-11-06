const $ = selector => document.querySelector(selector);
const sections = ['pairing', 'home', 'viewing', 'sleeping'];
const remote = new TVRemote.Receiver(crypto.randomUUID());
let access = '', receiverToken = '', current = 'home', lastState = null;
let busy = false, refreshing = false, powerPending = false, noticeTimer;
let menuFocus = '', catalogSignature = '';

function text(selector, value) {
  const element = $(selector);
  if (element.textContent !== value) element.textContent = value;
}
function notice(message) {
  text('#notice', message); $('#notice').hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => $('#notice').hidden = true, 7000);
}
function controls() {
  const scope = document.querySelector('dialog[open]') || $('#' + current);
  return [...scope.querySelectorAll('[data-nav]')].filter(element =>
    !element.disabled && !element.hidden && element.getClientRects().length);
}
function focus(id) {
  const list = controls();
  const target = list.find(element => element.dataset.nav === id) || list[0];
  if (!target) return;
  target.focus({preventScroll: true});
  target.scrollIntoView({block: 'nearest', inline: 'nearest'});
  if (target.dataset.cameraId) menuFocus = target.dataset.nav;
}
function show(name) {
  if (current === name && !$('#' + name).hidden) return;
  current = name;
  for (const id of sections) $('#' + id).hidden = id !== name;
  text('#key-hint', name === 'viewing' ? 'Zurück: andere Kamera wählen' : 'Pfeiltasten: auswählen · OK: ansehen');
  requestAnimationFrame(() => focus(name === 'home' ? menuFocus : undefined));
}
function resetAccess() {
  access = ''; receiverToken = '';
  localStorage.removeItem('oma-tv-access'); localStorage.removeItem('oma-tv-receiver');
  remote.reset();
  for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
  show('pairing');
}
async function request(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch('/api/tv/' + path, {
      signal: controller.signal, method: body ? 'POST' : 'GET',
      headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + access},
      body: body ? JSON.stringify(body) : undefined
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) resetAccess();
      throw Error(data.error || 'Das hat nicht geklappt. Bitte noch einmal versuchen.');
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof TypeError)
      throw Error('Verbindung unterbrochen. Bitte kurz warten.');
    throw error;
  } finally { clearTimeout(timer); }
}
function cameraButton(camera) {
  const button = document.createElement('button');
  button.className = 'camera-tile'; button.dataset.nav = 'camera:' + camera.id;
  button.dataset.cameraId = camera.id; button.dataset.available = String(camera.available);
  const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  icon.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#camera-glyph'); icon.append(use);
  const title = document.createElement('span');
  title.className = 'camera-title'; title.textContent = camera.name;
  button.append(icon, title);
  if (!camera.available) {
    const note = document.createElement('span');
    note.className = 'camera-note'; note.textContent = 'Nicht erreichbar'; button.append(note);
  }
  button.onclick = () => action('on', camera.id);
  return button;
}
function renderCameras(state) {
  const cameras = state.cameras || [];
  const signature = JSON.stringify(cameras.map(camera => [camera.id, camera.name, camera.available]));
  if (signature !== catalogSignature) {
    const initial = catalogSignature === '';
    const previous = initial ? '' : document.activeElement?.dataset.nav || menuFocus;
    $('#tv-cameras').replaceChildren(...cameras.map(cameraButton));
    $('#tv-cameras').dataset.count = String(cameras.length); catalogSignature = signature;
    if ((initial || !menuFocus) && state.selected_camera) menuFocus = 'camera:' + state.selected_camera;
    if (current === 'home' && !busy) requestAnimationFrame(() => focus(previous || menuFocus));
  }
  for (const button of $('#tv-cameras').querySelectorAll('button'))
    button.disabled = button.dataset.available !== 'true' || !state.available || busy;
  $('#empty-state').hidden = cameras.length > 0;
  text('#empty-message', 'Die Kameras werden noch eingerichtet. Bitte um Hilfe bitten.');
  text('#connection-hint', !state.available ? 'Verbindung unterbrochen. Bitte kurz warten.' :
    cameras.length && !cameras.some(camera => camera.available) ? 'Die Kameras sind gerade nicht erreichbar.' : '');
}
function render(state) {
  lastState = state; $('#demo-badge').hidden = !state.demo;
  renderCameras(state); text('#viewing-title', state.camera_name || 'Kamera');
  text('#viewing-description', state.demo ? 'Vorschau · kein Livebild' :
    state.playback_progress ? 'Zurück führt zur Kameraauswahl.' : 'Kamera wird verbunden …');
  if (current !== 'sleeping') {
    if (state.active) show('viewing');
    else if (current === 'viewing') show('home');
  }
  if (!busy && document.activeElement?.disabled) focus(menuFocus);
}
async function refresh() {
  if (!access || refreshing || busy || powerPending) return;
  refreshing = true;
  try { render(await request('status')); }
  catch (error) {
    text('#connection-hint', error.message);
    for (const button of $('#tv-cameras').querySelectorAll('button')) button.disabled = true;
    if (current === 'viewing') notice(error.message);
  } finally { refreshing = false; }
}
async function action(command, cameraId) {
  if (busy || !access) return;
  busy = true;
  const button = document.activeElement;
  if (button?.tagName === 'BUTTON') button.setAttribute('aria-busy', 'true');
  if (command === 'on') {
    if (cameraId) menuFocus = 'camera:' + cameraId;
    const camera = lastState?.cameras?.find(item => item.id === cameraId);
    text('#viewing-title', camera?.name || lastState?.camera_name || 'Kamera');
    text('#viewing-description', 'Kamera wird verbunden …');
    $('#back-to-menu').disabled = true;
    show('viewing');
  }
  try {
    const body = {action: command};
    if (cameraId) body.camera_id = cameraId;
    await request('action', body);
    if (command === 'off') {
      show('sleeping'); text('#sleep-message', lastState?.demo ? 'Ausschalten wird hier nur simuliert.' : '');
    } else if (command === 'menu') show('home');
    else show('viewing');
    render(await request('status'));
  } catch (error) {
    if (command === 'on') show('home');
    notice(error.message);
  }
  finally {
    busy = false;
    $('#back-to-menu').disabled = false;
    if (button) button.removeAttribute('aria-busy');
    if (lastState) renderCameras(lastState);
    focus(current === 'home' ? menuFocus : undefined);
  }
}
function closePower() { $('#power-dialog').close(); focus('power'); }
function back() {
  if (busy) return;
  if ($('#power-dialog').open) { closePower(); return; }
  if (current === 'viewing') { action('menu'); return; }
  if (current === 'sleeping') show('home');
  else focus(menuFocus);
}
$('#power').onclick = () => {
  if (busy) return;
  $('#power-dialog').showModal(); requestAnimationFrame(() => focus('cancel-power'));
};
$('#cancel-power').onclick = closePower;
$('#confirm-power').onclick = () => {
  closePower(); powerPending = true; action('off').finally(() => powerPending = false);
};
$('#power-dialog').addEventListener('cancel', event => { event.preventDefault(); back(); });
$('#back-to-menu').onclick = () => action('menu'); $('#wake').onclick = () => show('home');
const arrows = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
const ok = ['Enter', 'Select', 'Accept'];
const backKeys = ['Escape', 'Backspace', 'BrowserBack', 'GoBack'];
function handleKey(key, repeat = false) {
  if (![...arrows, ...ok, ...backKeys].includes(key) || repeat || busy) return;
  if (backKeys.includes(key)) { back(); return; }
  const list = controls(); if (!list.length) return;
  const selected = list.find(element => element === document.activeElement);
  if (ok.includes(key)) { (selected || list[0]).click(); return; }
  const items = list.map(element => {
    const r = element.getBoundingClientRect();
    return {id: element.dataset.nav, x: r.x + r.width / 2, y: r.y + r.height / 2,
      group: element.dataset.cameraId ? 'cameras' : undefined};
  });
  focus(TVNavigation.next(items, selected?.dataset.nav, key));
}
document.addEventListener('keydown', event => {
  if (![...arrows, ...ok, ...backKeys].includes(event.key)) return;
  event.preventDefault(); handleKey(event.key, event.repeat);
});
async function pollRemote() {
  if (!access || !receiverToken || document.hidden) {
    remote.reset(); setTimeout(pollRemote, 300); return;
  }
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch('/api/tv/input', {
      method: 'POST', signal: controller.signal,
      headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + receiverToken},
      body: JSON.stringify(remote.request())
    });
    if (response.status === 401) {
      receiverToken = ''; localStorage.removeItem('oma-tv-receiver');
      notice('Die Fernbedienung muss erneut verbunden werden. Bitte um Hilfe bitten.'); return;
    }
    if (!response.ok) throw Error('Tastenempfang unterbrochen');
    for (const key of remote.accept(await response.json())) {
      handleKey(key); await new Promise(requestAnimationFrame);
    }
  } catch (error) { remote.reset(); }
  finally { clearTimeout(timer); setTimeout(pollRemote, 300); }
}
function clock() {
  text('#clock', new Intl.DateTimeFormat('de-DE', {hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin'}).format(new Date()));
}
clock(); setInterval(clock, 30000);
async function init() {
  const params = new URLSearchParams(location.hash.slice(1));
  access = params.get('access') || localStorage.getItem('oma-tv-access') || '';
  receiverToken = params.get('receiver') || localStorage.getItem('oma-tv-receiver') || '';
  if (params.has('access') || params.has('receiver')) history.replaceState(null, '', '/tv');
  if (!access) { show('pairing'); return; }
  localStorage.setItem('oma-tv-access', access);
  if (receiverToken) localStorage.setItem('oma-tv-receiver', receiverToken);
  show('home'); await refresh();
  if (current === 'home') focus(menuFocus);
}
init().catch(() => { resetAccess(); notice('Die TV-Ansicht muss noch eingerichtet werden.'); });
setInterval(refresh, 2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
setTimeout(pollRemote, 300);
