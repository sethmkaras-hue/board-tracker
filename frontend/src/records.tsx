import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef, type VisibilityState } from '@tanstack/react-table'
import { ArrowDown, ArrowLeft, ArrowUp, ChevronDown, ChevronLeft, ChevronRight, CircuitBoard, Download, ExternalLink, Filter, Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { api, displayDate, show, useData, type Board, type Page, type Parent, type Person, type Program, type Review, type Metrics } from './api'
import { Empty, Failure, Loading, PageHeading, useTracker } from './shared'
import { Button } from './components/ui/button'
import { Badge, BarChart, Recent } from './dashboard'
import { checks, labels, levels, reviews, states, tools, types } from './fields'
import { choices, Editor, Modal, type Edit, type Field, type FieldGroup, type Values, type Value } from './forms'
import { Timeline } from './operations'
import { ReviewTimeline } from './review-timeline'

const boardKeys=['identifier','active','schematic_ri_id','layout_ri_id','board_ri_ids','program_ids','board_type','complexity','reuse_level','maturity','schematic_tool','layout_tool','components_status','aras_board_url','aras_export_url','overview_url','notes']
const programKeys=['name','manager_ids','deputy_ids','epm_id','notes']
const parentsFields:Field[]=[{key:'name',required:true},{key:'quantity',required:true,kind:'number'},{key:'url',kind:'url'},{key:'notes',kind:'notes'}]
const reviewFields:Field[]=[{key:'state',label:'State',required:true,options:choices(states)},{key:'date',kind:'date'},{key:'url',kind:'url',label:'Review hyperlink'}]
function selectValues(record:object, keys:string[]):Values {
  return Object.fromEntries(keys.map(key=>[key,(record as Values)[key]??null]))
}
function useFields() {
  const {people,programs}=useTracker()
  const directory=people.map(p=>({value:p.id,label:p.display_name+' · '+p.username}))
  const identity:Field[]=[{key:'identifier',required:true,help:'Format SRC00123 with an optional uppercase revision letter.'},{key:'active',kind:'boolean'}]
  const ownership:Field[]=[{key:'schematic_ri_id',required:true,options:directory},{key:'layout_ri_id',options:directory},{key:'board_ri_ids',kind:'many',options:directory}]
  const classification:Field[]=[
    {key:'board_type',options:choices(types)},{key:'complexity',options:choices(levels)},{key:'reuse_level',options:choices(levels)},
    {key:'maturity',options:choices([1,2,3,4]),numeric:true},{key:'schematic_tool',options:choices(tools)},
    {key:'layout_tool',options:choices(tools)},{key:'components_status',options:choices(checks)},
  ]
  const docs:Field[]=['aras_board_url','aras_export_url','overview_url'].map(key=>({key,kind:'url'}))
  const programLink:Field={key:'program_ids',kind:'many',options:programs.map(p=>({value:p.id,label:p.name}))}
  const notes:Field={key:'notes',kind:'notes',help:'UTF-8 capacity'}
  const program:Field[]=[{key:'name',required:true},{key:'manager_ids',kind:'many',options:directory},{key:'deputy_ids',kind:'many',options:directory},{key:'epm_id',options:directory},{key:'notes',kind:'notes'}]
  return {identity,ownership,classification,docs,programLink,notes,program}
}
function name(people:Person[],id:number|null) {return people.find(p=>p.id===id)?.display_name||'—'}
export function BoardCreate({onClose,onSaved}:{onClose:()=>void;onSaved:()=>void}) {
  const fields=useFields()
  const navigate=useNavigate()
  const {toast}=useTracker()
  const dateField:Field={key:'date',kind:'date',required:true,label:'Review date'}
  const groups:FieldGroup[]=[
    {title:'Board identification',fields:[...fields.identity,...fields.ownership,fields.classification[0]]},
    {title:'Technical information',fields:fields.classification.slice(1)},
    {title:'Reviews',fields:[],reviews:reviews.map(kind=>({
      title:kind,
      fields:[dateField,reviewFields[0],reviewFields[2]].map(field=>({...field,key:kind+'.'+field.key})),
    }))},
    {title:'Additional information',fields:[...fields.docs,fields.programLink,fields.notes]},
  ]
  const initial=Object.fromEntries(reviews.map(kind=>[kind+'.state','Not Started']))
  return <Modal title="New board" onClose={()=>{if(window.confirm('Close the new board form?'))onClose()}}>
    <p className="muted create-guidance">Fields marked * are required.</p>
    <Editor groups={groups} initial={{...initial,active:true}} creating submitLabel="Create board" onCancel={onClose} onSave={async ({changes})=>{
      const boardFields=Object.fromEntries(Object.entries(changes).filter(([key])=>!key.includes('.')))
      const reviewData=Object.fromEntries(reviews.map(kind=>[kind,{
        date:changes[kind+'.date'],state:changes[kind+'.state'],url:changes[kind+'.url']??null,
      }]))
      const board=await api<Board>('/boards','POST',{...boardFields,reviews:reviewData})
      toast('Board created');onSaved();onClose();navigate('/boards/'+board.id)
    }}/>
  </Modal>
}

export function Boards() {
  const {people,programs,timezone,toast}=useTracker()
  const [params,setParams]=useSearchParams()
  const q=params.get('q')||''
  const [term,setTerm]=useState(q)
  const [filters,setFilters]=useState(false)
  const [save,setSave]=useState(false)
  const [saveError,setSaveError]=useState('')
  const [visible,setVisible]=useState<VisibilityState>({created_at:false})
  const query=new URLSearchParams(params)
  query.delete('new')
  if(!query.has('tz'))query.set('tz',timezone)
  const {data,error,reload}=useData<Page<Board>>('/boards?'+query)
  const views=useData<{id:number;name:string;query:string}[]>('/views')
  const parentOptions=useData<string[]>('/parents/options')
  const fields=useFields()
  useEffect(()=>setTerm(q),[q])
  useEffect(()=>{
    if(term===q)return
    const timer=setTimeout(()=>setParams(prev=>{
      const next=new URLSearchParams(prev);term?next.set('q',term):next.delete('q');next.delete('page');return next
    },{replace:true}),320)
    return ()=>clearTimeout(timer)
  },[term,q,setParams])
  function change(key:string,values:string[]) {
    setParams(prev=>{
      const next=new URLSearchParams(prev)
      next.delete(key)
      for(const value of values.filter(Boolean))next.append(key,value)
      if(key!=='page'&&key!=='new')next.delete('page')
      if(key.endsWith('_from')||key.endsWith('_to'))next.set('tz',next.get('tz')||timezone)
      return next
    })
  }
  const columns:ColumnDef<Board>[]=[
    {accessorKey:'identifier',header:'Board identifier',cell:({row})=><Link className="board-link" to={'/boards/'+row.original.id}><CircuitBoard size={16}/>{row.original.identifier}</Link>},
    {accessorKey:'active',header:'Status',cell:({row})=><Badge active={row.original.active}/>},
    {accessorKey:'board_type',header:'Type',cell:({getValue})=>show(getValue())},
    {accessorKey:'schematic_ri_id',header:'Schematic RI',enableSorting:false,cell:({row})=>name(people,row.original.schematic_ri_id)},
    {accessorKey:'complexity',header:'Complexity',cell:({getValue})=>show(getValue())},
    {accessorKey:'maturity',header:'Maturity',cell:({getValue})=>getValue()===0?'0 (legacy)':show(getValue())},
    ...(['created_at','updated_at'] as const).map(key=>({accessorKey:key,header:labels[key],cell:({row}:{row:{original:Board}})=>displayDate(row.original[key],timezone)})),
  ]
  const sort=params.get('sort')||'identifier'
  const page=Number(params.get('page')||1)
  const table=useReactTable({data:data?.items||[],columns,getCoreRowModel:getCoreRowModel(),manualSorting:true,manualPagination:true,
    state:{columnVisibility:visible,sorting:[{id:sort.replace(/^-/,'') ,desc:sort.startsWith('-')}]},onColumnVisibilityChange:setVisible})
  const selections:Field[]=[{key:'active',options:[{value:'true',label:'Active'},{value:'false',label:'Inactive'}]},...fields.ownership,...fields.classification,
    {key:'program_ids',options:programs.map(p=>({value:p.id,label:p.name}))},{key:'review_kind',options:choices(reviews)},
    {key:'review_state',options:choices(states)},{key:'verification',options:choices(states)},
    {key:'parent',options:choices([...new Set([...(parentOptions.data||[]),...params.getAll('parent')])])}]
  const filterLabels:Record<string,string>={review_kind:'Review type',review_state:'Review state',verification:'Verification state',parent:'Parent system'}
  const filterCount=[...params.keys()].filter(k=>!['page','sort','q','new','tz'].includes(k)).length
  async function deleteSaved(id:number) {
    if(!window.confirm('Remove this saved view?'))return
    try{await api('/views/'+id,'DELETE');views.reload();toast('Saved view removed')}catch(e){toast((e as Error).message)}
  }
  return <>
    <PageHeading title="Boards" description="Search and manage circuit card design records." action={<Button onClick={()=>change('new',['true'])}><Plus size={17}/> New board</Button>}/>
    {params.has('new')&&<BoardCreate onClose={()=>change('new',[])} onSaved={reload}/>}
    <section className="panel">
      <div className="toolbar">
        <label className="search-field"><Search size={16}/><input aria-label="Board identifier search" placeholder="Search by board identifier" value={term} onChange={e=>setTerm(e.target.value)}/></label>
        <Button variant="outline" onClick={()=>setFilters(!filters)} aria-expanded={filters}><Filter size={15}/> Filters{filterCount?' ('+filterCount+')':''}</Button>
        <details className="dropdown"><summary>Columns <ChevronDown size={14}/></summary><div>{table.getAllLeafColumns().map(c=><label className="check" key={c.id}><input type="checkbox" checked={c.getIsVisible()} onChange={c.getToggleVisibilityHandler()}/>{String(c.columnDef.header)}</label>)}</div></details>
        <details className="dropdown"><summary><Download size={15}/> Export</summary><div>{['xlsx','csv'].map(fmt=><a key={fmt} href={'/api/export/boards?'+query+'&fmt='+fmt}>{fmt==='xlsx'?'Excel (.xlsx)':'CSV (.csv)'}</a>)}</div></details>
        <details className="dropdown"><summary>Saved views <ChevronDown size={14}/></summary><div>
          {views.error&&<small>{views.error}</small>}
          {views.data?.map(view=><div className="view-row" key={view.id}><button onClick={()=>setParams(view.query)}>{view.name}</button><button className="icon-button" aria-label={'Delete '+view.name} onClick={()=>void deleteSaved(view.id)}><Trash2 size={14}/></button></div>)}
          <button onClick={()=>{setSaveError('');setSave(true)}}>Save current view</button></div></details>
      </div>
      {save&&<Modal title="Save personal view" onClose={()=>setSave(false)}><form className="editor" onSubmit={async e=>{
        e.preventDefault();const form=new FormData(e.currentTarget);const saved=new URLSearchParams(params);saved.delete('page')
        try{await api('/views','POST',{name:form.get('name'),query:saved.toString()});views.reload();setSave(false);toast('View saved')}catch(e){setSaveError((e as Error).message)}
      }}>{saveError&&<Failure message={saveError}/>}<label>View name<input name="name" maxLength={120} required/></label><div className="form-actions"><Button>Save view</Button></div></form></Modal>}
      {filters&&<div className="filters"><div className="form-grid">
        {selections.map(f=><fieldset key={f.key} className="filter-group"><legend>{filterLabels[f.key]||labels[f.key]}</legend>
          <select multiple aria-label={filterLabels[f.key]||labels[f.key]} value={params.getAll(f.key)} onChange={e=>change(f.key,Array.from(e.target.selectedOptions,o=>o.value))}>
            {f.options?.map(o=><option value={o.value} key={o.value}>{o.label}</option>)}</select></fieldset>)}
        {Object.entries({created:'Creation date',updated:'Last modification date',review:'Current review date',activity:'Activity date'}).map(([key,label])=><fieldset className="filter-group" key={key}>
          <legend>{label}</legend><div className="date-pair">{['from','to'].map(side=><label key={side}>{side==='from'?'From':'Through'}<input type="date" value={params.get(key+'_'+side)||''} onChange={e=>change(key+'_'+side,[e.target.value])}/></label>)}</div>
        </fieldset>)}
      </div>{parentOptions.error&&<Failure message={parentOptions.error}/>}<small>Use Ctrl or Command to select multiple values. Date ranges include both selected dates.</small></div>}
      {(q||filterCount>0)&&<div className="filter-summary"><span>{filterCount} filter values applied</span><Button variant="ghost" onClick={()=>{setTerm('');setParams({})}}>Clear all filters</Button></div>}
      {error?<Failure message={error}/>:!data?<Loading/>:data.items.length?<div className="table-scroll"><table>
        <thead>{table.getHeaderGroups().map(group=><tr key={group.id}>{group.headers.map(h=><th key={h.id} aria-sort={h.column.getIsSorted()==='asc'?'ascending':h.column.getIsSorted()==='desc'?'descending':undefined}>
          {h.column.getCanSort()?<button className="sort" onClick={()=>change('sort',[sort===h.column.id?'-'+h.column.id:h.column.id])}>{flexRender(h.column.columnDef.header,h.getContext())}{h.column.getIsSorted()==='asc'?<ArrowUp size={13}/>:h.column.getIsSorted()==='desc'?<ArrowDown size={13}/>:null}</button>:flexRender(h.column.columnDef.header,h.getContext())}</th>)}</tr>)}</thead>
        <tbody>{table.getRowModel().rows.map(row=><tr key={row.original.id}>{row.getVisibleCells().map(c=><td key={c.id}>{flexRender(c.column.columnDef.cell,c.getContext())}</td>)}</tr>)}</tbody>
      </table></div>:<Empty>No boards match this view. Try clearing the filters or creating a board.</Empty>}
      {data&&<div className="pagination"><span>{data.total} {data.total===1?'board':'boards'} · Page {page} of {Math.max(1,Math.ceil(data.total/25))}</span>
        <Button variant="outline" aria-label="Previous page" disabled={page<=1} onClick={()=>change('page',[String(page-1)])}><ChevronLeft size={17}/></Button>
        <Button variant="outline" aria-label="Next page" disabled={page*25>=data.total} onClick={()=>change('page',[String(page+1)])}><ChevronRight size={17}/></Button>
      </div>}
    </section>
  </>
}

function RecordSection({title,fields,record,save,readOnly=false,collapsible=false}:{title:string;fields:Field[];record:object;save:(e:Edit)=>Promise<void>;readOnly?:boolean;collapsible?:boolean}) {
  const [editing,setEditing]=useState(false)
  const {people,programs}=useTracker()
  const values=selectValues(record,fields.map(f=>f.key))
  function render(key:string,value:Value) {
    if(key==='program_ids'&&Array.isArray(value)&&value.length)return value.map(id=><Link key={id} to={'/programs/'+id}>{programs.find(p=>p.id===id)?.name||id}</Link>)
    if(key.endsWith('_id'))return name(people,value as number|null)
    if(key.endsWith('_ids')&&Array.isArray(value))return value.map(id=>name(people,id)).join(', ')||'—'
    if((key.endsWith('_url')||key==='url')&&typeof value==='string'&&/^https?:\/\//i.test(value))return <a href={value} target="_blank" rel="noreferrer">Open link <ExternalLink size={13}/></a>
    if(key==='maturity'&&value===0)return '0 (legacy)'
    if(key==='active')return <Badge active={!!value}/>
    return show(value)
  }
  const editButton=!editing&&!readOnly&&<Button variant="ghost" onClick={()=>setEditing(true)}><Pencil size={15}/> Edit</Button>
  const content=editing?<Editor fields={fields} initial={values} onCancel={()=>setEditing(false)} onSave={async e=>{await save(e);setEditing(false)}}/>:
    <dl>{Object.entries(values).map(([key,value])=><div className={key==='notes'?'wide':''} key={key}><dt>{fields.find(field=>field.key===key)?.label||labels[key]||key}</dt><dd>{render(key,value)}</dd></div>)}</dl>
  return <section className="panel record-section">
    {collapsible?<details className="collapsible"><summary><h2>{title}</h2><ChevronDown size={16}/></summary>
      {editButton&&<div className="collapsible-actions">{editButton}</div>}{content}
    </details>:<><div className="section-heading"><h2>{title}</h2>{editButton}</div>{content}</>}
  </section>
}

export function BoardDetail() {
  const {id}=useParams()
  const {data:board,error,reload}=useData<Board>('/boards/'+id)
  const {person,people,timezone,toast}=useTracker()
  const fields=useFields()
  const [parent,setParent]=useState(false)
  if(error)return <Failure message={error}/>
  if(!board)return <Loading/>
  const locked=!!board.deleted_at
  const path='/boards/'+id
  async function persist(endpoint:string,method:string,data?:unknown,message='Board updated') {
    await api(path+endpoint,method,data);toast(message);reload()
  }
  function confirmAction(endpoint:string,method:string,message:string,data?:unknown) {
    if(window.confirm(message))void persist(endpoint,method,data).catch(e=>toast(e.message))
  }
  const sections:[string,Field[]][]=[
    ['Overview',[...fields.identity,fields.notes]],['Responsible individuals',fields.ownership],['Engineering attributes',fields.classification],
    ['Design documentation',fields.docs],['Programs',[fields.programLink]],
  ]
  return <>
    <Link className="back" to="/boards"><ArrowLeft size={15}/> Boards</Link>
    <PageHeading title={board.identifier} description={'Last modified '+displayDate(board.updated_at,timezone)+' by '+name(people,board.updated_by)}
      action={<div className="header-actions">{locked?<span className="badge inactive">Deleted</span>:<Badge active={board.active}/>}
        {person.admin&&<Button variant={locked?'outline':'danger'} onClick={()=>confirmAction('/lifecycle','POST',locked?'Restore this board?':'Soft-delete this board?',{action:locked?'restore':'delete'})}>{locked?'Restore board':'Delete board'}</Button>}</div>}/>
    <div className="record-meta">Created {displayDate(board.created_at,timezone)} by {name(people,board.created_by)}
      {!!board.revisions?.length&&<> · Related revisions {board.revisions.map(r=><Link key={r.id} to={'/boards/'+r.id}>{r.identifier}</Link>)}</>}
    </div>
    <ReviewTimeline reviews={board.reviews} timezone={timezone}/>
    <div className="chart-grid">{sections.map(([title,sectionFields])=><RecordSection title={title} fields={sectionFields} record={selectValues(board,boardKeys)} save={e=>persist('','PATCH',e)} readOnly={locked} key={title}/>)}</div>
    <section className="panel record-section separate"><div className="section-heading"><h2>Parent systems</h2>{!locked&&<Button variant="outline" onClick={()=>setParent(true)}><Plus size={15}/> Add parent system</Button>}</div>
      {parent&&<Editor fields={parentsFields} initial={{quantity:0}} creating onCancel={()=>setParent(false)} onSave={async e=>{await persist('/parents','POST',e.changes);setParent(false)}}/>}
      {board.parents.length?<div className="chart-grid">{board.parents.map((p:Parent)=><div key={p.id}>
        <RecordSection title={p.name} fields={parentsFields} record={p} readOnly={locked} save={e=>persist('/parents/'+p.id,'PATCH',e)}/>
        {!locked&&<Button variant="ghost" onClick={()=>confirmAction('/parents/'+p.id,'DELETE','Remove this parent system relationship?')}><Trash2 size={15}/> Remove relationship</Button>}
      </div>)}</div>:!parent&&<Empty>No parent systems are linked.</Empty>}
    </section>
    <section className="panel record-section separate"><div className="section-heading"><h2>Reviews and verification</h2></div>
      <div className="chart-grid">{reviews.map(kind=>board.reviews.find(r=>r.kind===kind)).filter((r):r is Review=>!!r).map(r=><RecordSection key={r.id} title={r.kind} fields={reviewFields} record={r} readOnly={locked} save={e=>persist('/reviews/'+encodeURIComponent(r.kind),'PUT',e)}/>)}</div>
    </section>
    <Timeline boardId={board.id} version={board.updated_at}/>
  </>
}

export function Programs() {
  const {data,error,reload}=useData<Program[]>('/programs')
  const {people,toast,refresh}=useTracker()
  const [creating,setCreating]=useState(false)
  const {program}=useFields()
  const navigate=useNavigate()
  return <>
    <PageHeading title="Programs" description="Manage program ownership and linked circuit card designs." action={<Button onClick={()=>setCreating(true)}><Plus size={17}/> New program</Button>}/>
    {creating&&<Modal title="New program" onClose={()=>{if(window.confirm('Close the new program form?'))setCreating(false)}}>
      <Editor fields={program} initial={{manager_ids:[],deputy_ids:[]}} creating onCancel={()=>setCreating(false)} onSave={async e=>{
        const row=await api<Program>('/programs','POST',e.changes);toast('Program created');reload();refresh();navigate('/programs/'+row.id)
      }}/>
    </Modal>}
    <section className="panel">{error?<Failure message={error}/>:!data?<Loading/>:data.length?<div className="table-scroll"><table><thead><tr><th>Program name</th><th>Program managers</th><th>Deputy managers</th><th>EPM</th></tr></thead><tbody>
      {data.map(row=><tr key={row.id}><td><Link to={'/programs/'+row.id}>{row.name}</Link></td><td>{row.manager_ids.map(p=>name(people,p)).join(', ')||'—'}</td><td>{row.deputy_ids.map(p=>name(people,p)).join(', ')||'—'}</td><td>{name(people,row.epm_id)}</td></tr>)}
    </tbody></table></div>:<Empty>Create a program to associate it with boards.</Empty>}</section>
  </>
}
export function ProgramDetail() {
  const {id}=useParams()
  const {data,error,reload}=useData<Program&{boards:Board[];metrics:Metrics}>('/programs/'+id)
  const {program}=useFields()
  const {toast,refresh}=useTracker()
  if(error)return <Failure message={error}/>
  if(!data)return <Loading/>
  return <><Link className="back" to="/programs"><ArrowLeft size={15}/> Programs</Link>
    <PageHeading title={data.name} description={data.boards.length+' associated boards'}/>
    <section className="panel record-section"><div className="section-heading"><h2>Associated boards</h2></div>
      {data.boards.length?<ul className="board-list">{data.boards.map(b=><li key={b.id}><Link to={'/boards/'+b.id}>{b.identifier}</Link><Badge active={b.active}/></li>)}</ul>:<Empty>No boards are associated with this program.</Empty>}
    </section>
    <div className="separate"><RecordSection collapsible key={id} title="Program details" fields={program} record={selectValues(data,programKeys)} save={async edit=>{
      await api('/programs/'+id,'PATCH',edit);toast('Program updated');reload();refresh()
    }}/></div>
    <div className="chart-grid separate">
      <BarChart title="Board maturity distribution" items={data.metrics.maturity} filter="maturity" scope={data.id}/>
      <BarChart title="Review states" items={data.metrics.reviews} filter="review_state" state scope={data.id}/>
      <BarChart title="Verification states" items={data.metrics.verification} filter="verification" state scope={data.id}/>
    </div>
    <Recent boards={data.boards.slice(0,8)} all={'/boards?program_ids='+id+'&sort=-updated_at'}/>
  </>
}
