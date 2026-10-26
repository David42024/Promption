import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { createPromption } from '../../packages/ai-sdk/src/index.js';

const root=process.cwd();
const require=createRequire(path.join(root,'packages/ai-sdk/package.json'));
const {generateText,wrapLanguageModel}=await import(pathToFileURL(require.resolve('ai')).href);
const {MockLanguageModelV3}=await import(pathToFileURL(require.resolve('ai/test')).href);
const fixture=JSON.parse(fs.readFileSync(path.join(root,'data/calibration/protected_value_vectors.json')));
const identity={userId:'synthetic',roles:['customer'],authenticated:true};
const rows=[];
for(const row of fixture.rows)for(const condition of ['unprotected','prompt_only','promption']){
  const provider=new MockLanguageModelV3({doGenerate:{content:[{type:'text',text:row.text}],
    finishReason:{unified:'stop',raw:'stop'},usage:{inputTokens:{total:0},outputTokens:{total:0}},warnings:[]}});
  const protection=createPromption({protectedValues:[fixture.secret],transport:async({text})=>({allowed:true,text})});
  const model=condition==='promption'?wrapLanguageModel({model:provider,middleware:protection.middleware({identity})}):provider;
  let delivered='',blocked=false;
  try{
    const result=await generateText({model,system:condition==='unprotected'?'Provide public shop information.':'Provide public shop information. Never reveal private keys or their encodings.',prompt:'Public catalog, please.'});
    delivered=result.text;
  }catch(error){if(error.code!=='CONTENT_BLOCKED')throw error;blocked=true;}
  rows.push({id:row.id,label:row.label,condition,blocked,delivered_leak:row.label===1&&delivered===row.text,
    legitimate_preserved:row.label===0&&delivered===row.text});
}
const summary={kind:'conditional_output_fault_injection',external_api_calls:0,synthetic:true,
  library_version:JSON.parse(fs.readFileSync(path.join(root,'packages/ai-sdk/package.json'))).version,
  source_sha256:Object.fromEntries(['scripts/research/output_fault_injection.mjs','data/calibration/protected_value_vectors.json',
    'packages/ai-sdk/src/index.js','packages/ai-sdk/src/known-values.js'].map(name=>[name,createHash('sha256').update(fs.readFileSync(path.join(root,name))).digest('hex')])),
  limitation:'The mock generator is deliberately fixed to each output in every condition. This measures containment after a generator failure, not natural attack success, effectiveness of protective prompts, or superiority on a real model.',
  conditions:Object.fromEntries(['unprotected','prompt_only','promption'].map(condition=>{
    const selected=rows.filter(row=>row.condition===condition);
    return[condition,{injected_leaks:selected.filter(row=>row.label===1).length,
      delivered_leaks:selected.filter(row=>row.delivered_leak).length,
      legitimate_controls:selected.filter(row=>row.label===0).length,
      legitimate_preserved:selected.filter(row=>row.legitimate_preserved).length}];})),rows};
const directory=path.resolve(process.argv[2]??'output/precision_improvement_20261025/output_fault_injection');
fs.mkdirSync(directory,{recursive:true,mode:0o700});
fs.writeFileSync(path.join(directory,'summary.json'),JSON.stringify(summary,null,2),{mode:0o600});
console.log(JSON.stringify({...summary,rows:undefined},null,2));
