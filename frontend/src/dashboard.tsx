import { ArrowRight, Boxes, CircuitBoard, Clock3, Plus, UserRound } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { Link } from 'react-router-dom'
import { displayDate, useData, type Board, type DashboardData } from './api'
import { Empty, Failure, Loading, PageHeading, useTracker } from './shared'
import { Button } from './components/ui/button'

const colors=['#6759ed','#8c7df5','#afa4fc','#c8bffd','#ded8ff','#eae6fd','#d8dce7']
export const stateColors:Record<string,string>={'Complete':'#22a77a','In-Review':'#8272ef','Scheduled':'#e5a049','Working Action Items':'#4eabe0','Not Started':'#acb6c9'}
export function Badge({active}:{active:boolean}) {return <span className={'badge '+(active?'active':'inactive')}><i/>{active?'Active':'Inactive'}</span>}
export function BarChart({title,items,filter,state=false,scope}:{title:string;items:Record<string,number>;filter:string;state?:boolean;scope?:number}) {
  const {programs}=useTracker()
  const entries=Object.entries(items)
  const maximum=Math.max(1,...entries.map(e=>e[1]))
  function href(label:string) {
    const value=filter==='program_ids'?programs.find(p=>p.name===label)?.id:label
    const params=new URLSearchParams()
    if(scope)params.set('program_ids',String(scope))
    if(value!==undefined)params.set(filter,String(value))
    if(filter==='review_state')for(const kind of ['Functional Overview Review','Detailed Design Review','Schematic Review','Artwork Review'])params.append('review_kind',kind)
    return '/boards?'+params
  }
  return <section className="panel chart"><h2>{title}</h2>
    {entries.length?<div className="bar-list">{entries.map(([name,count],i)=><div className="bar-row" key={name}>
      {name==='Unspecified'||(filter==='maturity'&&name==='0')?<span>{name==='0'?'0 (legacy)':name}</span>:<Link to={href(name)}>{name}</Link>}
      <div className="bar-track"><div style={{width:(count/maximum*100)+'%',background:state?stateColors[name]:colors[i%colors.length]}}/></div><strong>{count}</strong>
    </div>)}</div>:<Empty>No records to chart.</Empty>}
  </section>
}
function TypeChart({items}:{items:Record<string,number>}) {
  const data=Object.entries(items).map(([name,value])=>({name,value}))
  return <section className="panel chart"><h2>Boards by type</h2>
    {data.length?<div className="donut">
      <div className="donut-visual"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={data} dataKey="value" nameKey="name" innerRadius="66%" outerRadius="92%" paddingAngle={3} stroke="none" isAnimationActive={false}>
        {data.map(item=><Cell key={item.name} fill={colors[data.indexOf(item)%colors.length]}/>)}
      </Pie><Tooltip/></PieChart></ResponsiveContainer><div className="donut-title"><strong>{data.reduce((sum,i)=>sum+i.value,0)}</strong><small>Total boards</small></div></div>
      <div className="legend">{data.map(({name,value},i)=><div key={name}><i style={{background:colors[i%colors.length]}}/>{name==='Unspecified'?<span>{name}</span>:<Link to={'/boards?'+new URLSearchParams({board_type:name})}>{name}</Link>}<strong>{value}</strong></div>)}</div>
    </div>:<Empty>No board types to chart.</Empty>}
  </section>
}
export function Recent({boards,title='Recently modified boards',all='/boards?sort=-updated_at'}:{boards:Board[];title?:string;all?:string}) {
  const {timezone,people}=useTracker()
  return <section className="panel recent"><div className="section-heading"><div><h2>{title}</h2><p>Latest updates across tracked designs</p></div><Button variant="outline" asChild><Link to={all}>View boards <ArrowRight size={15}/></Link></Button></div>
    {boards.length?<div className="table-scroll"><table><thead><tr><th>Board identifier</th><th>Status</th><th>Type</th><th>Schematic RI</th><th>Last modified</th></tr></thead>
      <tbody>{boards.map(b=><tr key={b.id}><td><Link className="board-link" to={'/boards/'+b.id}><CircuitBoard size={16}/>{b.identifier}</Link></td><td><Badge active={b.active}/></td><td>{b.board_type||'—'}</td><td>{people.find(p=>p.id===b.schematic_ri_id)?.display_name||'—'}</td><td>{displayDate(b.updated_at,timezone)}</td></tr>)}</tbody>
    </table></div>:<Empty>Create a board to see activity here.</Empty>}
  </section>
}
export function Dashboard() {
  const {data,error}=useData<DashboardData>('/dashboard')
  return <>
    <PageHeading title="Engineering dashboard" description="Track circuit card designs, reviews, and program activity." action={<Button asChild><Link to="/boards?new=true"><Plus size={17}/> New board</Link></Button>}/>
    {error?<Failure message={error}/>:!data?<Loading/>:<>
      <div className="metrics">
        {[
          {label:'Active boards',value:data.active,description:'Currently active designs',to:'active=true',Icon:CircuitBoard,color:'purple'},
          {label:'Inactive boards',value:data.inactive,description:'Inactive designs',to:'active=false',Icon:Boxes,color:'slate'},
          {label:'Assigned to me',value:data.assigned,description:'Across all RI roles',to:'assigned=me',Icon:UserRound,color:'mint'},
          {label:'Needs attention',value:data.stale,description:'No updates in 30 days',to:'stale=true',Icon:Clock3,color:'amber'},
        ].map(({label,value,description,to,Icon,color})=><Link className="panel metric" to={'/boards?'+to} key={label}><div className="metric-top"><span>{label}</span><span className={'metric-icon '+color}><Icon size={18}/></span></div><strong>{value}</strong><small>{description}</small></Link>)}
      </div>
      <div className="chart-grid">
        <TypeChart items={data.types}/>
        <BarChart title="Review state distribution" items={data.reviews} filter="review_state" state/>
      </div>
      <Recent boards={data.recent}/>
      <div className="chart-grid secondary-charts">
        <BarChart title="Boards by maturity" items={data.maturity} filter="maturity"/>
        <BarChart title="Boards by complexity" items={data.complexity} filter="complexity"/>
        <BarChart title="Verification states" items={data.verification} filter="verification" state/>
        <BarChart title="Boards by program" items={data.programs} filter="program_ids"/>
      </div>
    </>}
  </>
}
