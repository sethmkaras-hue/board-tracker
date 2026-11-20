import { describe, expect, it } from 'vitest'
import { timelineScale } from './review-timeline'

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
