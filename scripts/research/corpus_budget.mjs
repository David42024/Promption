import fs from 'node:fs';
import path from 'node:path';
import { sha, lines, BudgetStop } from './api_budget.mjs';
import { setTimeout as delay } from 'node:timers/promises';

export class CorpusBudget {
  constructor(directory, protocol, previousLedger, fetchImpl = fetch) {
    const ceiling = ['precision_lumina_openai_three_conditions', 'precision_lumina_gemini_three_conditions',
      'precision_lumina_gemini_native_three_conditions', 'gemini_preflight', 'gemini_native_preflight', 'deepseek_preflight', 'precision_lumina_deepseek_three_conditions'].includes(protocol.study) ? 5
      : protocol.study === 'precision_lumina_three_conditions' ? 7 : 2;
    if (protocol.budget_usd !== ceiling || protocol.max_api_calls !== 1800 || sha(fs.readFileSync(previousLedger)) !== protocol.prior_ledger_sha256) throw Error('Unexpected shared authorization bounds');
    const old = new Map();
    for (const row of lines(previousLedger)) {
      if (row.kind === 'reserved') old.set(row.call, row.reserved_usd);
      if (row.kind === 'settled') old.set(row.call, row.charged_upper_usd);
    }
    this.prior = [...old.values()].reduce((a,b)=>a+b,0);
    if (Math.abs(this.prior-protocol.prior_spent_upper_usd)>1e-9) throw Error('Previous budget changed');
    this.directory=directory;this.protocol=protocol;this.fetchImpl=fetchImpl;this.quotas=new Map();this.outputReady=new Map();
    if(protocol.initial_quota_refill_ms)for(const model of Object.keys(protocol.groq_output_tokens_per_minute??{})){
      this.outputReady.set(model,Date.now()+protocol.initial_quota_refill_ms);
    }
    this.file=path.join(directory,'api_ledger.jsonl');this.costs=new Map();this.calls=0;this.stopped=false;
    for(const row of lines(this.file)){
      if(row.kind==='reserved'){this.calls=Math.max(this.calls,row.call);this.costs.set(row.call,row.reserved_usd);}
      if(row.kind==='settled')this.costs.set(row.call,row.charged_upper_usd);
    }
  }
  total(){return this.prior+[...this.costs.values()].reduce((a,b)=>a+b,0);}
  append(value){fs.appendFileSync(this.file,JSON.stringify({...value,at:new Date().toISOString()})+'\n',{mode:0o600});}
  async request(url,options,context){
    const endpoint=new URL(url);
    const groq=this.protocol.provider==='groq';
    const deepseek=this.protocol.provider==='deepseek';
    const native=this.protocol.provider==='gemini-native';
    const gemini=this.protocol.provider==='gemini'||native;
    const origin=gemini?'https://generativelanguage.googleapis.com':deepseek?'https://api.deepseek.com':groq?'https://api.groq.com':'https://api.openai.com';
    const match=native?endpoint.pathname.match(/^\/v1beta\/models\/([\w.-]+):generateContent$/):null;
    const pathname=native&&match?endpoint.pathname:gemini?'/v1beta/openai/chat/completions':deepseek?'/chat/completions':groq?'/openai/v1/chat/completions':'/v1/responses';
    if(endpoint.origin!==origin||endpoint.pathname!==pathname||endpoint.search||(native&&!match))throw Error('Unexpected endpoint');
    const body=typeof options.body==='string'?options.body:Buffer.from(options.body).toString();
    const parsed=JSON.parse(body);const model=native?match?.[1]:parsed.model;
    const rates=this.protocol.rates_usd_per_million[model];
    const maximum=native?parsed.generationConfig?.maxOutputTokens:gemini||deepseek?parsed.max_tokens:groq?parsed.max_completion_tokens:parsed.max_output_tokens;
    const effort=native?parsed.generationConfig?.thinkingConfig?.thinkingLevel:groq||gemini||deepseek?parsed.reasoning_effort:parsed.reasoning?.effort;
    const invalidTools=native?parsed.tools?.some(t=>Object.keys(t).some(key=>key!=='functionDeclarations')):parsed.tools?.some(t=>t.type!=='function');
    if(!rates||(gemini||deepseek?parsed.store!==undefined:parsed.store!==false)||maximum!==this.protocol.max_output_tokens||(deepseek?parsed.thinking?.type!=='disabled'||effort!==undefined:effort!==(gemini?'minimal':groq?'low':'none'))||invalidTools)throw Error('Unexpected request');
    if(native&&(parsed.serviceTier!==undefined||parsed.cachedContent!==undefined||parsed.contents?.some(message=>message.parts?.some(part=>part.functionCall&&part.thoughtSignature==='skip_thought_signature_validator'))))throw Error('Unsupported native provider fallback');
    if(gemini&&(this.protocol.free_tier_only!==true||rates.input!==0||rates.output!==0))throw Error('Gemini free-tier protocol required');
    if(gemini&&this.protocol.min_request_interval_ms){
      const wait=Math.max(0,(this.nextRequestAt??0)-Date.now());
      if(wait)await delay(wait,undefined,{signal:options.signal});
      this.nextRequestAt=Date.now()+this.protocol.min_request_interval_ms;
    }
    const outputLimit=this.protocol.groq_output_tokens_per_minute?.[parsed.model];
    if(outputLimit){
      while((this.outputReady.get(parsed.model)??0)>Date.now()){
        await delay(Math.min(55000,this.outputReady.get(parsed.model)-Date.now()),undefined,{signal:options.signal});
      }
    }
    const quotaLimit=this.protocol.groq_tokens_per_minute;
    if(groq&&quotaLimit){
      const needed=Math.ceil(Buffer.byteLength(body)/3)+maximum;
      if(needed>quotaLimit)throw Error('Request exceeds conservative token quota estimate');
      const previous=this.quotas.get(parsed.model)??{remaining:quotaLimit,at:Date.now()};
      const remaining=Math.min(quotaLimit,previous.remaining+(Date.now()-previous.at)*quotaLimit/60000);
      const wait=Math.max(0,Math.ceil((needed-remaining)*60000/quotaLimit)+500);
      if(wait>0)await delay(wait,undefined,{signal:options.signal});
      this.quotas.set(parsed.model,{remaining:Math.min(quotaLimit,remaining+wait*quotaLimit/60000)-needed,at:Date.now()});
    }
    const reserve=((Buffer.byteLength(body)+4000)*rates.input+this.protocol.max_output_tokens*rates.output)/1e6;
    if(this.stopped||this.calls>=this.protocol.max_api_calls||this.total()+reserve>this.protocol.budget_usd){this.stopped=true;throw new BudgetStop('SHARED_BUDGET_LIMIT');}
    const call=++this.calls;this.costs.set(call,reserve);
    fs.writeFileSync(path.join(this.directory,'requests',call+'.json'),body,{mode:0o600});
    this.append({kind:'reserved',call,reserved_usd:reserve,request_sha256:sha(body),model,...context});
    let charged=reserve;const entry={kind:'settled',call,...context};
    try{
      const response=await this.fetchImpl(url,{...options,redirect:'error',signal:AbortSignal.any([...(options.signal?[options.signal]:[]),AbortSignal.timeout(this.protocol.request_timeout_ms)])});
      entry.http_status=response.status;const payload=await response.clone().json();
      if(groq&&quotaLimit){
        const remaining=Number(response.headers.get('x-ratelimit-remaining-tokens'));
        if(response.headers.has('x-ratelimit-remaining-tokens')&&Number.isFinite(remaining))this.quotas.set(parsed.model,{remaining,at:Date.now()});
      }
      const input=native?payload.usageMetadata?.promptTokenCount:groq||gemini||deepseek?payload.usage?.prompt_tokens:payload.usage?.input_tokens;
      const output=native?(payload.usageMetadata?(payload.usageMetadata.candidatesTokenCount??0)+(payload.usageMetadata.thoughtsTokenCount??0):undefined)
        :groq||gemini||deepseek?payload.usage?.completion_tokens:payload.usage?.output_tokens;
      if(Number.isSafeInteger(input)&&Number.isSafeInteger(output)){
        if(outputLimit)this.outputReady.set(parsed.model,Date.now()+Math.ceil(output*60000/outputLimit)+1000);
        charged=(input*rates.input+output*rates.output)/1e6;
        entry.usage=native?{...payload.usageMetadata,input_tokens:input,output_tokens:output}:groq||gemini||deepseek?{...payload.usage,input_tokens:input,output_tokens:output}:payload.usage;
        entry.response_id=payload.id??payload.responseId;entry.actual_model=native?payload.modelVersion:payload.model;
        entry.provider=this.protocol.provider??'openai';
        entry.rate_limits=Object.fromEntries(['x-ratelimit-limit-requests','x-ratelimit-limit-tokens','x-ratelimit-remaining-requests','x-ratelimit-remaining-tokens','x-ratelimit-reset-requests','x-ratelimit-reset-tokens'].map(key=>[key,response.headers.get(key)]));
        if(charged>reserve||!(this.protocol.allowed_response_models?.[model]??[model]).includes(entry.actual_model))this.stopped=true;
      }else{entry.usage_missing=true;this.stopped=true;}
      const providerError=Array.isArray(payload)?payload[0]?.error:payload.error;
      fs.writeFileSync(path.join(this.directory,'api_responses',call+'.json'),JSON.stringify(response.ok?payload:{http_status:response.status,error:{code:providerError?.code,type:providerError?.type,status:providerError?.status,message:String(providerError?.message??'').replace(/(?:gsk_|sk-)[\w-]+|AIza[\w-]{20,}/g,'[REDACTED]').slice(0,1000)}}),{mode:0o600});
      return response;
    }catch(error){entry.error_name=error.name;this.stopped=true;throw error;}
    finally{this.costs.set(call,charged);this.append({...entry,charged_upper_usd:charged});}
  }
}
