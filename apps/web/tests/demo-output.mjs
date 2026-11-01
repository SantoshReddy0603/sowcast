import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {copyFile,mkdtemp,mkdir,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
const script=fileURLToPath(new URL('./demo.mjs',import.meta.url));
const root=fileURLToPath(new URL('../../..',import.meta.url));
for(const output of ['',root]) {
  const result=spawnSync(process.execPath,[script],{env:{...process.env,SOWCAST_DEMO_OUTPUT:output},encoding:'utf8'});
  assert.notEqual(result.status,0);
  assert.match(result.stderr,/outside the checkout/);
}
const encodedRoot=await mkdtemp(path.join(tmpdir(),'sowcast space % '));
try {
  const directory=path.join(encodedRoot,'apps','web','tests');
  await mkdir(directory,{recursive:true});
  const copy=path.join(directory,'demo.mjs');
  await copyFile(script,copy);
  const result=spawnSync(process.execPath,[copy],{env:{...process.env,SOWCAST_DEMO_OUTPUT:encodedRoot},encoding:'utf8'});
  assert.notEqual(result.status,0);
  assert.match(result.stderr,/outside the checkout/);
} finally {await rm(encodedRoot,{recursive:true,force:true});}
console.log('PASS recording refuses missing output and checkout output before launching a browser');
