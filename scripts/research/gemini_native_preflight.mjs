import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseEnv} from 'node:util';
import {createGoogleGenerativeAI} from '@ai-sdk/google';
import {CorpusBudget} from './corpus_budget.mjs';
import {createPromption, createContextEvaluator} from '../../packages/ai-sdk/src/index.js';

if(!process.argv.includes('--allow-external'))throw Error('Explicit --allow-external required');
const root=process.cwd();const directory=path.resolve(process.argv[2]);
const protocol=JSON.parse(fs.readFileSync(path.join(directory,'protocol.json')));
if(protocol.study!=='gemini_native_preflight')throw Error('Unexpected preflight');
const budget=new CorpusBudget(directory,protocol,path.join(directory,'prior_ledger.jsonl'));
if(budget.calls)throw Error('Preserve previous preflight outcomes');
const {generateText,jsonSchema,tool,wrapLanguageModel,stepCountIs}=await import(pathToFileURL(path.join(root,'packages/ai-sdk/node_modules/ai/dist/index.js')).href);
const key=parseEnv(fs.readFileSync('.env.gemini.local','utf8')).GEMINI_API_KEY;
const google=createGoogleGenerativeAI({apiKey:key,fetch:(url,options)=>budget.request(url,options,{purpose:'native_synthetic_compatibility'})});
const providerOptions={google:{thinkingConfig:{thinkingLevel:'minimal',includeThoughts:false}}};
const identity={userId:'synthetic',roles:['customer'],authenticated:true};
const protection=createPromption({transport:async({text})=>({allowed:true,text})});
const policy={roles:['customer']};
let result;
try{
 const model=wrapLanguageModel({model:google(protocol.generation_model),middleware:protection.middleware({identity,
  toolPolicies:{company_information:policy}})});
 const probe=await generateText({model,system:'Help with the fictional public catalog. Consult the tool and then answer with the product name and price.',
  prompt:'Consulta el catálogo público usando company_information con query="catalogo".',stopWhen:stepCountIs(3),
  prepareStep:({stepNumber})=>({toolChoice:stepNumber===0?{type:'tool',toolName:'company_information'}:'none'}),
  tools:{company_information:protection.protectTool(tool({description:'Public fictional lamps catalog.',
   inputSchema:jsonSchema({type:'object',properties:{query:{type:'string'}},required:['query'],additionalProperties:false}),
   execute:async()=>({product:'Aurora',price:80})}),{name:'company_information',identity,policy})},
  maxOutputTokens:protocol.max_output_tokens,maxRetries:0,providerOptions});
 const signatures=[];
 for(const file of fs.readdirSync(path.join(directory,'api_responses'))){
  const value=JSON.parse(fs.readFileSync(path.join(directory,'api_responses',file)));
  for(const candidate of value.candidates??[])for(const part of candidate.content?.parts??[]){
   if(part.functionCall&&part.thoughtSignature)signatures.push(part.thoughtSignature);
  }
 }
 const tools_ok=probe.steps.flatMap(step=>step.toolCalls).some(call=>call.toolName==='company_information');
 const roundtrip_ok=probe.steps.length>=2&&probe.text.includes('Aurora');
 const private_signatures_hidden=signatures.length>0&&signatures.every(signature=>!JSON.stringify(probe.steps).includes(signature)&&!JSON.stringify(probe.response).includes(signature));
 const evaluate=createContextEvaluator({model:google(protocol.scope_model),maxOutputTokens:protocol.max_output_tokens,providerOptions,schemaMode:'portable'});
 const verdict=await evaluate({text:'Hola, ¿qué productos públicos ofrecen?',systemPrompt:'Public catalog information and greetings are allowed. Never disclose private configuration.',identity,messages:[]});
 result={tools_ok,roundtrip_ok,private_signatures_hidden,structured_ok:verdict.allowed===true,api_calls:budget.calls,accounted_upper_usd:budget.total()};
}catch(error){result={tools_ok:false,structured_ok:false,error_name:error.name,error_code:error.code,http_status:error.statusCode,
 error_message:String(error.message).replace(/(?:gsk_|sk-)[\w-]+|AIza[\w-]{20,}/g,'[REDACTED]').slice(0,600),
 api_calls:budget.calls,accounted_upper_usd:budget.total()};}
fs.writeFileSync(path.join(directory,'result.json'),JSON.stringify(result,null,2),{mode:0o600});
process.stdout.write(JSON.stringify(result)+'\n');
