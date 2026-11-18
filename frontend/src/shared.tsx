import { createContext, useContext, type ReactNode } from 'react'
import type { Person, Program } from './api'

type Context = {person:Person; people:Person[]; programs:Program[]; timezone:string; toast:(message:string)=>void; refresh:()=>void}
export const Tracker = createContext<Context>(null!)
export const useTracker = () => useContext(Tracker)

export function Failure({message}:{message:string}) { return <div className="error" role="alert">{message}</div> }
export function Loading() {return <div className="skeleton" role="status" aria-label="Loading"><div/><div/><div/></div>}
export function Empty({children}:{children:ReactNode}) {return <div className="empty">{children}</div>}
export function PageHeading({title,description,action}:{title:string;description?:string;action?:ReactNode}) {
  return <header className="page-heading"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</header>
}
