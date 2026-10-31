(function(root){
  function timestamp(record,now){
    if(!record||typeof record.occurred_at!=='string')return null;
    const date=new Date(record.occurred_at);if(!Number.isFinite(date.getTime()))return null;
    const age=Math.max(0,(now-date.getTime())/1000);
    const amount=age<60?Math.floor(age):age<3600?Math.floor(age/60):age<86400?Math.floor(age/3600):Math.floor(age/86400);
    const unit=age<60?'second':age<3600?'minute':age<86400?'hour':'day';
    const relative=age<10?'Gerade eben':new Intl.RelativeTimeFormat('de',{numeric:'always'}).format(-amount,unit);
    const absolute=new Intl.DateTimeFormat('de-DE',{dateStyle:'short',timeStyle:'short',timeZone:'Europe/Berlin'}).format(date);
    return {label:relative,detail:absolute+' · von Protect gemeldet'};
  }
  function view(data,now=Date.now()){
    data=data||{};
    let camera='Noch nicht eingerichtet',connection='Nicht verbunden';
    if(!data.enabled){camera=data.reason==='demo'?'Beispielkamera':data.reason==='manual'?'Stream ohne Statusdaten':'Noch nicht eingerichtet';connection='Keine Ereignisdaten'}
    else{camera=!data.camera_fresh?'Status nicht aktuell':({CONNECTED:'Online',CONNECTING:'Verbindet …',DISCONNECTED:'Offline'}[data.camera_state]||'Unbekannt');connection=data.events_fresh?'Verbunden':data.events_state==='unsupported'?'Nicht unterstützt':data.events_state==='auth_error'?'Schlüssel prüfen':data.events_state==='certificate_error'?'Zertifikat prüfen':data.events_state==='connecting'?'Verbindet …':'Unterbrochen'}
    const records={};
    for(const [field,capability]of [['last_motion',null],['last_person','person'],['last_vehicle','vehicle']]){
      records[field]=timestamp(data[field],now)||{label:!data.enabled?'Nicht verfügbar':capability&&Array.isArray(data.supported_smart)&&!data.supported_smart.includes(capability)?'Nicht unterstützt':'Noch nicht empfangen',detail:!data.enabled?'Protect-Zugang für Ereignisse erforderlich.':'Hier empfangene Ereignisse; keine rückwirkende Historie.'};
    }
    return {camera,connection,records,motion:data.motion_active===true?'Bewegung erkannt':data.motion_active===false?'Bewegung beendet':'Aktueller Bewegungszustand unbekannt',warning:data.last_error||(!data.enabled?'Status- und Ereigniswerte benötigen eine eingerichtete Protect-Kamera.':!data.events_fresh?'Ereignisverbindung fehlt oder ist nicht aktuell. Gespeicherte Zeitpunkte bleiben sichtbar.':'Erfasst werden hier empfangene Ereignisse. Lücken bei Neustarts und Verbindungsunterbrechungen werden nicht nachgeladen.')};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={view};else root.TelemetryView={view};
})(typeof window==='undefined'?{}:window);
