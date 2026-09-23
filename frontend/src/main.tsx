import React,{useEffect,useRef,useState} from 'react';
import{createRoot}from'react-dom/client';
import{request,openSession,Result,Trace}from'./api/client';
import{dictionary,Language}from'./i18n';
import{VoiceConnection}from'./voice/VoiceConnection';
import{Orb}from'./components/Orb';
import{Icon}from'./components/Icon';
import'./styles/app.css';

function App(){
 const[lang,setLang]=useState<Language>('ru'),[page,setPage]=useState('assistant'),[status,setStatus]=useState('idle');
 const[connected,setConnected]=useState(false),[level,setLevel]=useState(0),[text,setText]=useState(''),[partial,setPartial]=useState('');
 const[trace,setTrace]=useState<Trace|null>(null),[result,setResult]=useState<Result|null>(null),[history,setHistory]=useState<{role:string;content:string}[]>([]);
 const[keyboard,setKeyboard]=useState(false),[error,setError]=useState(''),[diagnostics,setDiagnostics]=useState<any>(null),[ready,setReady]=useState(false),[duration,setDuration]=useState(0);
 const voice=useRef<VoiceConnection|null>(null),audio=useRef<HTMLAudioElement|null>(null),isConnected=useRef(false),speechStart=useRef(0),speechEnd=useRef(0),busy=useRef(false);
 const t=dictionary[lang];const currentLanguage=useRef(lang);currentLanguage.current=lang;
 const refresh=async()=>{try{setDiagnostics(await request('/api/diagnostics'));}catch(e){setError(String(e));}};
 useEffect(()=>{openSession().then(s=>{setHistory(s.history);setReady(true);refresh();}).catch(e=>setError(e.message));return()=>{voice.current?.stop();audio.current?.pause();};},[]);
 useEffect(()=>{document.documentElement.lang=lang;},[lang]);
 useEffect(()=>{if(status!=='speaking')return;const id=setInterval(()=>setDuration((performance.now()-speechStart.current)/1000),100);return()=>clearInterval(id);},[status]);
 const stopAudio=()=>{if(audio.current){audio.current.pause();audio.current.removeAttribute('src');audio.current.load();audio.current=null;}};
 const play=(r:Result)=>{if(!r.audio_url)return;stopAudio();const a=new Audio(r.audio_url);audio.current=a;
   a.onplaying=()=>{setStatus('answering');if(speechEnd.current){const value=performance.now()-speechEnd.current;setTrace(prev=>prev?{...prev,latency:{...prev.latency,client_first_audio_ms:Math.round(value)}}:prev);}};
   a.onended=()=>{setStatus(isConnected.current?'listening':'idle');request<Trace>(`/api/trace/${r.trace.request_id}`).then(server=>setTrace(prev=>prev?.request_id===server.request_id?{...server,latency:{...server.latency,client_first_audio_ms:prev.latency.client_first_audio_ms??null}}:prev)).catch(()=>{});};
   a.onerror=()=>{setError(dictionary[currentLanguage.current].audioError);setStatus(isConnected.current?'listening':'idle');};
   a.play().catch(()=>{setError(dictionary[currentLanguage.current].audioError);setStatus(isConnected.current?'listening':'idle');});
 };
 const receiveResult=(r:Result)=>{setResult(r);setTrace(r.trace);setPartial(r.trace.transcript);setHistory(h=>[...h,{role:'user',content:r.trace.transcript},{role:'assistant',content:r.response}].slice(-40));busy.current=false;setStatus(isConnected.current?'listening':'idle');play(r);};
 const disconnect=()=>{voice.current?.stop();voice.current=null;isConnected.current=false;setConnected(false);setLevel(0);setStatus('idle');};
 const toggleMic=async()=>{if(connected){disconnect();return;}setError('');setStatus('connecting');
  try{const v=new VoiceConnection();voice.current=v;await v.start(event=>{
   if(event.type==='ready')setStatus('listening');
   if(event.type==='speech_started'){stopAudio();speechStart.current=performance.now();setDuration(0);setPartial('');setStatus('speaking');}
   if(event.type==='speech_stopped'){speechEnd.current=performance.now();setStatus('thinking');busy.current=true;}
   if(event.type==='partial'||event.type==='final')setPartial(event.text);
   if(event.type==='result')receiveResult(event.data);
   if(event.type==='error'){setError(event.message);busy.current=false;}
   if(event.type==='closed'){disconnect();busy.current=false;}
  },setLevel,()=>{if(audio.current&&!audio.current.paused){stopAudio();setStatus('speaking');speechStart.current=performance.now();}});
  isConnected.current=true;setConnected(true);setStatus('listening');
  }catch(e){disconnect();setError((e as Error).message);}
 };
 const sendText=async(e:React.FormEvent)=>{e.preventDefault();if(!text.trim()||busy.current)return;busy.current=true;stopAudio();setError('');setStatus('thinking');speechEnd.current=performance.now();
  try{const r=await request<Result>('/api/route','POST',{text,request_id:crypto.randomUUID()});setText('');receiveResult(r);}catch(e){setError((e as Error).message);busy.current=false;setStatus(connected?'listening':'idle');}
 };
 const end=async()=>{disconnect();stopAudio();try{await request('/api/session','DELETE');const s=await openSession();setHistory(s.history);setTrace(null);setResult(null);setPartial('');setDuration(0);setError('');}catch(e){setError(String(e));}};
 const ms=(n:number|null|undefined)=>n==null?'—':`${Math.round(n).toLocaleString()} ms`;
 const healthy=diagnostics?.providers?.openai?.configured;
 return <><header><a className="brand" href="/" aria-label="Voice Router"><span className="brand-mark"><i/><i/><i/></span><span>Voice Router<small>HackAlem <b>•</b> Demo</small></span></a>
  <nav>{['assistant','instructions','diagnostics'].map(p=><button key={p} className={page===p?'nav-active':''} onClick={()=>{setPage(p);if(p==='diagnostics')refresh();}}>{t[p as 'assistant']}</button>)}</nav>
  <div className="language"><button className={lang==='kk'?'selected':''} onClick={()=>setLang('kk')}>KAZ</button><button className={lang==='ru'?'selected':''} onClick={()=>setLang('ru')}>RUS</button></div></header>
 <main>{page==='assistant'?<>
 <div className="intro"><span className="eyebrow"><span className="small-dot"/>{t.eyebrow}</span><h1>{t.headline}<span>.</span></h1><p>{t.subhead}</p></div>
 <div className="workspace"><section className="assistant-stage" aria-label={t.assistant}>
  <div className="stage-badge"><Icon name="shield" size={14}/><span>RU / KZ / MIXED</span><span className="separator"/>AI VOICE</div>
  <Orb level={level} active={connected}/>
  <div className="state" aria-live="polite"><span className={'state-dot '+(connected?'on':'')}/>{t[status as 'idle']||status}</div>
  <div className={'transcript '+(partial?'has-text':'')}>{partial?`«${partial}»`:t.placeholder}</div>
  <div className="voice-controls"><button className={'round secondary '+(keyboard?'pressed':'')} aria-label={t.keyboard} title={t.keyboard} onClick={()=>setKeyboard(!keyboard)}><Icon name="keyboard"/></button><button className={'round microphone '+(connected?'recording':'')} aria-label={connected?t.stop:t.mic} title={connected?t.stop:t.mic} onClick={toggleMic} disabled={!ready||!healthy||status==='connecting'}><Icon name="mic" size={31}/></button><button className="round end" aria-label={t.end} title={t.end} onClick={end}><Icon name="end"/></button></div>
  <div className="voice-meta"><span>{t.pause}</span><b>·</b><span>{duration.toFixed(1)} s</span></div>
  {keyboard&&<form className="debug-input" onSubmit={sendText}><label htmlFor="debug-text">{t.input}</label><div><input id="debug-text" value={text} maxLength={4000} onChange={e=>setText(e.target.value)} autoFocus/><button disabled={!text.trim()||status==='thinking'||!healthy}>{t.send}</button></div></form>}
  {error&&<div role="alert" className="error">{error}</div>}
  {!healthy&&diagnostics&&<div className="error">{t.keyMissing}</div>}
  {result&&<div className="spoken-response"><span>{t.agent}</span><p>{result.response}</p><button title={t.retry} aria-label={t.retry} onClick={()=>play(result)}><Icon name="speaker" size={19}/></button></div>}
  <div className="privacy"><Icon name="shield" size={15}/>{t.privacy}</div>
 </section>
 <aside className="trace-panel"><div className="trace-header"><span className="trace-icon"><Icon name="pulse"/></span><h2>{t.decision}</h2><span className="live-pill"><i/>{t.live}</span></div>
  <div className="selected-scenario"><label>{t.selected}</label><h3>{trace?.scenario_name||(trace?.decision==='clarify'?(lang==='ru'?'Нужно уточнение':'Нақтылау қажет'):t.waiting)}</h3><span className="scenario-id">{trace?.scenario_id||'—'}</span></div>
  <div className="trace-section"><label>{t.reason}</label><p>{trace?.reason_short||t.reasonEmpty}</p></div>
  <div className="trace-section"><label>{t.alternative}</label>{trace?.alternatives.length?trace.alternatives.map(a=><div className="alternative" key={a.scenario_id}><span>{lang==='kk'?a.name_kk:a.name_ru}</span><b>{a.confidence.toFixed(2)}</b></div>):<span className="muted">{trace?t.none:'—'}</span>}</div>
  <div className="confidence-row"><span>{t.confidence}</span><strong>{trace?trace.confidence.toFixed(2):'—'}</strong></div><progress value={trace?.confidence||0} max="1" aria-label="AI confidence"/><p className="confidence-note">{t.heuristic}</p>
  <div className="metrics"><div><span>{t.routing}</span><b>{ms(trace?.latency.router_ms)}</b></div><div><span>{t.firstAudio}</span><b>{ms(trace?.latency.client_first_audio_ms??trace?.latency.first_audio_ms)}</b></div><div><span>{t.total}</span><b>{ms(trace?.latency.total_ms)}</b></div></div>
  <div className="provider-row"><span>{trace?.provider||'OpenAI'} <small>Router</small></span><span>{trace?.decision||'STANDBY'}</span></div>
  {trace&&<details><summary>{t.trace}<Icon name="arrow" size={15}/></summary><pre>{JSON.stringify({trace,state:result?.state,backend:result?.backend},null,2)}</pre></details>}
 </aside></div>
 <section className="history"><div className="section-heading"><h2>{t.history}</h2><button onClick={end}>{t.reset}<Icon name="arrow" size={15}/></button></div>{history.length?history.map((m,i)=><div key={i} className={'message '+m.role}><span>{m.role==='user'?t.you:t.agent}</span><p>{m.content}</p></div>):<p className="muted">{t.emptyHistory}</p>}</section>
 </>:page==='instructions'?<section className="page-card"><span className="eyebrow">VOICE ROUTER / GUIDE</span><h1>{t.instructionTitle}</h1><ol className="steps">{t.steps.map(s=><li key={s}>{s}</li>)}</ol><div className="safety"><Icon name="shield"/>{t.safety}</div><p>{t.demo}</p></section>:<section className="page-card"><div className="section-heading"><h1>{t.diagnostics}</h1><button onClick={refresh}>{t.refresh}</button></div><p className="muted">{t.measured}</p><div className="diagnostic-grid">{['openai'].map(p=><article key={p}><label>{p.toUpperCase()}</label><h3>{diagnostics?.providers?.[p]?.configured?t.ready:t.missing}</h3><p>{diagnostics?.providers?.[p]?.model||'—'}</p><small>Circuit: {diagnostics?.providers?.[p]?.circuit||'—'}</small></article>)}{[[t.catalog,diagnostics?.scenario_count],[t.mode,diagnostics?.mode?.toUpperCase()],[t.sessions,diagnostics?.active_sessions],['Router p50',ms(diagnostics?.router_p50_ms)],['Router p95',ms(diagnostics?.router_p95_ms)],[t.errorRate,diagnostics?.error_rate==null?'—':(diagnostics.error_rate*100).toFixed(1)+'%']].map(([label,value])=><article key={label}><label>{label}</label><h3>{value??'—'}</h3></article>)}</div></section>}
 </main><footer><span className="footer-mark">VOICE ROUTER</span><p>{t.demo}</p><span>V1.0</span></footer></>;
}
createRoot(document.getElementById('root')!).render(<App/>);
