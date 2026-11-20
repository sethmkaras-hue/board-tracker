import { describe, expect, it } from 'vitest'
import { automaticReviewStart } from './review-fields'
import { packMilestones, timelineScale } from './review-timeline'

const iso = (date: Date) => date.toISOString().slice(0,10)

describe('review timeline scale', () => {
  it('clamps calendar month bounds on leap-year and short months', () => {
    const scale = timelineScale('2024-05-31', ['2024-03-31'])
    expect(iso(scale.start)).toBe('2024-02-29')
    expect(iso(scale.end)).toBe('2024-06-30')
    expect(scale.ticks.map(iso)).toEqual(['2024-03-01','2024-04-01','2024-05-01','2024-06-01'])
  })

  it('positions both past and future reviews in proportion to elapsed days', () => {
    const scale = timelineScale('2026-05-01', ['2026-04-01', '2026-05-02'])
    const start = scale.position(new Date('2026-04-01'))
    const today = scale.position(new Date('2026-05-01'))
    const future = scale.position(new Date('2026-05-02'))
    expect((today-start)/(future-today)).toBeCloseTo(30)
    expect(today).toBeGreaterThan(0)
    expect(today).toBeLessThan(100)
  })

  it('keeps Today inside the range with only past reviews or no review dates', () => {
    const today = '2026-01-31'
    for (const dates of [['2025-01-02'], []]) {
      const scale = timelineScale(today,dates)
      expect(iso(scale.end)).toBe('2026-02-28')
      expect(scale.position(new Date(today))).toBeGreaterThan(0)
      expect(scale.position(new Date(today))).toBeLessThan(100)
    }
    expect(iso(timelineScale(today,[]).start)).toBe('2025-12-31')
  })
})

describe('program milestone packing', () => {
  it('stacks nearby markers, reuses lanes, and preserves exact positions', () => {
    const markers = [{left:60},{left:10},{left:10},{left:11},{left:30}]
    const packed = packMilestones(markers,5)
    expect(packed.map(({left,lane})=>[left,lane])).toEqual([[10,0],[10,1],[11,2],[30,0],[60,0]])
    expect(markers.map(({left})=>left)).toEqual([60,10,10,11,30])
  })
})

it('uses seven calendar days across leap days and DST boundaries', () => {
  expect(automaticReviewStart('2024-03-06')).toBe('2024-02-28')
  expect(automaticReviewStart('2026-03-13')).toBe('2026-03-06')
})

it('places intersecting review windows on separate lanes and keeps meeting positions', () => {
  const reviews = [{start:5,left:10},{start:8,left:30},{start:14,left:25},{start:40,left:50}]
  expect(packMilestones(reviews,2).map(({left,lane})=>[left,lane])).toEqual([[10,0],[30,1],[25,0],[50,0]])
  const scale = timelineScale('2026-02-25',['2025-12-15','2026-03-10'])
  expect(iso(scale.start)).toBe('2025-11-15')
  expect(iso(scale.end)).toBe('2026-04-10')
  expect(scale.position(new Date('2025-12-15'))).toBeLessThan(scale.position(new Date('2026-03-10')))
})
