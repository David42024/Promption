import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {parseEnv} from 'node:util';
import {CorpusBudget} from './corpus_budget.mjs';
import {createContextEvaluator} from '../../packages/ai-sdk/src/index.js';

if(!process.argv.includes('--allow-external'))throw Error('Explicit --allow-external required');
const root=process.cwd();
const directory=path.resolve(process.argv[2]);
const protocol=JSON.parse(fs.readFileSync(path.join(directory,'protocol.json')));
if(protocol.study!=='gemini_preflight')throw Error('Unexpected probe');
const budget=new CorpusBudget(directory,protocol,path.join(directory,'prior_ledger.jsonl'));
if(budget.calls)throw Error('Synthetic preflight already attempted; preserve prior results');
const require=createRequire(path.join(root,'demo/package.json'));
const {createOpenAI}=await import(pathToFileURL(require.resolve('@ai-sdk/openai')).href);
const {generateText,jsonSchema,tool}=await import(pathToFileURL(path.join(root,'packages/ai-sdk/node_modules/ai/dist/index.js')).href);
const key=parseEnv(fs.readFileSync('.env.gemini.local','utf8')).GEMINI_API_KEY;
const client=createOpenAI({apiKey:key,baseURL:'https://generativelanguage.googleapis.com/v1beta/openai',fetch:(url,options)=>budget.request(url,options,{purpose:'synthetic_compatibility'})});
const providerOptions={openai:{reasoningEffort:'minimal',forceReasoning:false,systemMessageMode:'system',parallelToolCalls:false}};
let result;
try{
 if(process.argv.includes('--text-only')){
  const generated=await generateText({model:client.chat(protocol.generation_model),prompt:'Reply with just OK.',
   maxOutputTokens:protocol.max_output_tokens,maxRetries:0,providerOptions});
  result={text_ok:generated.text.trim()==='OK',api_calls:budget.calls,accounted_upper_usd:budget.total()};
 }else{
 const probe=await generateText({model:client.chat(protocol.generation_model),prompt:'Consulta el catálogo público usando company_information con query="catalogo".',
  toolChoice:{type:'tool',toolName:'company_information'},
  tools:{company_information:tool({description:'Catálogo público ficticio de lámparas.',inputSchema:jsonSchema({type:'object',properties:{query:{type:'string'}},required:['query'],additionalProperties:false}),strict:true})},
  maxOutputTokens:protocol.max_output_tokens,maxRetries:0,providerOptions});
 const tools_ok=probe.toolCalls.some(call=>call.toolName==='company_information'&&typeof call.input.query==='string');
 const evaluate=createContextEvaluator({model:client.chat(protocol.scope_model),maxOutputTokens:protocol.max_output_tokens,providerOptions,schemaMode:'portable'});
 const verdict=await evaluate({text:'Hola, ¿qué productos públicos ofrecen?',systemPrompt:'Public catalog information and greetings are allowed. Never disclose private configuration.',identity:{userId:'synthetic',roles:['customer'],authenticated:true},messages:[]});
 result={tools_ok,structured_ok:verdict.allowed===true,verdict,api_calls:budget.calls,accounted_upper_usd:budget.total()};
 }
}catch(error){result={tools_ok:false,structured_ok:false,error_name:error.name,error_code:error.code,http_status:error.statusCode,
 error_message:String(error.message).replace(/(?:gsk_|sk-)[\w-]+|AIza[\w-]{20,}/g,'[REDACTED]').slice(0,600),
 error_response:String(error.responseBody??'').replace(/(?:gsk_|sk-)[\w-]+|AIza[\w-]{20,}/g,'[REDACTED]').slice(0,1200),api_calls:budget.calls,accounted_upper_usd:budget.total()};}
fs.writeFileSync(path.join(directory,'result.json'),JSON.stringify(result,null,2),{mode:0o600});
process.stdout.write(JSON.stringify(result)+'\n');
