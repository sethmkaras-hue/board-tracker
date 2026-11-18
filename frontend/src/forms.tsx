import { useEffect, useId, useLayoutEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { ApiError, show } from './api'
import { Failure } from './shared'
import { labels } from './fields'
import { Button } from './components/ui/button'

export type Value = string|number|boolean|number[]|null
export type Values = Record<string,Value>
type Choice = {value:string|number; label:string}
export type Field = {key:string; options?:Choice[]; kind?:'many'|'notes'|'boolean'|'number'|'url'|'date'; required?:boolean; numeric?:boolean; help?:string}
export const choices = (values:(number|string)[]):Choice[] => values.map(value=>({value,label:String(value)}))
export type Edit = {changes:Values;expected:Values;overwrite:boolean}

export function Modal({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}) {
  const element=useRef<HTMLDialogElement>(null)
  useLayoutEffect(()=>{element.current?.showModal()},[])
  return <dialog ref={element} onCancel={e=>{e.preventDefault();onClose()}} aria-label={title} className="panel modal">
    <div className="section-heading"><h2>{title}</h2><button type="button" aria-label="Close" className="icon-button" onClick={onClose}><X size={19}/></button></div>{children}
  </dialog>
}

function Multi({field,value,onChange}:{field:Field;value:Value;onChange:(v:Value)=>void}) {
  const [term,setTerm]=useState('')
  const [open,setOpen]=useState(false)
  const selected=Array.isArray(value)?value:[]
  const matches=field.options?.filter(e=>e.label.toLowerCase().includes(term.toLowerCase()))||[]
  return <div className="picker">
    <Button type="button" variant="outline" aria-expanded={open} onClick={()=>setOpen(!open)}>{selected.length ? field.options?.filter(o=>selected.includes(Number(o.value))).map(o=>o.label).join(', ') : 'Select people or records'}</Button>
    {open && <div className="picker-options">
      <input aria-label={'Search '+(labels[field.key]||field.key)} placeholder="Search options…" value={term} onChange={e=>setTerm(e.target.value)}/>
      {matches.length?matches.map(o=><label className="check" key={o.value}><input type="checkbox" checked={selected.includes(Number(o.value))}
        onChange={e=>onChange(e.target.checked?[...selected,Number(o.value)].sort((a,b)=>a-b):selected.filter(v=>v!==Number(o.value)))}/>{o.label}</label>):<small>No matching options.</small>}
    </div>}
  </div>
}

function SinglePerson({field,value,onChange}:{field:Field;value:Value;onChange:(v:Value)=>void}) {
  const [filter,setFilter]=useState('')
  return <div className="person-pick">
    <input aria-label={'Search '+labels[field.key]} placeholder="Search people…" value={filter} onChange={e=>setFilter(e.target.value)} />
    <select aria-label={labels[field.key]} value={String(value??'')} required={field.required} onChange={e=>onChange(e.target.value?Number(e.target.value):null)}>
      <option value="">Select a person</option>
      {field.options?.filter(o=>o.value===value||o.label.toLowerCase().includes(filter.toLowerCase())).map(o=><option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </div>
}

export function FieldEditor({field,value,onChange}:{field:Field;value:Value;onChange:(v:Value)=>void}) {
  const label=labels[field.key]||field.key
  const id=useId()
  const bytes=4096-new TextEncoder().encode(String(value??'')).length
  if(field.kind==='boolean') return <label className="check"><input type="checkbox" checked={!!value} onChange={e=>onChange(e.target.checked)}/>{label}</label>
  return <div className={'form-field '+(field.kind==='notes'?'wide':'')}>
    <label htmlFor={field.kind==='many'||field.key.endsWith('_id')?undefined:id}>{label}{field.required?' *':''}</label>
    {field.kind==='many'?<Multi field={field} value={value} onChange={onChange}/>:
    field.key.endsWith('_id')&&field.options?<SinglePerson field={field} value={value} onChange={onChange}/>:
    field.options?<select id={id} required={field.required} value={String(value??'')} onChange={e=>onChange(e.target.value ? (field.numeric?Number(e.target.value):e.target.value) : null)}>
      <option value="">Select {label.toLowerCase()}</option>{field.options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select>:
    field.kind==='notes'?<><textarea id={id} rows={4} value={String(value??'')} onChange={e=>onChange(e.target.value||null)}/>
      {field.help && <small className={bytes<0?'negative':''}>{bytes.toLocaleString()} UTF-8 bytes remaining</small>}</>:
    <input id={id} required={field.required} type={field.kind||'text'} min={field.kind==='number'?0:undefined} step={field.kind==='number'?1:undefined}
      pattern={field.key==='identifier'?'SRC[0-9]{5}[A-Z]?':undefined} placeholder={field.key==='identifier'?'SRC00123A':undefined}
      value={String(value??'')} onChange={e=>onChange(e.target.value===''?null:field.kind==='number'?Number(e.target.value):e.target.value)}/>}
    {field.help&&field.kind!=='notes'&&<small>{field.help}</small>}
  </div>
}

export function Editor({fields,initial,onSave,onCancel,creating=false}:{fields:Field[];initial:Values;onSave:(edit:Edit)=>Promise<void>;onCancel:()=>void;creating?:boolean}) {
  const [draft,setDraft]=useState(initial)
  const [baseline,setBaseline]=useState(initial)
  const [error,setError]=useState('')
  const [conflicts,setConflicts]=useState<Record<string,{current:unknown;proposed:unknown}>>({})
  const [busy,setBusy]=useState(false)
  const changes=Object.fromEntries(Object.entries(draft).filter(([key,v])=>JSON.stringify(baseline[key])!==JSON.stringify(v)))
  const dirty=Object.keys(changes).length>0
  useEffect(()=>{
    function unload(e:BeforeUnloadEvent){if(dirty)e.preventDefault()}
    function navigate(e:MouseEvent){if(dirty && e.target instanceof Element && e.target.closest('a')&&!window.confirm('Discard unsaved changes?')){e.preventDefault();e.stopPropagation()}}
    window.addEventListener('beforeunload',unload)
    document.addEventListener('click',navigate,true)
    return ()=>{window.removeEventListener('beforeunload',unload);document.removeEventListener('click',navigate,true)}
  },[dirty])
  async function save(overwrite=false) {
    setBusy(true);setError('');setConflicts({})
    try {await onSave({changes:creating?draft:changes,expected:baseline,overwrite})}
    catch(e) {
      if(e instanceof ApiError && e.status===409 && e.detail && typeof e.detail==='object' && 'fields' in e.detail) setConflicts(e.detail.fields as typeof conflicts)
      else setError((e as Error).message)
    } finally {setBusy(false)}
  }
  function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();void save()}
  return <form className="editor" onSubmit={submit}>
    {error&&<Failure message={error}/>}
    {Object.keys(conflicts).length>0&&<div className="error" role="alert"><strong>This record changed while you were editing.</strong>
      <ul>{Object.entries(conflicts).map(([key,values])=><li key={key}>{labels[key]||key} · Current: {show(values.current)} · Yours: {show(values.proposed)}</li>)}</ul>
      <div className="form-actions"><Button type="button" variant="outline" onClick={()=>window.location.reload()}>Refresh record</Button>
        <Button type="button" variant="outline" onClick={()=>{
          const latest=Object.fromEntries(Object.entries(conflicts).map(([key,value])=>[key,value.current])) as Values
          setBaseline({...baseline,...latest})
          setDraft({...draft,...latest})
          setConflicts({})
        }}>Use current values</Button>
        <Button type="button" variant="danger" disabled={busy} onClick={()=>void save(true)}>Overwrite changed fields</Button></div>
    </div>}
    <div className="form-grid">{fields.map(field=><FieldEditor key={field.key} field={field} value={draft[field.key]??null} onChange={value=>{
      setDraft(current=>({...current,[field.key]:value}));setConflicts({})
    }}/>)}</div>
    <div className="form-actions"><Button type="button" variant="outline" onClick={()=>{if(!dirty||window.confirm('Discard unsaved changes?'))onCancel()}}>Cancel</Button>
      <Button disabled={busy||(!dirty&&!creating)}>{busy?'Saving…':creating?'Create record':'Save changes'}</Button></div>
  </form>
}
