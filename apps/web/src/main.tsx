import {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {request, errorText, ApiFailure} from './api';
import {Plot} from './views/Plot';
import {Reliability} from './views/Reliability';
import {Ask} from './views/Ask';
import {PlanView} from './views/Plan';
import type {Plan, RequestBody} from './types';
import './styles/app.css';

function App() {
  const [screen, setScreen] = useState<'plot'|'plan'|'ask'|'reliability'>('plot');
  const [plan, setPlan] = useState<Plan | null>(null);
  const [body, setBody] = useState<RequestBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [requestId, setRequestId] = useState<string | undefined>();
  const pending = useRef<AbortController | null>(null);
  const heading = useRef<HTMLDivElement>(null);
  useEffect(() => {heading.current?.focus(); window.scrollTo(0,0);}, [screen, busy]);
  useEffect(() => () => pending.current?.abort(), []);
  async function load(next: RequestBody) {
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller;
    setBody(next); setScreen('plan'); setBusy(true); setError(''); setPlan(null); setRequestId(undefined);
    try {setPlan(await request<Plan>('/v1/plans', next, controller.signal));}
    catch(cause) {if (!controller.signal.aborted) {setError(errorText(cause)); if(cause instanceof ApiFailure) setRequestId(cause.requestId);}}
    finally {if (!controller.signal.aborted) setBusy(false);}
  }
  function edit() {pending.current?.abort(); setBusy(false); setScreen('plot');}
  return <><a className="skip-link" href="#main">Skip to main content</a><header className="site-header"><a className="wordmark" href="/" onClick={event => {event.preventDefault(); edit();}}><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 27V13M16 21C6 21 4 14 5 8c7 0 11 4 11 10M16 16C16 8 20 4 27 4c1 7-3 12-11 12"/></svg>Sowcast<span>FIELD NOTES, FORWARD</span></a><nav aria-label="Main navigation"><button onClick={edit} aria-current={screen === 'plot' ? 'page' : undefined}>Plot</button><button disabled={!body} onClick={() => {if(body) {if(plan) setScreen('plan'); else void load(body);}}} aria-current={screen === 'plan' ? 'page' : undefined}>Plan</button><button disabled={!body} onClick={() => setScreen('ask')} aria-current={screen === 'ask' ? 'page' : undefined}>Ask</button><button disabled={!body} onClick={() => setScreen('reliability')} aria-current={screen === 'reliability' ? 'page' : undefined}>Reliability</button></nav></header><div ref={heading} tabIndex={-1} className="screen-focus" aria-label={{plot:'Choose your plot', plan:'Your field plan', ask:'Ask about your field', reliability:'Forecast reliability'}[screen]}/>
    {screen === 'reliability' && body ? <Reliability plot={body}/> : screen === 'ask' && body ? <Ask plot={body}/> : screen === 'plot' ? <Plot onSubmit={next => void load(next)} initial={body}/> : busy ? <main id="main" className="loading-plan" aria-busy="true"><p className="eyebrow" role="status">Reading the forecast for your plot…</p><div className="skeleton skeleton-title"/><div className="skeleton skeleton-strip"/>{[0,1,2].map(n => <div key={n} className="skeleton skeleton-row"/>)}</main> : error ? <main id="main" className="error-screen"><p className="eyebrow">Evidence unavailable</p><h1>A pause in the data.</h1><p className="error" role="alert">{error}</p>{requestId && <p className="quiet">Request {requestId}</p>}<p>No replacement weather or plan has been supplied.</p><div className="button-row"><button className="primary" onClick={() => body && void load(body)}>Try again</button><button onClick={edit}>Return to plot</button></div></main> : plan ? <PlanView key={plan.evidence.fetched_at} plan={plan} retry={() => body && void load(body)} editing={edit}/> : <main id="main" className="empty"><h1>No plan yet.</h1><button onClick={edit}>Choose your plot</button></main>}
    <footer className="site-footer"><span>Sowcast · A field notebook</span><span>Decision support. Confirm field conditions with your local extension officer.</span></footer></>;
}

createRoot(document.getElementById('root')!).render(<App/>);
