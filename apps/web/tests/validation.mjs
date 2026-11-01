import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const base=process.env.SOWCAST_WEB_URL || 'http://127.0.0.1:5173';
const browser=await chromium.launch({headless:true});
const page=await browser.newPage();
try {
  await page.goto(base);
  await page.getByLabel('Latitude',{exact:true}).fill('13.14');
  await page.getByLabel('Longitude',{exact:true}).fill('78.13');
  await page.getByLabel('Crop',{exact:true}).selectOption('maize');
  await page.waitForFunction(()=>document.querySelector('#district')?.value==='Kolar');
  await page.getByLabel('Already growing',{exact:true}).check();
  await page.getByLabel('Sowing date',{exact:true}).fill('2019-12-31');
  await page.getByRole('button',{name:'Read the field plan'}).click();
  await page.getByRole('alert').filter({hasText:'sowing_date: use a date from 2020 through one year ahead.'}).waitFor();
  await page.getByRole('heading',{name:'A pause in the data.'}).waitFor();
  await page.getByRole('button',{name:'Ask',exact:true}).click();
  await page.getByLabel('Your question').fill('   ');
  assert(await page.getByRole('button',{name:'Ask Sowcast',exact:true}).isDisabled());
  await page.getByLabel('Your question').fill('Check evidence');
  await page.getByRole('button',{name:'Ask Sowcast',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'sowing_date: use a date from 2020 through one year ahead.'}).waitFor();
  console.log('PASS server field errors in existing Plan and Ask error states; blank chat disabled');
} finally {await browser.close();}
