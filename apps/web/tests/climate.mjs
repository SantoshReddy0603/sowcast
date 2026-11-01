import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const base = process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({headless:true,...(process.env.SOWCAST_BROWSER_CHANNEL ? {channel:process.env.SOWCAST_BROWSER_CHANNEL} : {})});
const page = await browser.newPage({viewport:{width:1280,height:1000}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  const planResponse = await page.request.post(base+'/v1/plans',{timeout:120000,data:{latitude:13.14,longitude:78.13,crop:'maize',sowing_status:'not_sown',agronomy_context:{district:'Kolar',allow_fao_reference:false}}});
  assert.equal(planResponse.status(),200);
  const livePlan = await planResponse.json();
  const climateResponse = await page.request.get(base+'/v1/climate-normals?latitude=13.14&longitude=78.13',{timeout:60000});
  assert.equal(climateResponse.status(),200);
  const liveClimate = await climateResponse.json();
  assert.equal(liveClimate.data_status,'complete');
  let currentPlan = livePlan;
  await page.route('**/v1/plans',route => route.fulfill({json:currentPlan}));
  async function mount() {
    await page.goto(base);
    await page.getByLabel('Latitude',{exact:true}).fill('13.14');
    await page.getByLabel('Longitude',{exact:true}).fill('78.13');
    await page.waitForFunction(() => document.querySelector('#district').value === 'Kolar' && !document.querySelector('#district').disabled);
    await page.getByLabel('Crop',{exact:true}).selectOption('maize');
    await page.getByRole('button',{name:'Read the field plan'}).click();
    await page.getByRole('heading',{name:'Dates to keep in view'}).waitFor();
  }
  await mount();
  await page.locator('.climate-status').getByText('Historical comparison: 1991–2020 ERA5 calendar-day averages.',{exact:false}).waitFor({timeout:60000});
  assert.equal(await page.locator('path.climate-line').count(),3);
  assert.equal(await page.locator('.weather-chart title').count(),0);
  assert(await page.locator('.weather-chart').evaluate(svg => [...svg.querySelectorAll('text')].every(text => {
    const box = text.getBBox();
    return box.x >= 0 && box.x+box.width <= 800 && box.y >= 0 && box.y+box.height <= 366;
  })));
  await page.getByText('Daily forecast and historical averages',{exact:true}).click();
  assert.equal(await page.locator('.weather-values tbody tr').count(),livePlan.evidence.daily.time.length);
  assert((await page.locator('.weather-values tbody tr').first().innerText()).includes('expected 30 each'));
  if (process.env.SOWCAST_SCREENSHOT_DIR) await page.locator('.forecast-section').screenshot({path:process.env.SOWCAST_SCREENSHOT_DIR+'/weather-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.locator('.chart-scroll').focus();
  await page.keyboard.press('End');
  await page.locator('.chart-scroll').evaluate(element => {element.scrollLeft=element.scrollWidth;});
  assert(await page.locator('.chart-scroll').evaluate(element => element.scrollLeft > 0));
  await page.emulateMedia({colorScheme:'dark'});
  if (process.env.SOWCAST_SCREENSHOT_DIR) await page.locator('.forecast-section').screenshot({path:process.env.SOWCAST_SCREENSHOT_DIR+'/weather-mobile-dark.png'});
  console.log('PASS real baseline overlays, exact sample-count table, unclipped labels, keyboard/mobile scrolling and dark mode');

  let mode = 'error';
  await page.route('**/v1/climate-normals?**',async route => {
    if (mode === 'error') return route.abort();
    if (mode === 'live') return route.continue();
    const data = structuredClone(liveClimate);
    if (mode === 'stale') data.is_stale = true;
    if (mode === 'empty') {
      data.data_status = 'empty';
      for (const day of data.days) for (const field of Object.keys(day.values)) {day.values[field]=null;day.samples[field]=0;}
    }
    await route.fulfill({json:data});
  });
  await mount();
  await page.getByRole('button',{name:'Retry historical comparison'}).waitFor();
  assert.equal(await page.locator('path.climate-line').count(),0);
  assert.equal(await page.locator('rect.rain-bar').count(),livePlan.evidence.daily.time.length);
  mode='live';
  await page.getByRole('button',{name:'Retry historical comparison'}).click();
  await page.locator('.climate-status').getByText('All expected yearly samples are present.',{exact:false}).waitFor();
  mode='empty';
  await mount();
  await page.getByText('No complete historical means are available; no comparison lines are drawn.',{exact:false}).waitFor();
  assert.equal(await page.locator('path.climate-line').count(),0);
  assert.equal(await page.locator('rect.rain-bar').count(),livePlan.evidence.daily.time.length);
  mode='stale';
  await mount();
  await page.getByText('Cached historical evidence is stale;', {exact:false}).waitFor();
  currentPlan=structuredClone(livePlan);
  currentPlan.evidence.daily.values.temperature_2m_min.fill(null);
  currentPlan.evidence.daily.values.temperature_2m_max.fill(null);
  await mount();
  await page.getByText('Forecast temperatures are missing;', {exact:false}).waitFor();
  assert.equal(await page.locator('rect.rain-bar').count(),livePlan.evidence.daily.time.length);
  assert.deepEqual(errors,[]);
  console.log('PASS unavailable/retry, empty and stale historical states; rainfall survives missing forecast temperatures');
} finally {await browser.close();}
