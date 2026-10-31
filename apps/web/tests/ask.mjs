import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const base = process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:390,height:844}});
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(base);
  await page.getByLabel('Latitude', {exact:true}).fill('12.97');
  await page.getByLabel('Longitude', {exact:true}).fill('77.59');
  await page.getByLabel('Crop', {exact:true}).selectOption('maize');
  await page.getByLabel('District', {exact:true}).selectOption('Bengaluru Rural');
  await page.getByRole('button', {name:'Read the field plan'}).click();
  await page.getByRole('heading', {name:'Dates to keep in view'}).waitFor({timeout:40000});
  assert((await page.locator('body').innerText()).includes('Agent explanations unavailable'));
  await page.getByRole('button', {name:'Ask', exact:true}).click();
  await page.getByLabel('Your question').fill('What field evidence should I check?');
  await page.getByLabel('Answer language').selectOption('kn');
  await page.getByRole('button', {name:'Ask Sowcast'}).click();
  await page.getByRole('heading', {name:'Agent unavailable', exact:true}).waitFor({timeout:40000});
  await page.getByText('Agent trace', {exact:true}).click();
  await page.getByRole('cell', {name:'get_forecast', exact:true}).waitFor();
  await page.getByRole('cell', {name:'run_risk_assessment', exact:true}).waitFor();
  assert((await page.locator('body').innerText()).includes('provider_unconfigured'));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:'test-results/ask-unconfigured.png', fullPage:true});
  assert.deepEqual(errors, []);
  console.log('PASS actual weather → deterministic plan → typed Ask → unconfigured provider → persisted tool trace; mobile no overflow; no page errors');
} finally {await browser.close();}
