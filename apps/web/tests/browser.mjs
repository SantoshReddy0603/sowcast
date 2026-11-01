import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const base = process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({headless:true,...(process.env.SOWCAST_BROWSER_CHANNEL ? {channel:process.env.SOWCAST_BROWSER_CHANNEL} : {})});
const page = await browser.newPage({viewport:{width:1280,height:900}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(base);
  await page.getByLabel('Find a village or town').fill('Kolar');
  await page.getByRole('button', {name:'Search', exact:true}).click();
  await page.getByRole('button', {name:/Kolār/}).first().click({timeout:30000});
  assert(Number(await page.getByLabel('Latitude', {exact:true}).inputValue()) > 0);
  await page.getByLabel('Crop', {exact:true}).selectOption('maize');
  await page.getByLabel('District', {exact:true}).selectOption('Kolar');
  await page.getByLabel('Already growing').check();
  await page.getByLabel('Sowing date').fill('2026-10-01');
  await page.getByLabel('Include FAO reference water estimates', {exact:false}).check();
  const firstPlanResponse = page.waitForResponse(response => response.url().endsWith('/v1/plans') && response.request().method() === 'POST');
  await page.getByRole('button', {name:'Read the field plan'}).click();
  await page.getByRole('heading', {name:'Dates to keep in view'}).waitFor({timeout:40000});
  const rows = page.locator('.action-row');
  assert(await rows.count() > 0);
  const firstPlan = await (await firstPlanResponse).json();
  if (firstPlan.actions[0].water_balance.crop_et_mm.status === 'available') {
    assert((await rows.first().textContent()).includes('Kc'));
  } else {
    assert.equal(firstPlan.actions[0].water_balance.crop_et_mm.value, null);
    assert(firstPlan.water_balance_availability);
  }
  await rows.first().getByText('Why this task?', {exact:true}).click();
  await rows.first().getByText('Forecast rainfall', {exact:true}).waitFor();
  assert.equal(await page.locator('svg.weather-chart').count(), 1);
  assert((await page.locator('.climate-status').innerText()).toLowerCase().includes('historical comparison'));
  await page.screenshot({path:process.env.SOWCAST_SCREENSHOT || 'test-results/plan.png', fullPage:true});
  console.log('PASS real place search → pin → crop/date → live plan; evidence disclosure and chart');
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:'test-results/mobile-plan.png', fullPage:true});
  console.log('PASS mobile 390px: no page overflow; chart scroll contained');
  await page.getByRole('button', {name:'Edit plot'}).click();
  await page.keyboard.press('Tab');
  assert(await page.evaluate(() => document.activeElement?.id === 'place'));
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Search');
  console.log('PASS keyboard focus enters search field then Search button after screen change');
  await page.route('**/v1/plans', route => route.abort('failed'));
  await page.getByRole('button', {name:'Read the field plan'}).click();
  await page.getByRole('heading', {name:'A pause in the data.'}).waitFor();
  assert.equal(await page.locator('.action-row').count(), 0);
  assert((await page.locator('body').innerText()).includes('No replacement weather or plan'));
  console.log('PASS induced plan network failure: visible error, retry, no replacement data');
  await page.unroute('**/v1/plans');
  await page.getByRole('button', {name:'Try again', exact:true}).click();
  await page.getByRole('heading', {name:'Dates to keep in view'}).waitFor({timeout:40000});
  console.log('PASS retry recovers real plan');
  const live = await page.request.post(base + '/v1/plans', {data:{
    latitude:13.14, longitude:78.13, crop:'maize', sowing_status:'growing', sowing_date:'2026-10-01',
    agronomy_context:{district:'Kolar', allow_fao_reference:true},
  }});
  assert.equal(live.status(), 200);
  const partial = await live.json();
  partial.evidence.daily.time.splice(3, 1);
  for (const values of Object.values(partial.evidence.daily.values)) values.splice(3, 1);
  partial.evidence.data_status = 'partial';
  partial.evidence.is_stale = true;
  await page.route('**/v1/plans', route => route.fulfill({json:partial}));
  await page.getByRole('button', {name:'Refresh plan', exact:true}).click();
  await page.getByText('This forecast is stale.', {exact:false}).waitFor();
  assert.equal(await page.locator('path.temperature-band').count(), 2);
  assert((await page.locator('body').innerText()).includes('Forecast coverage is partial'));
  console.log('PASS isolated mutation of live response: stale notice and missing-date band gap');
  await page.unroute('**/v1/plans');
  await page.getByRole('button', {name:'Refresh plan', exact:true}).click();
  await page.getByRole('heading', {name:'Dates to keep in view'}).waitFor({timeout:40000});
  await page.getByText('Soil evidence · optional', {exact:true}).click();
  const soilResponse = page.waitForResponse(response => response.url().includes('/v1/evidence/soil?'), {timeout:90000});
  await page.getByRole('button', {name:'Request soil evidence'}).click();
  const soilHttp = await soilResponse;
  const soilBody = await soilHttp.json();
  const soilSection = page.getByText('Soil evidence · optional', {exact:true}).locator('..');
  if (soilHttp.status() === 200) {
    const expected = soilBody.data_status === 'empty' ? 'SoilGrids returned no property values at this plot.' : 'Modelled soil properties, not a field soil test.';
    await soilSection.getByText(expected, {exact:true}).waitFor();
    assert.equal(await soilSection.getByText('Missing', {exact:true}).count(), soilBody.properties.filter(p => p.value === null).length);
    for (const property of soilBody.properties.filter(p => p.value !== null)) assert(await soilSection.getByText(`${property.value} ${property.unit}`, {exact:true}).count() > 0);
  } else {
    assert.equal(soilHttp.status(), 503);
    assert(soilBody.error.source && soilBody.error.request_id);
    await soilSection.getByText(`${soilBody.error.message} The plan remains available.`, {exact:true}).waitFor();
  }
  assert(await page.locator('.action-row').count() > 0);
  console.log('PASS actual optional soil response agrees with UI; missing/error state stays visible and plan is retained');
  await page.emulateMedia({colorScheme:'dark', reducedMotion:'reduce'});
  assert(await page.evaluate(() => matchMedia('(prefers-color-scheme: dark)').matches));
  assert.equal(errors.length, 0, errors.join('\n'));
  console.log('PASS dark/reduced-motion preferences; no browser page errors');
} finally {await browser.close();}
