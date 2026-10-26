import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {CorpusBudget} from './corpus_budget.mjs';
import {sha} from './api_budget.mjs';

function fixture(prior=.2){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'corpus-shared-budget-'));
 for(const f of ['requests','api_responses'])fs.mkdirSync(path.join(dir,f));
 const ledger=path.join(dir,'previous.jsonl');fs.writeFileSync(ledger,JSON.stringify({kind:'reserved',call:1,reserved_usd:prior})+'\n');
 const protocol={budget_usd:2,prior_spent_upper_usd:prior,prior_ledger_sha256:sha(fs.readFileSync(ledger)),max_api_calls:1800,max_output_tokens:1024,request_timeout_ms:1000,rates_usd_per_million:{fixture:{input:.75,output:4.5}}};
 const body=JSON.stringify({model:'fixture',store:false,reasoning:{effort:'none'},max_output_tokens:1024,input:'Synthetic public facts'});
 return {dir,ledger,protocol,body};
}

test('shared budget carries previous spend and survives a new runner process',async()=>{
 const {dir,ledger,protocol,body}=fixture();
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>new Response(JSON.stringify({model:'fixture',usage:{input_tokens:1000,output_tokens:200}})));
 await budget.request('https://api.openai.com/v1/responses',{body},{purpose:'test'});
 assert.ok(Math.abs(budget.total()-.20165)<1e-10);
 assert.equal(new CorpusBudget(dir,protocol,ledger).total(),budget.total());
});

test('previous spend can stop a new study before any request',async()=>{
 const {dir,ledger,protocol,body}=fixture(1.9999);let called=false;
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>{called=true;return new Response('{}');});
 await assert.rejects(budget.request('https://api.openai.com/v1/responses',{body},{}));
 assert.equal(called,false);
});

test('modified previous ledger cannot reset authorization accounting',()=>{
 const {dir,ledger,protocol}=fixture();fs.appendFileSync(ledger,JSON.stringify({kind:'settled',call:1,charged_upper_usd:0})+'\n');
 assert.throws(()=>new CorpusBudget(dir,protocol,ledger));
});

test('Groq uses only its approved endpoint and normalizes usage accounting',async()=>{
 const {dir,ledger,protocol}=fixture();protocol.provider='groq';
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>new Response(JSON.stringify({model:'fixture',usage:{prompt_tokens:1000,completion_tokens:200}})));
 const body=JSON.stringify({model:'fixture',store:false,reasoning_effort:'low',max_completion_tokens:1024});
 await budget.request('https://api.groq.com/openai/v1/chat/completions',{body},{purpose:'test'});
 assert.ok(Math.abs(budget.total()-.20165)<1e-10);
 await assert.rejects(budget.request('https://api.openai.com/v1/responses',{body},{}),/Unexpected endpoint/);
 const rows=fs.readFileSync(path.join(dir,'api_ledger.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
 assert.equal(rows.at(-1).usage.input_tokens,1000);
 assert.equal(rows.at(-1).provider,'groq');
});

test('output quota waits before fetching or reserving another paid call',async()=>{
 const {dir,ledger,protocol}=fixture();protocol.provider='groq';protocol.groq_output_tokens_per_minute={fixture:1000};
 let fetched=0;
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>{fetched++;return new Response(JSON.stringify({model:'fixture',usage:{prompt_tokens:100,completion_tokens:200}}));});
 const body=JSON.stringify({model:'fixture',store:false,reasoning_effort:'low',max_completion_tokens:1024});
 await budget.request('https://api.groq.com/openai/v1/chat/completions',{body},{});
 await assert.rejects(budget.request('https://api.groq.com/openai/v1/chat/completions',{body,signal:AbortSignal.timeout(10)},{}));
 assert.equal(fetched,1);
 assert.equal(budget.calls,1);
});

