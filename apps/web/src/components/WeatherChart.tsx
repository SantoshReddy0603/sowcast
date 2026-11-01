import {scaleLinear} from 'd3-scale';
import {area, line} from 'd3-shape';
import type {ClimateNormals, Weather} from '../types';

const number = (value:number|null|undefined, unit:string) => value === null || value === undefined ? 'Missing' : `${value.toFixed(1)} ${unit}`;
const dateLabel = (value:string) => new Date(value).toLocaleDateString('en-IN', {day:'numeric',month:'short',timeZone:'UTC'});

export function WeatherChart({weather, baseline}: {weather:Weather; baseline?:ClimateNormals}) {
  const hasComparison = baseline && baseline.data_status !== 'empty';
  const historical = new Map(baseline?.days.map(day => [day.month_day,day]));
  const days = weather.daily.time.map((date,index) => {
    const normal = historical.get(date.slice(5,10));
    return {date, timestamp:new Date(date).getTime(), normal,
      low:weather.daily.values.temperature_2m_min?.[index] ?? null,
      high:weather.daily.values.temperature_2m_max?.[index] ?? null,
      rain:weather.daily.values.precipitation_sum?.[index] ?? null,
      averageLow:normal?.values.temperature_2m_min ?? null,
      averageHigh:normal?.values.temperature_2m_max ?? null,
      averageRain:normal?.values.precipitation_sum ?? null};
  });
  if (!days.length) return <p className="empty">No dated forecast values are available.</p>;
  const times = days.map(day => day.timestamp);
  const first = Math.min(...times), last = Math.max(...times);
  const temperatures = days.flatMap(day => [day.low,day.high,day.averageLow,day.averageHigh]).filter((value):value is number => value !== null);
  const x = scaleLinear().domain([first,last === first ? first + 86400000 : last]).range([64,740]);
  const y = scaleLinear().domain(temperatures.length ? [Math.min(...temperatures)-2,Math.max(...temperatures)+2] : [0,1]).range([176,40]);
  const rainMax = Math.max(1,...days.flatMap(day => [day.rain,day.averageRain]).filter((value):value is number => value !== null));
  const rainY = scaleLinear().domain([0,rainMax]).range([314,242]);
  const band = area<typeof days[number]>().defined(day => day.low !== null && day.high !== null).x(day => x(day.timestamp)).y0(day => y(day.low!)).y1(day => y(day.high!));
  const averageLine = (field:'averageLow'|'averageHigh'|'averageRain') => line<typeof days[number]>().defined(day => day[field] !== null).x(day => x(day.timestamp)).y(day => field === 'averageRain' ? rainY(day[field]!) : y(day[field]!));
  const segments:(typeof days)[] = [];
  for (const day of days) {
    const current = segments.at(-1), previous = current?.at(-1);
    if (!current || !previous || day.timestamp - previous.timestamp !== 86400000) segments.push([day]);
    else current.push(day);
  }
  return <>
    <div className="chart-legend" aria-label="Chart legend"><span><i className="legend-forecast" aria-hidden="true"/>Forecast temperature low–high</span><span><i className="legend-rain" aria-hidden="true"/>Forecast rainfall</span>{hasComparison && <span><i className="legend-history" aria-hidden="true"/>1991–2020 average low, high and rainfall</span>}</div>
    {!days.some(day => day.low !== null || day.high !== null) && <p className="quiet">Forecast temperatures are missing; available rainfall and historical values remain shown.</p>}
    <p className="chart-help quiet">UTC days · Rainfall in millimetres · Scroll sideways on smaller screens. Exact values are available below.</p>
    <div className="chart-scroll" tabIndex={0} role="region" aria-label="Daily weather chart; scroll horizontally on smaller screens">
      <svg className="weather-chart" viewBox="0 0 800 366" role="img" aria-label="Forecast daily temperature range and rainfall, with available historical averages" aria-describedby="forecast-description">
        <desc id="forecast-description">Temperature forecast band above rainfall bars. Dashed lines, when available, show ERA5 calendar-day averages for 1991 to 2020, not prediction intervals. Missing data leaves gaps. Exact values and historical sample counts are in the table below.</desc>
        <text x="64" y="18" className="chart-label">Daily low–high · °C</text>
        {temperatures.length ? y.ticks(3).map(t => <g key={t}><line x1="60" x2="752" y1={y(t)} y2={y(t)} className="grid-line"/><text x="8" y={y(t)+4}>{t}°C</text></g>) : <text x="64" y="100">Temperature values missing</text>}
        {segments.map(segment => <g key={segment[0].date}><path d={band(segment) ?? ''} className="temperature-band"/>{hasComparison && <><path d={averageLine('averageLow')(segment) ?? ''} className="climate-line"/><path d={averageLine('averageHigh')(segment) ?? ''} className="climate-line"/></>}</g>)}
        <text x="64" y="218" className="chart-label">Rainfall · mm</text>
        {rainY.ticks(2).map(t => <g key={t}><line x1="60" x2="752" y1={rainY(t)} y2={rainY(t)} className="grid-line"/><text x="8" y={rainY(t)+4}>{t.toFixed(1)}</text></g>)}
        {days.map(day => <g key={day.date}>{day.rain !== null && <><rect x={x(day.timestamp)-8} y={rainY(day.rain)} width="16" height={314-rainY(day.rain)} className="rain-bar"/><text x={x(day.timestamp)} y={Math.min(rainY(day.rain),day.averageRain === null ? 314 : rainY(day.averageRain))-9} textAnchor="middle">{day.rain.toFixed(1)}</text></>}</g>)}
        {hasComparison && segments.map(segment => <path key={segment[0].date} d={averageLine('averageRain')(segment) ?? ''} className="climate-line climate-rain-line"/>)}
        {days.map((day,index) => (index % 3 === 0 || index === days.length-1) && <text key={day.date} x={x(day.timestamp)} y="346" textAnchor="middle">{dateLabel(day.date)}</text>)}
      </svg>
    </div>
    <details className="weather-values"><summary>Daily forecast and historical averages</summary><div className="weather-values-scroll" tabIndex={0} role="region" aria-label="Exact weather values and historical sample counts"><table><caption>UTC dates; ERA5 averages: 1991-2020.</caption><thead><tr><th scope="col">Date</th><th scope="col">Forecast low / high</th><th scope="col">Average low / high</th><th scope="col">Forecast rain</th><th scope="col">Average rain</th><th scope="col">Historical samples: low / high / rain</th></tr></thead><tbody>{days.map(day => <tr key={day.date}><th scope="row">{dateLabel(day.date)}</th><td>{number(day.low,'°C')} / {number(day.high,'°C')}</td><td>{number(day.averageLow,'°C')} / {number(day.averageHigh,'°C')}</td><td>{number(day.rain,'mm')}</td><td>{number(day.averageRain,'mm')}</td><td>{day.normal ? `${day.normal.samples.temperature_2m_min} / ${day.normal.samples.temperature_2m_max} / ${day.normal.samples.precipitation_sum}; expected ${day.normal.expected_samples} each` : 'Unavailable'}</td></tr>)}</tbody></table></div></details>
  </>;
}
