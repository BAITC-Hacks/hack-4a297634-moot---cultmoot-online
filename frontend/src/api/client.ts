let csrf='';
export class ApiError extends Error {constructor(message:string,public status:number){super(message);}}
export async function request<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
  const r=await fetch(path,{method,credentials:'same-origin',signal:AbortSignal.timeout(30000),headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json().catch(()=>({detail:'Сервис временно недоступен. Повторите позже.'}));
  if(!r.ok)throw new ApiError(typeof data.detail==='string'?data.detail:`HTTP ${r.status}`,r.status);
  return data;
}
export async function openSession(){const result=await request('/api/session','POST',{});csrf=result.csrf;return result;}
export type Trace={request_id:string;transcript:string;language:string;decision:string;scenario_id:string|null;scenario_name:string|null;confidence:number;reason_short:string;alternatives:{scenario_id:string;confidence:number;name_ru:string;name_kk:string}[];provider:string;action:string;latency:Record<string,number|null>;topic_changed:boolean;requires_confirmation:boolean;validation_errors:string[];attempts:number};
export type Tutorial={id:string;title:string;language?:string;index:number;source:string|null;steps:{title:string;text:string;target:string}[]};
export type Result={response:string;trace:Trace;state:any;backend:any;audio_url:string|null;tutorial?:Tutorial|null;tutorial_offer?:boolean};
