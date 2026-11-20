import { useId, useLayoutEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { ApiError, show, type ReviewAssignmentInput } from './api'
import { Failure } from './shared'
import { labels } from './fields'
import { Button } from './components/ui/button'

export type Value = string|number|boolean|number[]|ReviewAssignmentInput[]|null
export type Values = Record<string,Value>
type Choice = {value:string|number; label:string}
export type Field = {key:string; label?:string; options?:Choice[]; kind?:'many'|'notes'|'boolean'|'number'|'url'|'date'; required?:boolean; numeric?:boolean; help?:string; max?:string; wide?:boolean; render?:(value:Value,onChange:(value:Value)=>void,draft:Values,error?:string)=>ReactNode}
export const choices = (values:(number|string)[]):Choice[] => values.map(value=>({value,label:String(value)}))
export type Edit = {changes:Values;expected:Values;overwrite:boolean}

export function Modal({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}) {
  const element=useRef<HTMLDialogElement>(null)
  useLayoutEffect(()=>{element.current?.showModal()},[])
  return <dialog ref={element} onCancel={e=>{e.preventDefault();onClose()}} aria-label={title} className={'panel modal'+(title==='New board'?' board-modal':'')}>
    <div className="section-heading"><h2>{title}</h2><button type="button" aria-label="Close" className="icon-button" onClick={onClose}><X size={19}/></button></div>{children}
  </dialog>
}

function Multi({field,value,onChange}:{field:Field;value:Value;onChange:(v:Value)=>void}) {
  const [term,setTerm]=useState('')
  const [open,setOpen]=useState(false)
  const selected=Array.isArray(value)?value.filter((item):item is number=>typeof item==='number'):[]
  const matches=field.options?.filter(e=>e.label.toLowerCase().includes(term.toLowerCase()))||[]
  return <div className="picker">
    <Button type="button" variant="outline" aria-expanded={open} onClick={()=>setOpen(!open)}>{selected.length ? field.options?.filter(o=>selected.includes(Number(o.value))).map(o=>o.label).join(', ') : 'Select people or records'}</Button>
    {open && <div className="picker-options">
      <input aria-label={'Search '+(field.label||labels[field.key]||field.key)} placeholder="Search options…" value={term} onChange={e=>setTerm(e.target.value)}/>
      {matches.length?matches.map(o=><label className="check" key={o.value}><input type="checkbox" checked={selected.includes(Number(o.value))}
        onChange={e=>onChange(e.target.checked?[...selected,Number(o.value)].sort((a,b)=>a-b):selected.filter(v=>v!==Number(o.value)))}/>{o.label}</label>):<small>No matching options.</small>}
    </div>}
  </div>
}

function SinglePerson({field,value,onChange,id,error}:{field:Field;value:Value;onChange:(v:Value)=>void;id:string;error?:string}) {
  const [filter,setFilter]=useState('')
  return <div className="person-pick">
    <input aria-label={'Search '+labels[field.key]} placeholder="Search people…" value={filter} onChange={e=>setFilter(e.target.value)} />
    <select id={id} aria-label={labels[field.key]} aria-invalid={error?true:undefined} aria-describedby={error?id+'-error':undefined} value={String(value??'')} required={field.required} onChange={e=>onChange(e.target.value?Number(e.target.value):null)}>
      <option value="">Select a person</option>
      {field.options?.filter(o=>o.value===value||o.label.toLowerCase().includes(filter.toLowerCase())).map(o=><option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </div>
}

export function FieldEditor({field,value,onChange,error}:{field:Field;value:Value;onChange:(v:Value)=>void;error?:string}) {
  const label=field.label||labels[field.key]||field.key
  const id=useId()
  const bytes=4096-new TextEncoder().encode(String(value??'')).length
  const legacyMaturity=field.key==='maturity'&&value===0
  const validation={ 'aria-invalid':error?true:undefined, 'aria-describedby':error?id+'-error':undefined }
  if(field.kind==='boolean') return <label className="check"><input type="checkbox" checked={!!value} onChange={e=>onChange(e.target.checked)}/>{label}</label>
  return <div data-field={field.key} className={'form-field '+(field.kind==='notes'?'wide':'')}>
    <label htmlFor={field.kind==='many'?undefined:id}>{label}{field.required?' *':''}</label>
    {field.kind==='many'?<Multi field={field} value={value} onChange={onChange}/>:
    field.key.endsWith('_id')&&field.options?<SinglePerson id={id} error={error} field={field} value={value} onChange={onChange}/>:
    field.options?<select id={id} {...validation} required={field.required} value={legacyMaturity?'legacy':String(value??'')} onChange={e=>onChange(e.target.value ? (field.numeric?Number(e.target.value):e.target.value) : null)}>
      <option value="">Select {label.toLowerCase()}</option>
      {legacyMaturity&&<option value="legacy" disabled>Select a new value</option>}
      {field.options.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select>:
    field.kind==='notes'?<><textarea id={id} {...validation} rows={4} value={String(value??'')} onChange={e=>onChange(e.target.value||null)}/>
      {field.help && <small className={bytes<0?'negative':''}>{bytes.toLocaleString()} UTF-8 bytes remaining</small>}</>:
    <input id={id} {...validation} required={field.required} type={field.kind||'text'} max={field.max} min={field.kind==='number'?0:undefined} step={field.kind==='number'?1:undefined}
      pattern={field.key==='identifier'?'SRC[0-9]{5}[A-Z]?':field.kind==='url'?'[Hh][Tt][Tt][Pp][Ss]?://.+':undefined} placeholder={field.key==='identifier'?'SRC00123A':undefined}
      value={String(value??'')} onChange={e=>onChange(e.target.value===''?null:field.kind==='number'?Number(e.target.value):e.target.value)}/>}
    {field.help&&field.kind!=='notes'&&<small>{field.help}</small>}
    {legacyMaturity&&<small>Stored maturity is 0 (legacy).</small>}
    {error&&<small id={id+'-error'} className="negative" role="alert">{error}</small>}
  </div>
}

export type FieldGroup = {title:string; fields:Field[]; reviews?:FieldGroup[]}

export function Editor({fields=[],groups,submitLabel,initial,onSave,onCancel,creating=false}:{fields?:Field[];groups?:FieldGroup[];submitLabel?:string;initial:Values;onSave:(edit:Edit)=>Promise<void>;onCancel:()=>void;creating?:boolean}) {
  const [draft,setDraft]=useState(initial)
  const [baseline,setBaseline]=useState(initial)
  const [error,setError]=useState('')
  const [invalid,setInvalid]=useState<Record<string,string>>({})
  const [conflicts,setConflicts]=useState<Record<string,{current:unknown;proposed:unknown}>>({})
  const [busy,setBusy]=useState(false)
  const changes=Object.fromEntries(Object.entries(draft).filter(([key,v])=>JSON.stringify(baseline[key])!==JSON.stringify(v)))
  const dirty=Object.keys(changes).length>0
  useLayoutEffect(()=>{
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
  function submit(e:FormEvent<HTMLFormElement>){
    e.preventDefault()
    const notes = [...fields,...(groups?.flatMap(group=>group.fields)||[])].find(field=>field.key==='notes'&&field.help)
    if(notes&&new TextEncoder().encode(String(draft.notes??'')).length>4096){
      setInvalid(current=>({...current,notes:'Notes must fit within 4096 UTF-8 bytes.'}))
      e.currentTarget.querySelector('textarea')?.focus()
      return
    }
    void save()
  }
  function fieldGrid(items:Field[]) {
    return <div className="form-grid">{items.map(field=>{
      const value=draft[field.key]??null
      function change(value:Value) {
        setDraft(current=>({...current,[field.key]:value}))
        setInvalid(current=>({...current,[field.key]:''}))
        setConflicts({})
      }
      return field.render?<div key={field.key} className={field.wide?'wide':undefined}>{field.render(value,change,draft,invalid[field.key])}</div>:
        <FieldEditor key={field.key} field={field} value={value} error={invalid[field.key]} onChange={change}/>
    })}</div>
  }
  return <form className={'editor'+(groups?' grouped-editor':'')} onSubmit={submit} onInvalid={event=>{
    const input=event.target as HTMLInputElement
    const key=input.closest<HTMLElement>('[data-field]')?.dataset.field
    if(!key)return
    const message=input.validity.valueMissing&&input.type==='date'?'Enter a review date.':
      input.type==='url'?'Enter a valid HTTP or HTTPS URL.':input.validationMessage
    setInvalid(current=>({...current,[key]:message}))
  }}>
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
    {groups?groups.map(group=><section className="create-section" key={group.title}>
      <h3>{group.title}</h3>
      {group.reviews?<div className="review-inputs">{group.reviews.map(review=><fieldset key={review.title}>
        <legend>{review.title}</legend>{fieldGrid(review.fields)}
      </fieldset>)}</div>:fieldGrid(group.fields)}
    </section>):fieldGrid(fields)}
    <div className="form-actions"><Button type="button" variant="outline" onClick={()=>{if(!dirty||window.confirm('Discard unsaved changes?'))onCancel()}}>Cancel</Button>
      <Button disabled={busy||(!dirty&&!creating)}>{busy?'Saving…':creating?(submitLabel||'Create record'):'Save changes'}</Button></div>
  </form>
}
