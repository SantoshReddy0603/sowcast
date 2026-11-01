import {useEffect, useRef, useState, type FormEvent} from 'react';
import {request, errorText} from '../api';
import {PlotMap} from '../components/PlotMap';
import type {Places, RequestBody} from '../types';

const crops = ['ragi', 'paddy', 'maize', 'tur', 'groundnut', 'tomato'];
const districts = ['Bengaluru Rural', 'Kolar', 'Tumakuru', 'Chikkaballapura', 'Ramanagara'];
type DistrictLookup = {status: 'matched'|'ambiguous'|'unavailable'; district: string | null; supported_district: string | null; attribution: string; source_url: string; licence_url: string; boundary_year: number; limitation: string};

export function Plot({onSubmit, initial}: {onSubmit: (body: RequestBody) => void; initial: RequestBody | null}) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<Places | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [latitude, setLatitude] = useState(initial?.latitude.toString() ?? '');
  const [longitude, setLongitude] = useState(initial?.longitude.toString() ?? '');
  const [crop, setCrop] = useState(initial?.crop ?? '');
  const [district, setDistrict] = useState(initial?.agronomy_context.district ?? '');
  const [districtLookup, setDistrictLookup] = useState<DistrictLookup | null>(null);
  const [districtBusy, setDistrictBusy] = useState(false);
  const [districtError, setDistrictError] = useState('');
  const [status, setStatus] = useState<'growing' | 'not_sown'>(initial?.sowing_status ?? 'not_sown');
  const [sowingDate, setSowingDate] = useState(initial?.sowing_date ?? '');
  const [flowering, setFlowering] = useState(initial?.growth_stage === 'flowering');
  const [reference, setReference] = useState(initial?.agronomy_context.allow_fao_reference ?? false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const point = latitude !== '' && longitude !== '' && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude)) && Math.abs(Number(latitude)) <= 90 && Math.abs(Number(longitude)) <= 180 ? {latitude:Number(latitude), longitude:Number(longitude)} : null;
  useEffect(() => {
    setDistrict(''); setDistrictLookup(null); setDistrictError('');
    const lat = Number(latitude), lon = Number(longitude);
    if (!latitude || !longitude || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {setDistrictBusy(false); return;}
    const abort = new AbortController();
    setDistrictBusy(true);
    const timer = window.setTimeout(() => {
      void request<DistrictLookup>(`/v1/places/district?latitude=${lat}&longitude=${lon}`, undefined, abort.signal)
        .then(result => {
          if (abort.signal.aborted) return;
          setDistrictLookup(result);
          setDistrict(result.supported_district ?? (result.status === 'matched' ? 'outside' : ''));
          if (!result.supported_district) setReference(false);
        })
        .catch(cause => {if (!abort.signal.aborted) setDistrictError(errorText(cause));})
        .finally(() => {if (!abort.signal.aborted) setDistrictBusy(false);});
    }, 350);
    return () => {window.clearTimeout(timer); abort.abort();};
  }, [latitude, longitude]);
  function choose(lat: number, lon: number) {setLatitude(lat.toFixed(6)); setLongitude(lon.toFixed(6));}
  async function searchPlaces(event: FormEvent) {
    event.preventDefault();
    controller.current?.abort();
    const abort = new AbortController(); controller.current = abort;
    setBusy(true); setError(''); setResults(null);
    try {setResults(await request<Places>(`/v1/places?name=${encodeURIComponent(search.trim())}`, undefined, abort.signal));}
    catch (cause) {if (!abort.signal.aborted) setError(errorText(cause));}
    finally {if (!abort.signal.aborted) setBusy(false);}
  }
  return <main id="main" className="plot-layout">
    <div className="intro"><p className="eyebrow">Your field notebook</p><h1>Begin with<br/>a piece of land.</h1><p>A location, a crop, and the evidence for your next decision.</p><p className="scope">For Bengaluru Rural, Kolar, Tumakuru, Chikkaballapura and Ramanagara.</p></div>
    <section className="plot-work" aria-label="Choose your plot">
      <form onSubmit={searchPlaces} className="search-form">
        <label htmlFor="place">Find a village or town</label>
        <div className="search-row"><input id="place" value={search} onChange={e => setSearch(e.target.value)} minLength={2} maxLength={120} required autoComplete="off"/><button disabled={busy} type="submit">{busy ? 'Searching…' : 'Search'}</button></div>
      </form>
      {busy && <div className="search-loading skeleton" role="status">Searching live place data…</div>}
      {error && <p className="error" role="alert">{error} Try the search again or enter coordinates.</p>}
      {results && <div className="places" aria-live="polite">{results.places.length ? <ul>{results.places.map(place => <li key={place.id}><button type="button" onClick={() => {choose(place.latitude, place.longitude); setResults(null);}}><strong>{place.name}</strong><span>{[place.admin2, place.admin1].filter(Boolean).join(', ')}</span></button></li>)}</ul> : <p>No places matched. Try a nearby town or enter coordinates.</p>}<footer><a href={results.attribution_url}>{results.attribution_text}</a> · Fetched {new Date(results.fetched_at).toLocaleString('en-IN')}{results.is_stale && ' · Stale'}</footer></div>}
      <PlotMap point={point} onSelect={choose}/>
      <p className="map-caption">Tap to pin your plot. Keyboard users can pan with arrows and pin the centre, or enter coordinates.</p>
      <form className="plot-form" onSubmit={event => {
        event.preventDefault();
        if (!point || districtBusy || !district) return;
        onSubmit({api_version:'1.0', ...point, crop, sowing_status:status, sowing_date:status === 'growing' ? sowingDate : null, growth_stage:status === 'growing' && flowering ? 'flowering' : null, agronomy_context:{district:district === 'outside' ? null : district, allow_fao_reference:reference && district !== 'outside'}});
      }}>
        <div className="field-pair"><label>Latitude<input type="number" step="any" min="-90" max="90" required value={latitude} onChange={e => setLatitude(e.target.value)}/></label><label>Longitude<input type="number" step="any" min="-180" max="180" required value={longitude} onChange={e => setLongitude(e.target.value)}/></label></div>
        <div className="field-pair"><div><label htmlFor="crop">Crop</label><select id="crop" required value={crop} onChange={e => setCrop(e.target.value)}><option value="">Choose a crop</option>{crops.map(c => <option key={c} value={c}>{c === 'tur' ? 'Tur · pigeon pea' : c === 'ragi' ? 'Ragi · finger millet' : c[0].toUpperCase() + c.slice(1)}</option>)}</select></div><div><label htmlFor="district">District</label><select id="district" aria-describedby="district-status" required disabled={districtBusy} value={district} onChange={e => {setDistrict(e.target.value); if (e.target.value === 'outside') setReference(false);}}><option value="">{districtBusy ? 'Identifying district…' : 'Confirm district'}</option>{districts.map(d => <option key={d}>{d}</option>)}<option value="outside">{districtLookup?.status === 'matched' && !districtLookup.supported_district ? `${districtLookup.district} · outside pilot area` : 'Outside pilot area'}</option></select></div></div>
        <div id="district-status" className="quiet" role="status" aria-live="polite">
          {districtBusy ? <p>Identifying the district for this pin…</p> : districtError ? <p>District lookup unavailable. Confirm the district manually. {districtError}</p> : districtLookup?.status === 'matched' ? <p>Detected {districtLookup.district}. You can correct the selection if needed.</p> : point ? <p>{districtLookup?.status === 'ambiguous' ? 'This pin is near a district boundary.' : 'No district could be identified for this pin.'} Confirm the district manually.</p> : <p>Pin your plot to identify its district automatically.</p>}
          {district === 'outside' && <p>This location is outside the five pilot districts. Weather evidence remains available; district-specific crop guidance and reference water estimates are unavailable.</p>}
          {districtLookup && <p>{districtLookup.limitation} <a href={districtLookup.source_url} target="_blank" rel="noreferrer">{districtLookup.attribution}</a> · <a href={districtLookup.licence_url} target="_blank" rel="noreferrer">Licence</a></p>}
        </div>
        <fieldset><legend>Sowing status</legend><label className="choice"><input type="radio" name="status" checked={status === 'not_sown'} onChange={() => setStatus('not_sown')}/>Not yet sown</label><label className="choice"><input type="radio" name="status" checked={status === 'growing'} onChange={() => setStatus('growing')}/>Already growing</label></fieldset>
        {status === 'growing' && <><label>Sowing date<input type="date" required max={new Date().toLocaleDateString('en-CA')} value={sowingDate} onChange={e => setSowingDate(e.target.value)}/></label>{crop === 'paddy' && <label className="choice"><input type="checkbox" checked={flowering} onChange={e => setFlowering(e.target.checked)}/>The crop is currently flowering</label>}</>}
        <label className="choice reference-choice"><input type="checkbox" checked={reference} disabled={districtBusy || !district || district === 'outside'} onChange={e => setReference(e.target.checked)}/><span>Include FAO reference water estimates where supported.<small>These are not locally calibrated. Without a verified stage, the water estimate stays unavailable.</small></span></label>
        <button className="primary" type="submit" disabled={districtBusy || !district}>Read the field plan <span aria-hidden="true">→</span></button>
      </form>
    </section>
  </main>;
}
