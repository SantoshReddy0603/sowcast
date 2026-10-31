import {scaleLinear} from 'd3-scale';
import {area} from 'd3-shape';
import type {Weather} from '../types';

export function WeatherChart({weather}: {weather: Weather}) {
  const days = weather.daily.time.map((date, index) => ({
    date, timestamp: new Date(date).getTime(),
    low: weather.daily.values.temperature_2m_min?.[index] ?? null,
    high: weather.daily.values.temperature_2m_max?.[index] ?? null,
    rain: weather.daily.values.precipitation_sum?.[index] ?? null,
  }));
  const temperatures = days.flatMap(d => [d.low, d.high]).filter((v): v is number => v !== null);
  if (!temperatures.length) return <p className="empty">Temperature coverage is missing. No band is drawn.</p>;
  const times = days.map(d => d.timestamp);
  const first = Math.min(...times);
  const last = Math.max(...times);
  const x = scaleLinear().domain([first, last === first ? first + 86400000 : last]).range([52, 746]);
  const y = scaleLinear().domain([Math.min(...temperatures) - 2, Math.max(...temperatures) + 2]).range([160, 28]);
  const rainMax = Math.max(1, ...days.map(d => d.rain ?? 0));
  const rainY = scaleLinear().domain([0, rainMax]).range([252, 194]);
  const band = area<typeof days[number]>().defined(d => d.low !== null && d.high !== null)
    .x(d => x(d.timestamp)).y0(d => y(d.low!)).y1(d => y(d.high!));
  const segments: (typeof days)[] = [];
  for (const day of days) {
    const current = segments.at(-1);
    const previous = current?.at(-1);
    if (!current || !previous || day.timestamp - previous.timestamp !== 86400000) segments.push([day]);
    else current.push(day);
  }
  return <div className="chart-scroll">
    <svg className="weather-chart" viewBox="0 0 800 300" role="img" aria-labelledby="forecast-title forecast-description">
      <title id="forecast-title">Forecast daily temperature range and rainfall</title>
      <desc id="forecast-description">Temperature band in degrees Celsius above rainfall bars in millimetres. All dates use UTC. Missing data leaves gaps. Exact values are in the dated plan below.</desc>
      {y.ticks(3).map(t => <g key={t}><line x1="48" x2="752" y1={y(t)} y2={y(t)} className="grid-line"/><text x="8" y={y(t) + 4}>{t}°C</text></g>)}
      {segments.map(segment => <path key={segment[0].date} d={band(segment) ?? ''} className="temperature-band"/>)}
      <text x="52" y="18" className="chart-label">Daily low–high · °C</text>
      <text x="52" y="186" className="chart-label">Rainfall · mm</text>
      {days.map((d,index) => <g key={d.date}>
        {d.rain !== null && <rect x={x(d.timestamp) - 8} y={rainY(d.rain)} width="16" height={252 - rainY(d.rain)} className="rain-bar"><title>{d.date.slice(0, 10)}: {d.rain} mm</title></rect>}
        {d.rain !== null && <text x={x(d.timestamp)} y={rainY(d.rain) - 5} textAnchor="middle">{d.rain.toFixed(1)}</text>}
        {(index % 3 === 0 || index === days.length - 1) && <text x={x(d.timestamp)} y="280" textAnchor="middle">{new Date(d.date).toLocaleDateString('en-IN', {day:'numeric', month:'short', timeZone:'UTC'})}</text>}
      </g>)}
    </svg>
  </div>;
}
