import { useId } from 'react'
import { allocationStatuses, type Person, type Review, type ReviewAssignmentInput } from './api'
import { Button } from './components/ui/button'
import { states } from './fields'
import { choices, FieldEditor, type Field, type Value } from './forms'

const dateFormatter = new Intl.DateTimeFormat('en-US', {month:'short',day:'numeric',year:'numeric',timeZone:'UTC'})
export const reviewDateLabel = (date:string) => dateFormatter.format(new Date(date))

export function automaticReviewStart(meeting:string) {
  const date = new Date(meeting)
  date.setUTCDate(date.getUTCDate()-7)
  return date.getUTCFullYear() < 1 ? '0001-01-01' : date.toISOString().slice(0,10)
}

export function allocationCounts(assignments:ReviewAssignmentInput[]) {
  const allocated = assignments.filter(item=>item.allocation_status==='Allocated').length
  return `${allocated} allocated · ${assignments.length-allocated} not allocated`
}

function reviewerAssignments(value:Value):ReviewAssignmentInput[] {
  return Array.isArray(value)?value.filter((item):item is ReviewAssignmentInput=>typeof item==='object'):[]
}

function ReviewStart({fieldKey,value,meeting,onChange,error}:{fieldKey:string;value:Value;meeting:Value;onChange:(value:Value)=>void;error?:string}) {
  return <div className="review-form-control">
    <FieldEditor field={{key:fieldKey,label:'Review start date override',kind:'date',max:typeof meeting==='string'?meeting:undefined}}
      value={value} onChange={onChange} error={error}/>
    <small>{typeof value==='string'?`Manual start · ${reviewDateLabel(value)}`:
      typeof meeting==='string'?`Automatic start · ${reviewDateLabel(automaticReviewStart(meeting))}`:'Automatic start appears when a meeting date is set.'}</small>
    {value!==null&&<Button type="button" variant="ghost" onClick={()=>onChange(null)}>Restore automatic start</Button>}
  </div>
}

function ReviewerEditor({value,people,onChange}:{value:Value;people:Person[];onChange:(value:Value)=>void}) {
  const id = useId()
  const assignments = reviewerAssignments(value)
  const directory = people.map(person=>({value:person.id,label:person.display_name+' · '+person.username}))
  // Existing assignments remain selectable while the directory is loading.
  for(const item of assignments)if(!directory.some(person=>person.value===item.reviewer_id)){
    directory.push({value:item.reviewer_id,label:`Reviewer ${item.reviewer_id}`})
  }
  return <div className="review-form-control">
    <FieldEditor field={{key:'assignments',label:'Reviewers',kind:'many',options:directory}}
      value={assignments.map(item=>item.reviewer_id)} onChange={value=>{
        const ids = Array.isArray(value)?value.filter((item):item is number=>typeof item==='number'):[]
        onChange(ids.map<ReviewAssignmentInput>(reviewer_id=>assignments.find(item=>item.reviewer_id===reviewer_id)||
          {reviewer_id,allocation_status:'Not Allocated'}))
      }}/>
    {assignments.length>0&&<div className="reviewer-allocations">
      <small>{allocationCounts(assignments)} · Manually tracked</small>
      {assignments.map(item=>{
        const name=directory.find(person=>person.value===item.reviewer_id)?.label
        const inputId=id+'-'+item.reviewer_id
        return <div key={item.reviewer_id}>
          <label htmlFor={inputId}>{name}</label>
          <select id={inputId} aria-label={`Allocation for ${name}`} value={item.allocation_status}
            onChange={event=>{
              const status=allocationStatuses.find(status=>status===event.target.value)
              if(status)onChange(assignments.map(assignment=>assignment.reviewer_id===item.reviewer_id?
                {...assignment,allocation_status:status}:assignment))
            }}>
            {allocationStatuses.map(status=><option key={status}>{status}</option>)}
          </select>
        </div>
      })}
    </div>}
  </div>
}

export function reviewFields(people:Person[],prefix='',required=false):Field[] {
  return [
    {key:prefix+'date',label:'Review meeting date',kind:'date',required},
    {key:prefix+'review_start_date',label:'Review start date',render:(value,onChange,draft,error)=><ReviewStart
      fieldKey={prefix+'review_start_date'} error={error} value={value} meeting={draft[prefix+'date']??null} onChange={onChange}/>},
    {key:prefix+'state',label:'State',required:true,options:choices(states)},
    {key:prefix+'url',label:'Review hyperlink',kind:'url'},
    {key:prefix+'assignments',label:'Reviewers',wide:true,render:(value,onChange)=><ReviewerEditor value={value} people={people} onChange={onChange}/>},
  ]
}

export function reviewReadout(review:Review,key:string) {
  if(key==='date')return review.date?reviewDateLabel(review.date):'—'
  if(key==='review_start_date')return review.effective_review_start_date?
    `${reviewDateLabel(review.effective_review_start_date)} · ${review.review_start_date?'Manual override':'Automatic'}`:'—'
  if(key==='assignments')return review.assignments.length?<div className="reviewer-summary">
    <small>{allocationCounts(review.assignments)} · Manually tracked</small>
    <ul>{review.assignments.map(item=><li key={item.reviewer_id}>{item.reviewer_name} · {item.allocation_status}</li>)}</ul>
  </div>:'No reviewers assigned · 0 allocated · 0 not allocated'
  return undefined
}
