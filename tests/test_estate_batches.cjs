const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const root = require('path').resolve(__dirname, '..');
const ts = require(root + '/web/node_modules/typescript');
const code = ts.transpileModule(fs.readFileSync(root + '/web/src/lib/realestate.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const calls=[];
const sandbox={exports:{},process:{env:{}},require:()=>({apiFetch:async(url,init)=>{
 const q=JSON.parse(init.body);calls.push(q);
 if(q.regions.includes('r5')) throw new Error('simulated failure');
 return {ok:true,json:async()=>({items:q.regions.map((r,i)=>({id:r,date:`2026-09-${String(i+1).padStart(2,'0')}`,property_type:'아파트'})),errors:[],requests:q.regions.length*q.property_types.length})};
}})};
vm.runInNewContext(code,sandbox);
(async()=>{
 const progress=[];
 const out=await sandbox.exports.estateApi.trades({regions:[...Array.from({length:12},(_,i)=>`r${i}`),'r0'],property_types:['아파트','오피스텔'],month:'202609',max_price_100m:5,max_area:85},(done,total)=>progress.push([done,total]));
 assert.equal(calls.length,3);assert.equal(out.items.length,7);assert.equal(out.errors.length,1);assert.equal(out.counts['아파트'],7);
 assert(calls.every(q=>q.regions.length<=5 && q.max_price_100m===5 && q.max_area===85));
 assert.deepEqual(progress,[[5,12],[10,12],[12,12]]);
 assert(out.items.every((x,i)=>i===0||out.items[i-1].date>=x.date));
 console.log('PASS: batching, duplicate regions, partial failure, price preservation, counts, progress, sorting');
})().catch(e=>{console.error(e);process.exitCode=1});
