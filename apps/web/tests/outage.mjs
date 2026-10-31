import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const base = process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:390,height:844}});
try {
  await page.goto(base);
  await page.getByLabel('Latitude', {exact:true}).fill('13.14');
  await page.getByLabel('Longitude', {exact:true}).fill('78.13');
  await page.getByLabel('Crop', {exact:true}).selectOption('maize');
  await page.getByLabel('District', {exact:true}).selectOption('Kolar');
  const response = page.waitForResponse(r => r.url().endsWith('/v1/plans'));
  await page.getByRole('button', {name:'Read the field plan'}).click();
  const failure = await response;
  assert.equal(failure.status(), 503);
  const body = await failure.json();
  assert.equal(body.error.source, 'Open-Meteo forecast');
  assert.equal(body.error.retryable, true);
  assert(body.error.request_id);
  await page.getByRole('heading', {name:'A pause in the data.'}).waitFor();
  await page.getByRole('alert').filter({hasText:body.error.message}).waitFor();
  assert.equal(await page.locator('.action-row').count(), 0);
  assert((await page.locator('body').innerText()).includes('Request '));
  await page.screenshot({path:'test-results/source-outage.png',fullPage:true});
  console.log('PASS actual typed source failure: HTTP503, typed source error + request ID visible, no plan values');
} finally {await browser.close();}
