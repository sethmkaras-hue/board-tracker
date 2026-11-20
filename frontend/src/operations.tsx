import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, ChevronDown, ChevronLeft, ChevronRight, Download, ShieldCheck } from 'lucide-react'
import { api, displayDate, show, useData, type Event, type Page, type Person } from './api'
import { Empty, Failure, Loading, PageHeading, useTracker } from './shared'
import { Button } from './components/ui/button'
import { labels } from './fields'

export function Timeline({boardId,programId,version}:{boardId?:number;programId?:number;version?:string}) {
  const [page,setPage]=useState(1)
  const [expanded,setExpanded]=useState(false)
  const scope=new URLSearchParams()
  if(boardId)scope.set('board_id',String(boardId))
  if(programId)scope.set('program_id',String(programId))
  const params=new URLSearchParams(scope)
  params.set('page',String(page))
  if(version)params.set('v',version)
  const {data,error}=useData<Page<Event>>(expanded?'/activity?'+params:null,programId?30_000:undefined)
  return <section className="panel record-section separate">
    <details className="collapsible" onToggle={event=>setExpanded(event.currentTarget.open)}>
      <summary><h2>{boardId||programId?'Activity history':'Recorded changes'}</h2><ChevronDown size={16}/></summary>
    <div className="section-heading activity-actions"><details className="dropdown"><summary><Download size={16}/> Export</summary><div>
      {['xlsx','csv'].map(fmt=><a key={fmt} href={'/api/export/activity?'+new URLSearchParams({...Object.fromEntries(scope),fmt})}>{fmt==='xlsx'?'Excel (.xlsx)':'CSV (.csv)'}</a>)}
    </div></details></div>
    {error?<Failure message={error}/>:!data?<Loading/>:data.items.length?<div className="activity-scroll" tabIndex={0} role="region" aria-label="Activity log"><ol className="timeline">
      {data.items.map(event=><li key={event.id}><div className="timeline-title">
        <strong>{labels[event.field]||event.field}</strong><span className="badge">{event.action}</span>
        {!boardId&&event.board_id&&<Link to={'/boards/'+event.board_id}>{event.board_label}</Link>}
      </div><p>{show(event.previous)} <span className="muted">→</span> {show(event.value)}</p>
      <small>{event.username} · {displayDate(event.timestamp)}</small></li>)}
    </ol></div>:<Empty>No activity has been recorded.</Empty>}
    {data&&data.total>50&&<div className="pagination"><span>Page {page} of {Math.ceil(data.total/50)}</span>
      <Button variant="outline" aria-label="Previous page" disabled={page===1} onClick={()=>setPage(page-1)}><ChevronLeft size={16}/></Button>
      <Button variant="outline" aria-label="Next page" disabled={page*50>=data.total} onClick={()=>setPage(page+1)}><ChevronRight size={16}/></Button></div>}
    </details>
  </section>
}
export function ActivityPage(){return <><PageHeading title="Activity History" description="Review and export changes across the workspace."/><Timeline/></>}

