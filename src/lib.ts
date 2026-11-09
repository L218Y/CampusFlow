export type Task={id:number;title:string;course:string;description:string;priority:'low'|'medium'|'high';status:'todo'|'doing'|'done';due_date:string|null;scheduled_start:string|null;duration_minutes:number;project_id?:string|null;project_title?:string|null;step_index?:number|null};
export type Plan={id:string;title:string;goal:string;daily_budget_minutes:number;tasks:Task[];status:string};
export type Trace={id:string;name:string;arguments:unknown;result:{action_id?:string;draft?:Plan;[key:string]:unknown};status:string;duration_ms:number};
export type Message={id:string;role:string;content:string;traces?:Trace[];usage?:{total_tokens:number};error?:boolean};
export type Health={configured:boolean;model:string;provider:string};
export type Overview={total:number;completed:number;pending:number;overdue:number;today:number;completion_rate:number};
export type Change={action_id?:string;tasks?:Task[]};
export const STATUS={todo:'待开始',doing:'进行中',done:'已完成'};
export const PRIORITY={low:'低优先级',medium:'中优先级',high:'高优先级'};
export const LABELS:Record<string,string>={list_tasks:'查询任务',get_overview:'读取统计',create_task:'创建任务',update_task:'修改任务',complete_task:'完成任务',delete_task:'删除任务',propose_plan:'生成计划草稿'};
const fmt=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'});
export const today=()=>fmt.format(new Date());
export const dayDate=(s:string)=>new Date(s+'T12:00:00+08:00');
export function addDays(s:string,n:number){const d=dayDate(s);d.setUTCDate(d.getUTCDate()+n);return fmt.format(d);}
export const monday=(s:string)=>addDays(s,-((dayDate(s).getUTCDay()+6)%7));
export const shortDate=(s:string)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'numeric',day:'numeric'}).format(dayDate(s));
export const dateTitle=(s:string)=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'long'}).format(dayDate(s));
export const taskDay=(t:Task)=>t.scheduled_start?.slice(0,10)||t.due_date;
export const cstTime=(s:string)=>s?(s.length===16?s+':00+08:00':s):null;
export const freshTask=():Task=>({id:0,title:'',course:'个人学习',description:'',priority:'medium',status:'todo',due_date:null,scheduled_start:null,duration_minutes:45});
export async function api<T>(path:string,method='GET',body?:unknown,key?:string):Promise<T>{
 const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},body:body===undefined?undefined:JSON.stringify(body)});
 const d=await r.json().catch(()=>({detail:'后端返回了无法识别的响应'}));
 if(!r.ok)throw new Error(typeof d.detail==='string'?d.detail:'操作失败，请检查输入。');
 return d;
}
