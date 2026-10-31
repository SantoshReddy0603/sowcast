import {useEffect, useRef, useState} from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export function PlotMap({point, onSelect}: {
  point: {latitude: number; longitude: number} | null;
  onSelect: (latitude: number, longitude: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.CircleMarker | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  const [tileError, setTileError] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    const instance = L.map(container.current, {scrollWheelZoom: false}).setView([20, 78], 4);
    map.current = instance;
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(instance);
    tiles.on('tileerror', () => setTileError(true));
    instance.on('click', (event: L.LeafletMouseEvent) => select.current(event.latlng.lat, event.latlng.lng));
    container.current.setAttribute('aria-label', 'Plot map. Use arrow keys to pan; use Pin map centre to select.');
    return () => {instance.remove(); map.current = null;};
  }, []);
  useEffect(() => {
    if (!point || !map.current) return;
    const position: L.LatLngExpression = [point.latitude, point.longitude];
    if (marker.current) marker.current.setLatLng(position);
    else marker.current = L.circleMarker(position, {radius: 8, color: '#fff', weight: 3, fillColor: '#91462f', fillOpacity: 1}).addTo(map.current);
    map.current.setView(position, Math.max(map.current.getZoom(), 12), {animate: false});
  }, [point]);
  return <div className="map-wrap">
    <div className="map" ref={container}/>
    <button type="button" className="map-select" onClick={() => {
      const centre = map.current?.getCenter();
      if (centre) onSelect(centre.lat, centre.lng);
    }}>Pin map centre</button>
    {tileError && <p className="map-warning" role="status">Map tiles unavailable. Search or enter coordinates below.</p>}
  </div>;
}