type Digest={id:number;day:string;read:boolean;payload:{board_id:number;board:string;field:string;previous:unknown;value:unknown;username:string;timestamp:string}[]}
export function Notifications(){
  const {data,error,reload}=useData<Digest[]>('/notifications')
  const {toast}=useTracker()
  async function update(row:Digest){
    try{await api('/notifications/'+row.id,'PATCH',{read:!row.read});reload()}
    catch(e){toast((e as Error).message)}
  }
  return <><PageHeading title="Notifications" description="Daily digests for boards and programs you support."/>
    {error?<Failure message={error}/>:!data?<Loading/>:data.length?data.map(row=><section key={row.id} className="panel record-section separate">
      <div className="section-heading"><h2><Bell size={17}/> {row.day} {row.read?'':'· Unread'}</h2><Button variant="outline" onClick={()=>void update(row)}>Mark {row.read?'unread':'read'}</Button></div>
      <ol className="timeline">{row.payload.map((event,i)=><li key={i}><div className="timeline-title"><Link to={'/boards/'+event.board_id}>{event.board}</Link><strong>{labels[event.field]||event.field}</strong></div>
        <p>{show(event.previous)} → {show(event.value)}</p><small>{event.username} · {displayDate(event.timestamp)}</small></li>)}</ol>
    </section>):<section className="panel"><Empty>No digests yet. Changes to your assigned boards will appear here after processing.</Empty></section>}
  </>
}
type SystemStatus={database:string;ldap_configured:boolean;smtp_configured:boolean;backup:string;notification_timezone:string;cycles:{day:string;completed_at:string}[];failures:{id:number;day:string;person_id:number;attempts:number;status:string;error:string}[]}
export function Admin(){
  const {person,people,refresh,toast}=useTracker()
  const status=useData<SystemStatus>('/admin/status')
  const [error,setError]=useState('')
  async function privilege(row:Person){
    if(!window.confirm((row.admin?'Revoke':'Grant')+' administrator access for '+row.username+'?'))return
    try{await api('/admin/people/'+row.id,'PATCH',{grant:!row.admin});refresh();toast('Administrator access updated')}catch(e){setError((e as Error).message)}
  }
  return <><PageHeading title="Administration" description="Manage access, deleted records, and system operations."
    action={<Button variant="outline" asChild><Link to="/boards?deleted=true">View deleted boards</Link></Button>}/>
    {error&&<Failure message={error}/>}
    {status.error?<Failure message={status.error}/>:!status.data?<Loading/>:<div className="chart-grid">
      <section className="panel record-section"><div className="section-heading"><h2><ShieldCheck size={18}/> System status</h2></div>
        <dl>{Object.entries({Database:status.data.database,LDAP:status.data.ldap_configured?'Configured':'Missing configuration',SMTP:status.data.smtp_configured?'Configured':'Missing configuration',Backup:status.data.backup}).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      </section>
      <section className="panel record-section"><div className="section-heading"><h2>Notification settings</h2></div>
        <form className="editor" key={status.data.notification_timezone} onSubmit={async event=>{
          event.preventDefault();const form=new FormData(event.currentTarget)
          try{await api('/admin/settings','PUT',{timezone:form.get('timezone')});setError('');status.reload();toast('Notification timezone saved')}catch(e){setError((e as Error).message)}
        }}><label>Midnight timezone<input list="zones" required name="timezone" defaultValue={status.data.notification_timezone}/></label>
          <datalist id="zones">{['UTC',...Intl.supportedValuesOf('timeZone')].map(zone=><option key={zone} value={zone}/>)}</datalist>
          <div className="form-actions"><Button>Save timezone</Button></div>
        </form>
      </section>
      <section className="panel record-section"><div className="section-heading"><h2>Notification job history</h2></div>
        {status.data.cycles.length?<ul className="board-list">{status.data.cycles.map(row=><li key={row.day}>{row.day} · digest generation completed</li>)}</ul>:<Empty>No digest cycles have run.</Empty>}</section>
      <section className="panel record-section"><div className="section-heading"><h2>Failed delivery attempts</h2></div>
        {status.data.failures.length?<ul className="board-list">{status.data.failures.map(row=><li key={row.id}>{row.day} · {people.find(p=>p.id===row.person_id)?.username} · {row.attempts} attempts · {row.status} · {row.error}</li>)}</ul>:<Empty>No failed deliveries.</Empty>}</section>
    </div>}
    <section className="panel separate"><div className="section-heading"><h2>User directory</h2></div><div className="table-scroll"><table><thead><tr><th>Display name</th><th>Username</th><th>Email</th><th>Role</th><th>Access</th></tr></thead><tbody>
      {people.map(row=><tr key={row.id}><td>{row.display_name}</td><td>{row.username}</td><td>{row.email||'—'}</td><td>{row.admin?'Administrator':'Engineer'}</td>
        <td>{row.id!==person.id&&<Button variant="outline" onClick={()=>void privilege(row)}>{row.admin?'Revoke admin':'Grant admin'}</Button>}</td></tr>)}
    </tbody></table></div></section>
  </>
}
