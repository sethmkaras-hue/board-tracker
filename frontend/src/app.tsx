import { Component, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Activity, Bell, ChevronRight, CircuitBoard, FolderKanban, LayoutDashboard, LogOut, Menu, Moon, Search, ShieldCheck, Sun } from 'lucide-react'
import { api, ApiError, setSession, useData, type Person, type Program } from './api'
import { appName, appAcronym } from './branding'
import { Button } from './components/ui/button'
import { Dashboard } from './dashboard'
import { Boards, BoardDetail, Programs, ProgramDetail } from './records'
import { ActivityPage, Admin, Notifications } from './operations'
import { Failure, Loading, Tracker } from './shared'

class Boundary extends Component<{children:ReactNode},{failed:boolean}> {
  state = {failed:false}
  static getDerivedStateFromError() {return {failed:true}}
  render() {return this.state.failed ? <Failure message="This page could not be displayed. Reload or open another page."/> : this.props.children}
}
function SignIn({onLogin}:{onLogin:(p:Person)=>void}) {
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form=new FormData(event.currentTarget)
    setBusy(true)
    setError('')
    try {onLogin(await api<Person>('/auth/login','POST',{username:form.get('username'),password:form.get('password')}))}
    catch(e){setError((e as Error).message)}
    finally{setBusy(false)}
  }
  return <main className="login-shell"><form className="login panel" onSubmit={submit}>
    <div className="logo-icon"><CircuitBoard size={23}/></div><h1>{appName}</h1>
    <p className="app-acronym">{appAcronym}</p>
    <p>Sign in with your corporate account.</p>
    {error && <Failure message={error}/>}
    <label>Username<input name="username" autoComplete="username" required autoFocus/></label>
    <label>Password<input name="password" type="password" autoComplete="current-password" required/></label>
    <Button disabled={busy}>{busy?'Signing in…':'Sign in'}</Button>
  </form></main>
}
const navigation = [
  ['Dashboard','/',LayoutDashboard], ['Boards','/boards',CircuitBoard], ['Programs','/programs',FolderKanban],
  ['Activity History','/activity',Activity], ['Notifications','/notifications',Bell], ['Administration','/admin',ShieldCheck],
] as const

function Layout({person,onLogout}:{person:Person;onLogout:()=>void}) {
  const location=useLocation()
  const navigate=useNavigate()
  const people=useData<Person[]>('/people')
  const programs=useData<Program[]>('/programs')
  const [theme,setTheme]=useState(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark')
  const [message,toast]=useState('')
  const [menu,setMenu]=useState(false)
  const [term,setTerm]=useState('')
  const section=navigation.find(item=>item[1] !== '/' && location.pathname.startsWith(item[1]))?.[0] || 'Dashboard'
  function toggleTheme() {
    const next = theme==='light'?'dark':'light'
    document.documentElement.dataset.theme = next
    localStorage.setItem('theme',next)
    setTheme(next)
  }
  useEffect(()=>{if(message){const timeout=setTimeout(()=>toast(''),4200);return ()=>clearTimeout(timeout)}},[message])
  async function logout(){try{await api('/auth/logout','POST');onLogout()}catch(e){toast((e as Error).message)}}
  function search(event:FormEvent){event.preventDefault();navigate('/boards?'+new URLSearchParams({q:term.trim()}));setMenu(false)}
  return <Tracker.Provider value={{person,people:people.data||[],programs:programs.data||[],toast,refresh:()=>{people.reload();programs.reload()}}}>
    <div className="shell">
      <aside className={'sidebar '+(menu?'open':'')}>
        <Link className="brand" to="/" onClick={()=>setMenu(false)}><span className="logo-icon"><CircuitBoard size={21}/></span><span>{appName}<small>{appAcronym}</small></span></Link>
        <nav aria-label="Main navigation">
          {navigation.filter(i=>i[1]!=='/admin'||person.admin).map(([name,to,Icon])=><NavLink key={to} to={to} end={to==='/'} onClick={()=>setMenu(false)}><Icon size={18}/>{name}</NavLink>)}
        </nav>
        <div className="account">
          <div className="account-row"><span className="avatar">{person.display_name.split(' ').slice(0,2).map(s=>s[0]).join('')}</span><span><strong>{person.display_name}</strong><small>{person.admin?'Administrator':'Engineer'}</small></span><button className="icon-button" aria-label="Sign out" title="Sign out" onClick={logout}><LogOut size={17}/></button></div>
        </div>
      </aside>
      <div className="workspace">
        <div className="topbar">
          <button className="icon-button mobile-menu" onClick={()=>setMenu(!menu)} aria-expanded={menu} aria-label="Toggle navigation"><Menu size={21}/></button>
          <div className="crumb"><span className="app-name">{appName}</span><ChevronRight size={14}/><strong>{section}</strong></div>
          <form onSubmit={search} className="global-search"><Search size={17}/><input aria-label="Search boards globally" placeholder="Search boards…" value={term} onChange={e=>setTerm(e.target.value)}/></form>
          <button className="icon-button theme" title="Toggle theme" aria-label="Toggle theme" onClick={toggleTheme}>{theme==='light'?<Moon size={18}/>:<Sun size={18}/>}</button>
        </div>
        <main className="content"><Boundary key={location.pathname}><Routes>
          <Route path="/" element={<Dashboard/>}/><Route path="/boards" element={<Boards/>}/><Route path="/boards/:id" element={<BoardDetail/>}/>
          <Route path="/programs" element={<Programs/>}/><Route path="/programs/:id" element={<ProgramDetail/>}/>
          <Route path="/activity" element={<ActivityPage/>}/><Route path="/notifications" element={<Notifications/>}/>
          <Route path="/admin" element={person.admin?<Admin/>:<Navigate to="/" replace/>}/><Route path="*" element={<Failure message="Page not found."/>}/>
        </Routes></Boundary></main>
      </div>
      {message && <div className="toast" role="status">{message}<button aria-label="Dismiss message" onClick={()=>toast('')}>×</button></div>}
    </div>
  </Tracker.Provider>
}

export function App() {
  const [person,update]=useState<Person|null|undefined>(undefined)
  const [error,setError]=useState('')
  function setPerson(value:Person|null){setSession(value);update(value)}
  useEffect(()=>{
    const expire=()=>setPerson(null)
    window.addEventListener('tracker-expired',expire)
    api<Person>('/auth/me').then(setPerson,e=>{
      if (!(e instanceof ApiError) || e.status!==401) setError(e.message)
      setPerson(null)
    })
    return ()=>window.removeEventListener('tracker-expired',expire)
  },[])
  if(person===undefined)return <Loading/>
  if(error)return <Failure message={error}/>
  return person?<Layout person={person} onLogout={()=>setPerson(null)}/>:<SignIn onLogin={setPerson}/>
}
