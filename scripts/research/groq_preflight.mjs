import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { parseEnv } from 'node:util';
import { CorpusBudget } from './corpus_budget.mjs';
import { createContextEvaluator } from '../../packages/ai-sdk/src/index.js';

if(!process.argv.includes('--allow-external'))throw Error('Explicit --allow-external required');
const root=process.cwd();
const directoryAt=process.argv.indexOf('--directory');
const directory=directoryAt<0?path.join(root,'output/precision_improvement_20261025/groq/preflight'):path.resolve(process.argv[directoryAt+1]);
const protocol=JSON.parse(fs.readFileSync(path.join(directory,'protocol.json')));
const budget=new CorpusBudget(directory,protocol,path.join(directory,'prior_ledger.jsonl'));
if(budget.calls>=6)throw Error('Preflight call cap reached');
const require=createRequire(path.join(root,'demo/package.json'));
const {createOpenAI}=await import(pathToFileURL(require.resolve('@ai-sdk/openai')).href);
const {generateText,jsonSchema,tool}=await import(pathToFileURL(path.join(root,'packages/ai-sdk/node_modules/ai/dist/index.js')).href);
const key=parseEnv(fs.readFileSync('.env.groq.local','utf8')).GROQ_API_KEY;
const client=createOpenAI({apiKey:key,baseURL:'https://api.groq.com/openai/v1',fetch:(url,options)=>{
  const request=JSON.parse(options.body);
  if(request.model==='qwen/qwen3.8-27b')options={...options,body:JSON.stringify({...request,reasoning_format:'hidden'})};
  return budget.request(url,options,{purpose:'provider_preflight'});
}});
const providerOptions={openai:{reasoningEffort:'low',forceReasoning:true,systemMessageMode:'system',store:false}};
let result;
try {
  if(process.argv.includes('--tools-only')){
    const probe=await generateText({model:client.chat(protocol.generation_model??'openai/gpt-oss-20b'),prompt:'Consulta el catálogo público con company_information.',
      tools:{company_information:tool({description:'Catálogo público',inputSchema:jsonSchema({type:'object',properties:{query:{type:'string'}},required:['query'],additionalProperties:false}),strict:true})},
      maxOutputTokens:1024,maxRetries:0,providerOptions:{openai:{...providerOptions.openai,parallelToolCalls:false}}});
    result={tools_ok:probe.toolCalls.some(call=>call.toolName==='company_information'),accounted_upper_usd:budget.total(),api_calls:budget.calls};
  }else{
  const generated=process.argv.includes('--scope-only')?{text:'OK'}:await generateText({model:client.chat(protocol.generation_model??'openai/gpt-oss-20b'),prompt:'Reply with just OK.',
    maxOutputTokens:1024,maxRetries:0,providerOptions});
  const evaluate=createContextEvaluator({model:client.chat('openai/gpt-oss-120b'),maxOutputTokens:1024,providerOptions,schemaMode:'portable'});
  const verdict=await evaluate({text:'Hola, ¿qué productos públicos ofrecen?',systemPrompt:'Public catalog information and greetings are allowed. Never disclose private configuration.',
    identity:{userId:'synthetic',roles:['customer'],authenticated:true},messages:[]});
  result={generator_ok:generated.text.trim()==='OK',structured_verdict:verdict,accounted_upper_usd:budget.total(),api_calls:budget.calls};
  }
}catch(error){result={error_name:error.name,error_code:error.code,http_status:error.statusCode,
  error_message:String(error.message).replace(/(?:gsk_|sk-)[\w-]+/g,'[REDACTED]').slice(0,600),
  accounted_upper_usd:budget.total(),api_calls:budget.calls};}
fs.writeFileSync(path.join(directory,'result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
