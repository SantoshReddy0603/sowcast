import {useEffect, useRef, useState} from 'react';
import {errorText, request} from '../api';
import type {RequestBody} from '../types';

type Language = 'en'|'hi'|'kn'|'te'|'ta'|'mr';
type Fact = {label?: string | null; window_start?: string | null; window_end?: string | null; supporting_urls?: string[]; id: string; date: string; value: number; unit: string; latitude: number; longitude: number; source_url: string};
type Answer = {trace_access_token:string; trace_id: string; status: string; note: string; claims: {text: string; evidence_id: string; date: string}[]; facts: Fact[]; formatted_facts: Record<string,string>};
type Trace = {trace: {tools: {name: string; latency_ms: number; status: string; code?: string}[]; guardrail: unknown; error?: string; cache_hit?: boolean}};
type Recognition = {lang: string; start(): void; stop(): void; onresult: ((event: {results: {0: {0: {transcript: string}}}}) => void) | null; onerror: (() => void) | null; onend: (() => void) | null};
const locales: Record<Language,string> = {en:'en-IN', hi:'hi-IN', kn:'kn-IN', te:'te-IN', ta:'ta-IN', mr:'mr-IN'};

export function Ask({plot}: {plot: RequestBody}) {
  const [question, setQuestion] = useState('');
  const [language, setLanguage] = useState<Language>('en');
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [busy, setBusy] = useState(false);
  const [traceDeleted, setTraceDeleted] = useState(false);
  const [deletingTrace, setDeletingTrace] = useState(false);
  const [error, setError] = useState('');
  const [voice, setVoice] = useState('');
  const recognition = useRef<Recognition | null>(null);
  const pending = useRef<AbortController | null>(null);
  const tracePending = useRef<AbortController | null>(null);
  const deletePending = useRef<AbortController | null>(null);
  useEffect(() => {setTrace(null); setTraceDeleted(false); setDeletingTrace(false); return () => {tracePending.current?.abort(); deletePending.current?.abort();};}, [answer?.trace_id]);
  useEffect(() => () => {recognition.current?.stop(); pending.current?.abort(); window.speechSynthesis?.cancel();}, []);
  const speechWindow = window as typeof window & {SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition};
  const Constructor = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
  async function submit() {
    if(!question.trim()) return;
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller;
    setBusy(true); setError(''); setAnswer(null); setTrace(null);
    try {setAnswer(await request<Answer>('/v1/chat', {question, plot, language}, controller.signal));}
    catch(cause) {if(!controller.signal.aborted) setError(errorText(cause));}
    finally {if(!controller.signal.aborted) setBusy(false);}
  }
  function listen() {
    if(!Constructor) return;
    recognition.current?.stop(); const active = new Constructor(); recognition.current = active;
    active.lang = locales[language]; active.onresult = event => {setQuestion(event.results[0][0].transcript); setVoice('Transcript ready. Review it before sending.');};
    active.onerror = () => setVoice('Voice input unavailable. Type your question below.');
    active.onend = () => setVoice(current => current === 'Listening…' ? 'Listening stopped. You can type your question.' : current);
    try {active.start(); setVoice('Listening…');} catch {setVoice('Voice input unavailable. Type your question below.');}
  }
  return <main id="main" className="ask-layout"><p className="eyebrow">Ask about your field</p><h1>Start with the evidence.</h1><p>Answers use this plot’s available evidence. Missing data stays missing. Rules decide the field tasks.</p>
    <form onSubmit={event => {event.preventDefault(); void submit();}}><label htmlFor="answer-language">Answer language</label><select id="answer-language" disabled={busy} value={language} onChange={event => {setLanguage(event.target.value as Language); setAnswer(null); setTrace(null);}}>{Object.entries({en:'English',hi:'हिन्दी',kn:'ಕನ್ನಡ',te:'తెలుగు',ta:'தமிழ்',mr:'मराठी'}).map(([code,label]) => <option key={code} value={code}>{label}</option>)}</select><label htmlFor="field-question">Your question</label><textarea id="field-question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} rows={4} required/><div className="button-row"><button className="primary" disabled={busy || !question.trim()}>{busy ? 'Reading evidence…' : 'Ask Sowcast'}</button><button type="button" onClick={listen} disabled={!Constructor}>Use microphone</button><button type="button" onClick={() => recognition.current?.stop()}>Stop listening</button></div><p className="quiet">{Constructor ? 'Voice recognition may send audio to your browser’s speech service. Review the transcript before sending.' : 'Voice input is unavailable in this browser. Type your question.'}</p><p role="status">{voice}</p></form>
    {error && <p className="error" role="alert">{error}</p>}
    {answer && <section aria-live="polite"><h2>{answer.status === 'verified' ? 'Evidence-linked answer' : 'Agent unavailable'}</h2><p className="notice">{answer.note}</p>{answer.claims.map((claim,index) => {const fact = answer.facts.find(item => item.id === claim.evidence_id); return <article key={index}><p>{claim.text}</p>{fact && <p className="quiet">{fact.label && <span>{fact.label} · </span>}<a href={fact.source_url} target="_blank" rel="noreferrer">Source evidence</a>{fact.supporting_urls?.map(url => <span key={url}> · <a href={url} target="_blank" rel="noreferrer">Reference evidence</a></span>)} · {fact.window_start && `${fact.window_start} to ${fact.window_end} · `}{new Intl.DateTimeFormat(locales[language], {timeZone:'UTC',year:'numeric',month:'short',day:'numeric'}).format(new Date(`${fact.date}T00:00:00Z`))} · <strong>{answer.formatted_facts[fact.id]}</strong> · {fact.latitude}, {fact.longitude}</p>}</article>;})}
      {!!answer.facts.length && <details open><summary>{answer.status === 'verified' ? 'Evidence values behind this answer' : 'Evidence retrieved (no explanation shown)'}</summary><dl>{answer.facts.map(fact => <div key={fact.id}><dt>{fact.label || fact.id} · {fact.date}</dt><dd><strong>{answer.formatted_facts[fact.id]}</strong> · <a href={fact.source_url} target="_blank" rel="noreferrer">Source</a></dd></div>)}</dl></details>}
      {!!answer.claims.length && <div className="button-row"><button disabled={!window.speechSynthesis} onClick={() => {const utterance = new SpeechSynthesisUtterance(answer.claims.map(c => c.text).join(' ')); utterance.lang = locales[language]; window.speechSynthesis.cancel(); window.speechSynthesis.speak(utterance);}}>Read answer aloud</button><button onClick={() => window.speechSynthesis?.cancel()}>Stop speaking</button></div>}
      {answer.status !== 'verified' && <p>Your structured tasks remain available in Plan.</p>}
      <details onToggle={event => {if(event.currentTarget.open && !trace && !traceDeleted) {tracePending.current?.abort(); const controller = new AbortController(); tracePending.current = controller; void request<Trace>(`/v1/traces/${answer.trace_id}`, undefined, controller.signal, {accessToken:answer.trace_access_token}).then(result => {if(!controller.signal.aborted) setTrace(result);}).catch(cause => {if(!controller.signal.aborted) setError(errorText(cause));});}}}><summary>Agent trace</summary><p className="quiet">Trace {answer.trace_id}</p>{traceDeleted ? <p role="status">Trace deleted from this server.</p> : trace ? <><table><thead><tr><th>Tool</th><th>Status</th><th>Latency</th></tr></thead><tbody>{trace.trace.tools.map((tool,index) => <tr key={index}><td>{tool.name}</td><td>{tool.code || tool.status}</td><td>{tool.latency_ms} ms</td></tr>)}</tbody></table><p>Guardrail: {typeof trace.trace.guardrail === 'string' ? trace.trace.guardrail : JSON.stringify(trace.trace.guardrail)}</p>{trace.trace.error && <p>Unavailable: {trace.trace.error}</p>}</> : <p>Loading trace…</p>}{!traceDeleted && <button disabled={deletingTrace} onClick={async () => {
        setDeletingTrace(true); tracePending.current?.abort(); const controller=new AbortController(); deletePending.current=controller;
        try {await request<void>(`/v1/traces/${answer.trace_id}`,undefined,controller.signal,{accessToken:answer.trace_access_token,method:'DELETE'}); if(!controller.signal.aborted) {setTraceDeleted(true); setTrace(null);}}
        catch(cause) {if(!controller.signal.aborted) setError(errorText(cause));}
        finally {if(!controller.signal.aborted) setDeletingTrace(false);}
      }}>{deletingTrace ? 'Deleting trace…' : 'Delete this trace'}</button>}</details>
    </section>}
  </main>;
}
