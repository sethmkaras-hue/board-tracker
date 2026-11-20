import { useEffect, useState } from 'react'
import { type Review } from './api'
import { stateColors } from './dashboard'
import { reviews as reviewKinds } from './fields'

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
  const ordered = [today, ...dates].sort()
  const start = calendarMonth(new Date(ordered[0]), -1)
  const end = calendarMonth(new Date(ordered[ordered.length - 1]), 1)
  const position = (date: Date) => (+date - +start) / (+end - +start) * 100
  const ticks: Date[] = []
  const first = new Date(start)
  first.setUTCDate(1)
  for (let tick = first < start ? calendarMonth(first, 1) : first; tick <= end; tick = calendarMonth(tick, 1)) {
    ticks.push(tick)
  }
  return { start, end, ticks, position }
}

function todayIn(timeZone: string) {
  const parts = new Intl.DateTimeFormat('en-US', {timeZone, year:'numeric', month:'2-digit', day:'2-digit'}).formatToParts()
  return ['year','month','day'].map(type=>parts.find(part=>part.type===type)?.value).join('-')
}

const monthLabel = new Intl.DateTimeFormat('en-US', {month:'short', year:'numeric', timeZone:'UTC'})
const dateLabel = new Intl.DateTimeFormat('en-US', {month:'short', day:'numeric', year:'numeric', timeZone:'UTC'})

export function ReviewTimeline({reviews, timezone}: {reviews:Review[]; timezone:string}) {
  const [today,setToday] = useState(()=>todayIn(timezone))
  useEffect(()=>{
    const refresh = ()=>setToday(todayIn(timezone))
    refresh()
    const timer = window.setInterval(refresh, 60_000)
    return ()=>window.clearInterval(timer)
  },[timezone])
  const scheduled = reviewKinds.flatMap(kind=>reviews.filter(review=>review.kind===kind && review.date!==null))
  const {ticks, position} = timelineScale(today,scheduled.map(review=>review.date!))
  const todayPosition = position(new Date(today))
  return <section className="panel record-section review-timeline" aria-labelledby="review-timeline-title">
    <div className="section-heading"><h2 id="review-timeline-title">Review timeline</h2></div>
    <div className="review-timeline-scroll" role="region" aria-label="Review dates by month" tabIndex={0}>
      <div className="review-timeline-chart" style={{minWidth:Math.max(650,(ticks.length+1)*96)}}>
        <div className="review-timeline-plot">
          <div className="review-axis" aria-hidden="true">{ticks.map(date=>
            <span key={date.toISOString()} style={{left:position(date)+'%'}}>{monthLabel.format(date)}</span>)}</div>
          <div className="today-line" style={{left:todayPosition+'%'}}>
            <span><b>Today</b> · <time dateTime={today}>{dateLabel.format(new Date(today))}</time></span>
          </div>
          {scheduled.map(review=>{
            const date = new Date(review.date!)
            const left = position(date)
            const label = review.kind+' · '+dateLabel.format(date)+' · '+review.state
            return <div className="review-lane" key={review.id}>
              <div className={'review-milestone'+(left>=50?' label-before':'')} style={{left:left+'%'}}>
                <span className="review-dot" style={{background:stateColors[review.state]}}/>
                <span className="review-milestone-label" title={label} aria-label={label} tabIndex={0}>
                  <strong>{review.kind}</strong><small>{dateLabel.format(date)} · {review.state}</small>
                  <span className="review-tooltip" aria-hidden="true">{label}</span>
                </span>
              </div>
            </div>
          })}
        </div>
      </div>
    </div>
    {scheduled.length<reviewKinds.length&&<p className="review-timeline-note muted">{scheduled.length===0?'No review dates scheduled.':(reviewKinds.length-scheduled.length)+' reviews without dates.'}</p>}
  </section>
}
