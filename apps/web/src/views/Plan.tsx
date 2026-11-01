import {useEffect, useState} from 'react';
import {request, errorText} from '../api';
import {WeatherChart} from '../components/WeatherChart';
import type {Plan as PlanData, Soil, Flood, Power, Provenance, ClimateNormals} from '../types';

type Optional<T> = {status:'idle' | 'loading' | 'error' | 'ready'; data?:T; error?:string};
function Freshness({data}: {data: Provenance}) {
  return <footer className="freshness"><a href={data.attribution_url}>{data.attribution_text}</a> · Fetched {new Date(data.fetched_at).toLocaleString('en-IN')}{data.is_stale && <strong> · Stale</strong>} {data.licence_url && <> · <a href={data.licence_url}>Licence</a></>}<span>{data.modifications}</span></footer>;
}
export function PlanView({plan, retry, editing}: {plan:PlanData; retry:()=>void; editing:()=>void}) {
  const [soil, setSoil] = useState<Optional<Soil>>({status:'idle'});
  const [flood, setFlood] = useState<Optional<Flood>>({status:'idle'});
  const [power, setPower] = useState<Optional<Power>>({status:'idle'});
  const [climate, setClimate] = useState<Optional<ClimateNormals>>({status:'loading'});
  const [climateRefresh, setClimateRefresh] = useState(0);
  const coords = `latitude=${plan.evidence.location.latitude}&longitude=${plan.evidence.location.longitude}`;
  useEffect(() => {
    const controller = new AbortController();
    setClimate({status:'loading'});
    void request<ClimateNormals>(`/v1/climate-normals?${coords}`,undefined,controller.signal)
      .then(data => {if (!controller.signal.aborted) setClimate({status:'ready',data});})
      .catch(error => {if (!controller.signal.aborted) setClimate({status:'error',error:errorText(error)});});
    return () => controller.abort();
  }, [coords,climateRefresh]);
  useEffect(() => {
    const controller = new AbortController();
    setFlood({status:'loading'});
    request<Flood>(`/v1/evidence/flood?${coords}`, undefined, controller.signal).then(data => setFlood({status:'ready', data})).catch(error => {if (!controller.signal.aborted) setFlood({status:'error', error:errorText(error)});});
    return () => controller.abort();
  }, [coords]);
  const heat = plan.actions.some(a => a.metrics.heat_stress_days?.status === 'available' && (a.metrics.heat_stress_days.value ?? 0) > 0) ? 'Exposure flagged' : plan.actions.some(a => a.metrics.heat_stress_days?.status === 'available') ? 'No exceedance in available days' : 'Not assessed';
  const water = plan.actions.some(a => a.water_balance.crop_et_mm.status === 'available') ? 'Reference estimate only' : 'Stage estimate unavailable';
  return <main id="main" className="plan-layout">
    <div className="plan-heading"><div><p className="eyebrow">The field plan</p><h1>A little foresight.<br/>A clearer next step.</h1><p>{plan.crop[0].toUpperCase() + plan.crop.slice(1)} · {plan.evidence.location.latitude.toFixed(4)}, {plan.evidence.location.longitude.toFixed(4)}{plan.sowing_date && ` · Sown ${plan.sowing_date}`}</p></div><button className="text-button" onClick={editing}>Edit plot <span aria-hidden="true">↗</span></button></div>
    {plan.evidence.is_stale && <div className="notice" role="status">This forecast is stale. Tasks ask you to refresh before acting. <button onClick={retry}>Refresh evidence</button></div>}
    {plan.evidence.data_status !== 'complete' && <p className="notice">Forecast coverage is {plan.evidence.data_status}. {plan.evidence.missing_reasons.join(' ')}</p>}
    <section className="risk-strip" aria-label="Risk assessment"><div><span>Heat</span><strong>{heat}</strong></div><div><span>Water</span><strong>{water}</strong></div><div><span>Flood</span><strong>{flood.status === 'loading' ? 'Checking source…' : flood.status === 'ready' ? 'Discharge only · risk not assessed' : flood.status === 'error' ? 'Source unavailable · risk unknown' : 'Not assessed'}</strong></div></section>
    <section className="forecast-section"><div className="section-title"><h2>The weather ahead</h2><span>UTC forecast days</span></div><WeatherChart weather={plan.evidence} baseline={climate.data}/>
      <div className="climate-status" role="status" aria-live="polite">
        {climate.status === 'loading' && <p className="quiet">Loading the 1991–2020 historical comparison… The live forecast remains available.</p>}
        {climate.status === 'error' && <p className="quiet">Historical comparison unavailable. {climate.error} The live forecast remains available. <button className="text-button" onClick={() => setClimateRefresh(value => value+1)}>Retry historical comparison</button></p>}
        {climate.data && <><p className="quiet">Historical comparison: 1991–2020 ERA5 calendar-day averages. {climate.data.data_status === 'empty' ? 'No complete historical means are available; no comparison lines are drawn.' : climate.data.data_status === 'partial' ? 'Coverage is incomplete; missing historical means leave gaps.' : 'All expected yearly samples are present.'}{climate.data.is_stale && ' Cached historical evidence is stale; a refresh is in progress.'}</p><details><summary>About the historical comparison</summary><p className="quiet">{climate.data.limitation} Historical grid: {climate.data.grid_location.latitude}, {climate.data.grid_location.longitude}. Sample counts are in the daily table.</p><Freshness data={climate.data}/></details></>}
      </div><Freshness data={plan.evidence}/></section>
    <section className="actions-section"><div className="section-title"><h2>Dates to keep in view</h2><button className="text-button" onClick={retry}>Refresh plan</button></div><p className="notice">{plan.agent_note}</p><p className="quiet">{plan.water_balance_availability}</p>
      {plan.forecast_reliability.length > 0 && <details><summary>GFS model rain agreement with ERA5 at this location (a different model from this forecast)</summary><ul className="quiet">{plan.forecast_reliability.map(line => <li key={line}>{line}</li>)}</ul></details>}
      {!plan.actions.length && <p className="empty">No dated tasks could be produced. Refresh the forecast or change the plot.</p>}
      <ol className="action-list">{plan.actions.map(action => <li key={action.date} className="action-row"><time dateTime={action.date}><span>{new Date(`${action.date}T00:00:00Z`).toLocaleDateString('en-IN', {month:'short', timeZone:'UTC'})}</span><strong>{new Date(`${action.date}T00:00:00Z`).getUTCDate()}</strong></time><div><h3>{action.kind === 'inspect_heat_exposure' ? 'Check flowering heat exposure' : action.kind === 'review_water_balance' ? 'Review water before deciding' : plan.sowing_status === 'not_sown' ? 'Review weather before sowing' : 'Review the weather evidence'}</h3><p>{action.reason}</p>{action.explanation_status === 'verified' && <p>{action.explanation}</p>}<details><summary>Why this task?</summary><div className="evidence-detail"><p>{action.water_balance.stage_basis || 'No applicable crop water-stage profile.'}</p><dl>{action.inputs.map(input => <div key={input.field}><dt>{input.field.includes('precipitation') ? 'Forecast rainfall' : input.field.includes('evapotranspiration') ? 'Reference ET0' : input.field.includes('_min') ? 'Minimum temperature' : 'Maximum temperature'}</dt><dd>{input.value === null ? 'Missing' : `${input.value} ${input.unit}`}</dd></div>)}</dl><p>{action.water_balance.warning}</p>{[...action.citations, ...action.water_balance.citations].map((citation,index) => <p key={`${citation.url}-${index}`}><a href={citation.url} target="_blank" rel="noreferrer">{citation.title}</a><small>{citation.locator}{citation.region && ` · ${citation.region}`}</small></p>)}<p className="quiet">Rule version {plan.rule_version}. Rules determine these tasks. Agent text, when available, passes the numeric evidence guardrail.</p></div></details></div></li>)}</ol><Freshness data={plan.evidence}/></section>
    <section className="optional-section"><h2>More evidence, when available</h2><p>These sources are optional. Missing soil or retrospective observations do not block this plan.</p><details><summary>River discharge</summary>{flood.status === 'loading' && <p role="status">Fetching river data…</p>}{flood.error && <p className="error">{flood.error}</p>}{flood.data && <><p>{flood.data.limitation} Coverage: {flood.data.data_status}.</p><p>{flood.data.missing_reasons.join(' ')}</p><Freshness data={flood.data}/></>}</details>
      <details><summary>Soil evidence · optional</summary><button disabled={soil.status === 'loading'} onClick={async () => {setSoil({status:'loading'}); try {setSoil({status:'ready', data:await request<Soil>(`/v1/evidence/soil?${coords}`)});} catch(error){setSoil({status:'error', error:errorText(error)});}}}>{soil.status === 'loading' ? 'Fetching soil…' : 'Request soil evidence'}</button>{soil.error && <p className="error">{soil.error} The plan remains available.</p>}{soil.data && <><p>{soil.data.data_status === 'empty' ? 'SoilGrids returned no property values at this plot.' : 'Modelled soil properties, not a field soil test.'}</p><dl>{soil.data.properties.map(p => <div key={p.name}><dt>{p.name} · {p.depth}</dt><dd>{p.value === null ? 'Missing' : `${p.value} ${p.unit}`}</dd></div>)}</dl><Freshness data={soil.data}/></>}</details>
      <details><summary>NASA observation cross-check · past dates only</summary><p>Retrospective gridded observations are not used to predict the next fortnight.</p><button disabled={power.status === 'loading'} onClick={async () => {
        const end = new Date(); end.setUTCDate(end.getUTCDate()-8); const start = new Date(end); start.setUTCDate(start.getUTCDate()-6);
        setPower({status:'loading'}); try {setPower({status:'ready', data:await request<Power>(`/v1/evidence/power?${coords}&start_date=${start.toISOString().slice(0,10)}&end_date=${end.toISOString().slice(0,10)}`)});} catch(error){setPower({status:'error', error:errorText(error)});}
      }}>{power.status === 'loading' ? 'Fetching past observations…' : 'Request past-week observations'}</button>{power.error && <p className="error">{power.error}</p>}{power.data && <><p>{power.data.daily.time[0]?.slice(0,10)} to {power.data.daily.time.at(-1)?.slice(0,10)} · {power.data.data_status} coverage. {power.data.missing_reasons.join(' ')}</p><p>No forecast-error score is implied: an aligned comparison service is not implemented.</p><Freshness data={power.data}/></>}</details>
    </section>
    <details className="limits"><summary>What this plan cannot establish</summary><p>{plan.limitation}</p><ul>{plan.disabled_parameters.map(p => <li key={p.parameter}><strong>{p.parameter.replaceAll('_',' ')}</strong>: {p.reason}</li>)}</ul></details>
  </main>;
}
