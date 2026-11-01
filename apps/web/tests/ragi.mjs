import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';

const base = process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({headless:true,...(process.env.SOWCAST_BROWSER_CHANNEL ? {channel:process.env.SOWCAST_BROWSER_CHANNEL} : {})});
const page = await browser.newPage({viewport:{width:1280,height:900}});
try {
  let plan;
  if (process.env.SOWCAST_PLAN_RESPONSE_PATH) plan=JSON.parse(await readFile(process.env.SOWCAST_PLAN_RESPONSE_PATH,'utf8'));
  else {
    const response=await page.request.post(base+'/v1/plans',{timeout:120000,data:{latitude:13.14,longitude:78.13,crop:'ragi',sowing_status:'not_sown',agronomy_context:{district:'Kolar',allow_fao_reference:false}}});
    assert.equal(response.status(),200);
    plan=await response.json();
  }
  assert.equal(plan.crop,'ragi');
  assert.equal(plan.sowing_status,'not_sown');
  await page.route('**/v1/plans',route => route.fulfill({json:plan}));
  await page.goto(base);
  await page.getByLabel('Latitude',{exact:true}).fill('13.14');
  await page.getByLabel('Longitude',{exact:true}).fill('78.13');
  await page.waitForFunction(() => document.querySelector('#district').value==='Kolar' && !document.querySelector('#district').disabled);
  await page.getByLabel('Crop',{exact:true}).selectOption('ragi');
  await page.getByRole('button',{name:'Read the field plan'}).click();
  await page.getByRole('heading',{name:'Dates to keep in view'}).waitFor();
  assert.equal(await page.getByRole('heading',{name:'Review weather before sowing',exact:true}).count(),14);
  assert.equal(await page.getByRole('heading',{name:'Review water before deciding',exact:true}).count(),0);
  assert((await page.locator('.actions-section').innerText()).includes('crop-water need is not estimated'));
  assert((await page.locator('.action-row').first().innerText()).includes('not a safe-to-sow recommendation'));
  if (plan.agent_note.includes('quota limit')) assert((await page.locator('.actions-section .notice').innerText()).includes('Gemini has reached a quota limit'));
  await page.emulateMedia({colorScheme:'dark'});
  await page.locator('.actions-section').evaluate(element => element.scrollIntoView({block:'start'}));
  if (process.env.SOWCAST_SCREENSHOT) await page.screenshot({path:process.env.SOWCAST_SCREENSHOT});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  console.log('PASS real unsown-ragi response: weather-only headings, no crop-water claim, visible quota cause and mobile containment');
} finally {await browser.close();}
