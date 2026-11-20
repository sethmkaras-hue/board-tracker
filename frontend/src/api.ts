import { useEffect, useState } from 'react'

export type Person = {id:number; username:string; display_name:string; email:string|null; admin:boolean; csrf?:string}
export type Program = {id:number; name:string; epm_id:number|null; notes:string|null; manager_ids:number[]; deputy_ids:number[]}
export type Parent = {id:number; name:string; quantity:number; url:string|null; notes:string|null}
export const allocationStatuses = ['Not Allocated','Allocated'] as const
export type ReviewAssignmentInput = {reviewer_id:number; allocation_status:typeof allocationStatuses[number]}
export type ReviewAssignment = ReviewAssignmentInput & {reviewer_name:string}
export type Review = {
  id:number; kind:string; state:string; date:string|null; url:string|null
  review_start_date:string|null; effective_review_start_date:string|null; assignments:ReviewAssignment[]
}
export type Board = {
  id:number; identifier:string; active:boolean; deleted_at:string|null; schematic_ri_id:number;
  layout_ri_id:number|null; board_ri_ids:number[]; program_ids:number[]; programs:Program[];
  parents:Parent[]; reviews:Review[]; created_at:string; updated_at:string; created_by:number; updated_by:number;
  board_type:string|null; complexity:string|null; reuse_level:string|null; maturity:number|null;
  schematic_tool:string|null; layout_tool:string|null; components_status:string|null;
  aras_board_url:string|null; aras_export_url:string|null; overview_url:string|null; notes:string|null;
  revisions?:{id:number; identifier:string}[];
}
export type Event = {id:number; board_id:number|null; board_label:string|null; action:string; field:string; username:string; timestamp:string; previous:unknown; value:unknown; entity:string}
export type Metrics = Record<'types'|'maturity'|'complexity'|'reviews'|'verification'|'programs',Record<string,number>>
export type DashboardData = Metrics & {active:number; inactive:number; assigned:number; stale:number; recent:Board[]}
export type Page<T> = {items:T[]; total:number}
export class ApiError extends Error {
  constructor(public status:number, public detail:unknown) {
    super(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(e => [e.field,e.message].filter(Boolean).join(' · ')).join(' / ') : 'The request could not be completed.')
  }
}
let csrf = ''
export function setSession(person:Person|null) { csrf = person?.csrf || '' }
export async function api<T>(path:string, method='GET', body?:unknown, signal?:AbortSignal):Promise<T> {
  const response = await fetch('/api'+path, {
    method, signal,
    headers: { ...(body !== undefined ? {'Content-Type':'application/json'} : {}), ...(csrf ? {'X-CSRF-Token':csrf} : {}) },
    ...(body !== undefined ? {body:JSON.stringify(body)} : {}),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/me') window.dispatchEvent(new globalThis.Event('tracker-expired'))
    throw new ApiError(response.status, data.detail || response.statusText)
  }
  return response.status === 204 ? undefined as T : response.json()
}
export function useData<T>(path:string|null, refreshInterval?:number) {
  const [result,set] = useState<{path:string; data?:T; error?:string}>({path:''})
  const [version,refresh] = useState(0)
  useEffect(() => {
    if(path===null)return
    const c = new AbortController()
    api<T>(path,'GET',undefined,c.signal).then(data=>{
      if(!c.signal.aborted)set({path,data})
    }, error=>{
      if(c.signal.aborted)return
      const keepData=refreshInterval && (!(error instanceof ApiError)||error.status>=500)
      set(current=>({path,error:error.message,data:keepData&&current.path===path?current.data:undefined}))
    })
    return ()=>c.abort()
  },[path,version,refreshInterval])
  useEffect(()=>{
    if(!path||!refreshInterval)return
    const refreshVisible=()=>{
      if(document.visibilityState==='visible')refresh(value=>value+1)
    }
    const timer=window.setInterval(refreshVisible,refreshInterval)
    document.addEventListener('visibilitychange',refreshVisible)
    window.addEventListener('focus',refreshVisible)
    return ()=>{
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange',refreshVisible)
      window.removeEventListener('focus',refreshVisible)
    }
  },[path,refreshInterval])
  return {...(result.path===path?result:{}), reload:()=>refresh(v=>v+1)}
}
export function displayDate(value:string) {
  return new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value))
}

export function browserTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}
export function show(value:unknown):string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.map(show).join(', ') || '—'
  if (typeof value === 'object') return 'name' in value ? String(value.name) : JSON.stringify(value)
  return String(value)
}
