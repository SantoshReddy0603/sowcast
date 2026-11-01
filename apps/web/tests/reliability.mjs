import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const base = process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({headless:true,...(process.env.SOWCAST_BROWSER_CHANNEL ? {channel:process.env.SOWCAST_BROWSER_CHANNEL} : {})});
const page = await browser.newPage({viewport:{width:1280,height:900}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(base);
  await page.getByLabel('Latitude', {exact:true}).fill('13.14');
  await page.getByLabel('Longitude', {exact:true}).fill('78.13');
  await page.getByLabel('Crop', {exact:true}).selectOption('maize');
  await page.waitForFunction(() => document.querySelector('#district')?.value === 'Kolar');
  await page.getByRole('button', {name:'Read the field plan'}).click();
  await page.getByRole('heading', {name:'Dates to keep in view'}).waitFor({timeout:40000});
  const responsePromise = page.waitForResponse(response => response.url().includes('/v1/backtests?'));
  await page.getByRole('button', {name:'Reliability', exact:true}).click();
  const response = await responsePromise;
  assert.equal(response.status(), 200);
  const live = await response.json();
  await page.getByRole('heading', {name:'GFS model: rain or no rain agreement'}).waitFor({timeout:40000});
  assert.equal(await page.locator('svg.reliability-chart').count(), 1);
  assert.equal(await page.locator('svg.weather-chart').count(), 0);
  for (const definition of ['gt0','ge1']) {
    await page.getByLabel('Rain definition', {exact:true}).selectOption(definition);
    const rows = page.getByRole('region', {name:'GFS model rain samples, ERA5 base rate and majority baseline'}).locator('tbody tr');
    assert.equal(await rows.count(), 7);
    for (const [index,score] of live.scores.entries()) {
      const rain = score.rain_definitions.find(rule => rule.definition === definition);
      assert((await page.locator('body').innerText()).includes(`${rain.correct_days} of ${rain.paired_days} days correct`));
      const text = await rows.nth(index).innerText();
      assert(text.includes(`GFS model ${score.lead_hours}h`));
      assert(text.includes(`${rain.era5_rain_days} / ${rain.paired_days}`));
      assert(text.includes(`${rain.majority_correct_days} / ${rain.paired_days}`));
      assert(text.includes(`n=${rain.paired_days} days`));
    }
  }
  assert((await page.locator('body').innerText()).includes('IST is UTC +05:30'));
  assert((await page.locator('body').innerText()).toLowerCase().includes('no lead ranking is established'));
  await page.screenshot({path:'test-results/reliability.png', fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:'test-results/reliability-mobile.png', fullPage:true});
  console.log('PASS live GFS model backtest: both definitions, per-lead ERA5 base rates, majority baselines, sample counts/intervals, UTC/IST, mobile no overflow');
  await page.route('**/v1/backtests?*', route => route.abort('failed'));
  await page.getByRole('button', {name:'Refresh comparison'}).click();
  await page.getByRole('heading', {name:'Comparison unavailable'}).waitFor();
  assert.equal(await page.locator('svg.reliability-chart').count(), 0);
  assert((await page.locator('body').innerText()).includes('No scores have been supplied'));
  await page.unroute('**/v1/backtests?*');
  await page.getByRole('button', {name:'Try comparison again'}).click();
  await page.getByRole('heading', {name:'GFS model: rain or no rain agreement'}).waitFor({timeout:40000});
  console.log('PASS error removes scores; retry restores real backtest');
  const empty = structuredClone(live);
  empty.data_status = 'empty'; empty.is_stale = true;
  empty.uncertainty_note = 'Each GFS model lead has 0–0 paired rain days out of 60. Sparse or absent paired days limit what these comparisons can establish. No lead ranking is established.';
  for (const score of empty.scores) {
    Object.assign(score, {temperature_mae_c:null, temperature_pairs:0, temperature_missing_hours:1440,
      rain_accuracy:null, rain_pairs:0, rain_correct_days:0, rain_missing_days:60});
    for(const rule of score.rain_definitions) Object.assign(rule, {paired_days:0, missing_days:60, correct_days:0, accuracy:null, accuracy_ci95:null, era5_rain_days:0, era5_rain_share:null, majority_class:null, majority_correct_days:0, majority_accuracy:null});
  }
  await page.route('**/v1/backtests?*', route => route.fulfill({json:empty}));
  await page.getByRole('button', {name:'Refresh comparison'}).click();
  await page.getByText('No paired samples are available.', {exact:false}).waitFor();
  assert.equal(await page.locator('svg.reliability-chart').count(), 0);
  assert((await page.locator('body').innerText()).includes('This comparison is stale'));
  assert((await page.locator('body').innerText()).includes('Unavailable'));
  await page.emulateMedia({colorScheme:'dark', reducedMotion:'reduce'});
  assert.deepEqual(errors, []);
  console.log('PASS isolated mutation of real response: empty/stale notices, no fabricated zero scores, dark/reduced motion, no page errors');
} finally {await browser.close();}
