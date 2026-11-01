import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const browser = await chromium.launch({headless:true, ...(process.env.SOWCAST_BROWSER_CHANNEL ? {channel:process.env.SOWCAST_BROWSER_CHANNEL} : {})});
const page = await browser.newPage({viewport:{width:390,height:844}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
async function pin(latitude, longitude, district) {
  await page.getByLabel('Latitude', {exact:true}).fill(String(latitude));
  await page.getByLabel('Longitude', {exact:true}).fill(String(longitude));
  await page.waitForFunction(expected => {
    const select = document.querySelector('#district');
    return !select.disabled && select.value === expected;
  }, district);
}
try {
  await page.goto(process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173');
  for (const [latitude, longitude, district] of [
    [13.14, 78.13, 'Kolar'], [13.29, 77.54, 'Bengaluru Rural'],
    [13.34, 77.1, 'Tumakuru'], [13.43, 77.73, 'Chikkaballapura'],
    [12.72, 77.28, 'Ramanagara'],
  ]) await pin(latitude, longitude, district);
  console.log('PASS all five pilot districts follow coordinate changes');
  await pin(13.14, 78.13, 'Kolar');
  await page.getByRole('button', {name:'Pin map centre', exact:true}).click();
  await page.waitForFunction(() => document.querySelector('#district').value === 'Kolar' && !document.querySelector('#district').disabled);
  console.log('PASS keyboard map pin identifies the district');
  const previousLatitude = await page.getByLabel('Latitude', {exact:true}).inputValue();
  await page.locator('.map').click({position:{x:60,y:100}});
  await page.waitForFunction(() => document.querySelector('#district').value === 'Kolar' && !document.querySelector('#district').disabled);
  assert.notEqual(await page.getByLabel('Latitude', {exact:true}).inputValue(), previousLatitude);
  console.log('PASS clicking the map updates coordinates and identifies the district');
  let releaseLookup, lookupStarted, lookupFinished;
  const held = new Promise(resolve => {releaseLookup = resolve;});
  const started = new Promise(resolve => {lookupStarted = resolve;});
  const finished = new Promise(resolve => {lookupFinished = resolve;});
  const delayedPattern = '**/v1/places/district?latitude=13.141&**';
  await page.route(delayedPattern, async route => {
    const response = await page.request.get(route.request().url());
    lookupStarted();
    await held;
    await route.fulfill({response}).catch(() => {});
    lookupFinished();
  });
  await page.getByLabel('Latitude', {exact:true}).fill('13.141');
  await started;
  await pin(12.3, 76.65, 'outside');
  releaseLookup();
  await finished;
  assert.equal(await page.getByLabel('District', {exact:true}).inputValue(), 'outside');
  await page.unroute(delayedPattern);
  console.log('PASS a delayed previous-pin response cannot overwrite the new district');
  await pin(13.14, 78.13, 'Kolar');
  await page.getByLabel('Include FAO reference water estimates', {exact:false}).check();
  await pin(12.3, 76.65, 'outside');
  assert((await page.locator('#district option:checked').textContent()).includes('Mysore'));
  assert(await page.getByLabel('Include FAO reference water estimates', {exact:false}).isDisabled());
  assert(!(await page.getByLabel('Include FAO reference water estimates', {exact:false}).isChecked()));
  assert((await page.locator('#district-status').innerText()).includes('outside the five pilot districts'));
  if (process.env.SOWCAST_SCREENSHOT) await page.screenshot({path:process.env.SOWCAST_SCREENSHOT,fullPage:true});
  await page.getByLabel('Crop', {exact:true}).selectOption('maize');
  const submitted = page.waitForRequest(request => request.url().endsWith('/v1/plans'));
  await page.route('**/v1/plans', route => route.abort());
  await page.getByRole('button', {name:'Read the field plan'}).click();
  const body = (await submitted).postDataJSON();
  assert.equal(body.agronomy_context.district, null);
  assert.equal(body.agronomy_context.allow_fao_reference, false);
  console.log('PASS outside district is named and cannot inherit pilot water guidance');
  await page.unroute('**/v1/plans');
  await page.reload();
  await page.route('**/v1/places/district?**', route => route.abort());
  await page.getByLabel('Latitude', {exact:true}).fill('13.14');
  await page.getByLabel('Longitude', {exact:true}).fill('78.13');
  await page.getByText('District lookup unavailable.', {exact:false}).waitFor();
  await page.getByLabel('District', {exact:true}).selectOption('Kolar');
  assert(await page.getByRole('button', {name:'Read the field plan'}).isEnabled());
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  console.log('PASS lookup outage allows manual correction; mobile width and page errors checked');
} finally {await browser.close();}