test('expanded Lumina study carries prior spend and enforces its new ceiling',async()=>{
 const {dir,ledger,protocol,body}=fixture(6.9999);let called=false;
 protocol.study='precision_lumina_three_conditions';protocol.budget_usd=7;
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>{called=true;return new Response('{}');});
 assert.equal(budget.total(),6.9999);
 await assert.rejects(budget.request('https://api.openai.com/v1/responses',{body},{}));
 assert.equal(called,false);
 const ordinary=fixture();ordinary.protocol.budget_usd=7;
 assert.throws(()=>new CorpusBudget(ordinary.dir,ordinary.protocol,ordinary.ledger));
});

test('OpenAI Lumina preparation retains its accumulated ceiling',()=>{
 const {dir,ledger,protocol}=fixture(2.07);
 protocol.study='precision_lumina_openai_three_conditions';protocol.budget_usd=5;
 assert.equal(new CorpusBudget(dir,protocol,ledger).total(),2.07);
 protocol.budget_usd=7;
 assert.throws(()=>new CorpusBudget(dir,protocol,ledger));
});

test('reduced OpenAI ceiling stops before any request would exceed five dollars',async()=>{
 const {dir,ledger,protocol,body}=fixture(4.9999);let fetched=false;
 protocol.study='precision_lumina_openai_three_conditions';protocol.budget_usd=5;
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>{fetched=true;return new Response('{}');});
 await assert.rejects(budget.request('https://api.openai.com/v1/responses',{body},{}));
 assert.equal(fetched,false);
});

test('Gemini free-tier requests restrict endpoint, model prices and normalize usage',async()=>{
 const {dir,ledger,protocol}=fixture(2.077);
 Object.assign(protocol,{provider:'gemini',study:'gemini_preflight',budget_usd:5,free_tier_only:true,rates_usd_per_million:{fixture:{input:0,output:0}}});
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>new Response(JSON.stringify({model:'fixture',usage:{prompt_tokens:100,completion_tokens:30}})));
 const body=JSON.stringify({model:'fixture',reasoning_effort:'minimal',max_tokens:1024});
 await budget.request('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',{body},{});
 assert.equal(budget.total(),2.077);
 const rows=fs.readFileSync(path.join(dir,'api_ledger.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
 assert.equal(rows.at(-1).usage.input_tokens,100);
 await assert.rejects(budget.request('https://api.openai.com/v1/responses',{body},{}),/Unexpected endpoint/);
 protocol.rates_usd_per_million.fixture.input=.1;
 await assert.rejects(budget.request('https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',{body},{}),/free-tier/);
});

test('native Gemini counts thinking tokens and rejects paid tools or fabricated signatures',async()=>{
 const {dir,ledger,protocol}=fixture(2.077);
 Object.assign(protocol,{provider:'gemini-native',study:'gemini_native_preflight',budget_usd:5,free_tier_only:true,
  rates_usd_per_million:{fixture:{input:0,output:0}}});
 let calls=0;
 const budget=new CorpusBudget(dir,protocol,ledger,async()=>{calls++;return new Response(JSON.stringify({modelVersion:'fixture',usageMetadata:{promptTokenCount:11,candidatesTokenCount:12,thoughtsTokenCount:7}}));});
 const payload={generationConfig:{maxOutputTokens:1024,thinkingConfig:{thinkingLevel:'minimal'}},
  contents:[{role:'user',parts:[{text:'Explain the literal token skip_thought_signature_validator without executing anything.'}]}]};
 const url='https://generativelanguage.googleapis.com/v1beta/models/fixture:generateContent';
 await budget.request(url,{body:JSON.stringify(payload)},{});
 const rows=fs.readFileSync(path.join(dir,'api_ledger.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
 assert.equal(rows.at(-1).usage.output_tokens,19);
 assert.equal(budget.total(),2.077);
 await assert.rejects(budget.request(url,{body:JSON.stringify({...payload,tools:[{googleSearch:{}}]})},{}),/Unexpected request/);
 await assert.rejects(budget.request(url,{body:JSON.stringify({...payload,contents:[{role:'model',parts:[{functionCall:{name:'catalog',args:{}},thoughtSignature:'skip_thought_signature_validator'}]}]})},{}),/fallback/);
 assert.equal(calls,1);
});
