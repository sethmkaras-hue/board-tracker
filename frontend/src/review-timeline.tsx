import { useEffect, useId, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { type Board, type Review } from './api'
import { stateColors } from './dashboard'
import { reviews as reviewKinds, states } from './fields'

function calendarMonth(date: Date, offset: number) {
  const first = new Date(date)
  first.setUTCDate(1)
  first.setUTCMonth(first.getUTCMonth() + offset)
  const last = new Date(first)
  last.setUTCMonth(last.getUTCMonth() + 1, 0)
  first.setUTCDate(Math.min(date.getUTCDate(), last.getUTCDate()))
  return first
}

export function timelineScale(today: string, dates: string[]) {
  let earliest = today
  let latest = today
  for (const date of dates) {
    if (date < earliest) earliest = date
    if (date > latest) latest = date
  }
  const start = calendarMonth(new Date(earliest), -1)
  const end = calendarMonth(new Date(latest), 1)
  const position = (date: Date) => (+date - +start) / (+end - +start) * 100
  const ticks: Date[] = []
  const first = new Date(start)
  first.setUTCDate(1)
  for (let tick = first < start ? calendarMonth(first, 1) : first; tick <= end; tick = calendarMonth(tick, 1)) {
    ticks.push(tick)
  }
  return { start, end, ticks, position }
}

function localToday() {
  const parts = new Intl.DateTimeFormat('en-US', {year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts()
  return ['year','month','day'].map(type=>parts.find(part=>part.type===type)?.value).join('-')
}

const monthLabel = new Intl.DateTimeFormat('en-US', {month:'short', year:'numeric', timeZone:'UTC'})
const dateLabel = new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', year:'numeric', timeZone:'UTC'})

type TimelineBoard = Pick<Board, 'id'|'identifier'|'reviews'>
type TimelineProps = {reviews:Review[]; boards?:never} | {boards:TimelineBoard[]; reviews?:never}
type ScheduledReview = Review & {date:string}

function scheduledReviews(reviews:Review[]):ScheduledReview[] {
  return reviewKinds.flatMap(kind=>reviews.filter(
    (review):review is ScheduledReview=>review.kind===kind && review.date!==null,
  ))
}

// Reserve enough horizontal space for each focus target. Each extra lane handles a collision.
export function packMilestones<T extends {left:number}>(milestones:T[], minimumGap:number) {
  const laneEnds:number[]=[]
  return [...milestones].sort((a,b)=>a.left-b.left).map(milestone=>{
    const available=laneEnds.findIndex(end=>milestone.left-end>=minimumGap)
    const lane=available<0?laneEnds.length:available
    laneEnds[lane]=milestone.left
    return {...milestone,lane}
  })
}

export function ReviewTimeline({reviews,boards}:TimelineProps) {
  const headingId=useId()
  const [today,setToday] = useState(localToday)
  useEffect(()=>{
    const refresh=()=>setToday(localToday())
    const timer=window.setInterval(refresh,60_000)
    window.addEventListener('focus',refresh)
    return ()=>{
      window.clearInterval(timer)
      window.removeEventListener('focus',refresh)
    }
  },[])
  const rows=useMemo(()=>boards
    ? [...boards].sort((a,b)=>a.identifier.localeCompare(b.identifier))
      .map(board=>({id:board.id,identifier:board.identifier,reviews:scheduledReviews(board.reviews)}))
    : [{id:0,identifier:null,reviews:scheduledReviews(reviews||[])}], [boards,reviews])
  const {ticks,position}=useMemo(()=>timelineScale(today,rows.flatMap(row=>row.reviews.map(review=>review.date))),[today,rows])
  const count=rows.reduce((total,row)=>total+row.reviews.length,0)
  const plotWidth=Math.max(550,(ticks.length+1)*96)
  const milestone=(review:ScheduledReview,left:number,identifier:string|null,lane=0)=>{
    const date=dateLabel.format(new Date(review.date))
    const label=[identifier,review.kind,date,review.state].filter(Boolean).join(' · ')
    return <div key={review.id} className={'review-milestone'+(left>=50?' label-before':'')}
      style={{left:left+'%',top:identifier?lane*28+17:undefined}}>
      {identifier?<span className="program-review-marker" tabIndex={0} role="img" aria-label={label}>
        <span className="review-dot" style={{background:stateColors[review.state]}}/>
        <span className="review-tooltip" aria-hidden="true">{label}</span>
      </span>:<>
        <span className="review-dot" style={{background:stateColors[review.state]}}/>
        <span className="review-milestone-label" title={label} aria-label={label} tabIndex={0}>
          <strong>{review.kind}</strong><small>{date} · {review.state}</small>
          <span className="review-tooltip" aria-hidden="true">{label}</span>
        </span>
      </>}
    </div>
  }
  return <section className={'panel record-section review-timeline'+(boards?' program-review-timeline separate':'')} aria-labelledby={headingId}>
    <div className="section-heading"><h2 id={headingId}>{boards?'Program Review Timeline':'Review timeline'}</h2></div>
    <div className="review-timeline-scroll" role="region" aria-label="Review dates by month" tabIndex={0}>
      <div className="review-timeline-chart" style={{minWidth:plotWidth+(boards?212:104)}}>
        <div className="review-timeline-plot">
          <div className="review-axis" aria-hidden="true">{ticks.map(date=>
            <span key={date.toISOString()} style={{left:position(date)+'%'}}>{monthLabel.format(date)}</span>)}</div>
          <div className="today-line" style={{left:position(new Date(today))+'%'}}>
            <span><b>Today</b> · <time dateTime={today}>{dateLabel.format(new Date(today))}</time></span>
          </div>
          {rows.map(row=>{
            if(!row.identifier)return row.reviews.map(review=><div className="review-lane" key={review.id}>
              {milestone(review,position(new Date(review.date)),null)}
            </div>)
            const markers=packMilestones(row.reviews.map(review=>({review,left:position(new Date(review.date))})),28/plotWidth*100)
            const height=34+28*(markers.reduce((max,marker)=>Math.max(max,marker.lane),0))
            return <div className="program-review-row" key={row.id} style={{height}}>
              <div className="program-review-board"><Link to={'/boards/'+row.id}>{row.identifier}</Link></div>
              {markers.length?markers.map(({review,left,lane})=>milestone(review,left,row.identifier,lane)):
                <span className="program-review-undated muted">No review dates</span>}
            </div>
          })}
        </div>
      </div>
    </div>
    {boards && count>0&&<ul className="program-review-legend" aria-label="Review states">{states.map(state=>
      <li key={state}><span className="review-dot" style={{background:stateColors[state]}}/>{state}</li>
    )}</ul>}
    {boards && count===0&&<p className="review-timeline-note muted">No associated boards have scheduled review dates.</p>}
    {!boards && count<reviewKinds.length&&<p className="review-timeline-note muted">{count===0?'No review dates scheduled.':(reviewKinds.length-count)+' reviews without dates.'}</p>}
  </section>
}
