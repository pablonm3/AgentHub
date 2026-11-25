import { describe, expect, it } from 'vitest'
import type { UsageFigure } from '../api'
import { formatResetTime, limitLabel, usageLines } from './usage'

const NOW = Date.parse('2026-11-25T14:03:07Z')
const RESETS = 1795993200 // 2026-11-29 23:00 UTC

function fig(limit: string, used: number | null, over: Partial<UsageFigure> = {}): UsageFigure {
  return { limit, used, resets_at: RESETS, reached: false, read_at: '2026-11-25T14:00:00Z', ...over }
}

describe('limitLabel', () => {
  it('names the three known limits and shows any other under its own name', () => {
    expect(limitLabel('seven_day')).toBe('Week')
    expect(limitLabel('five_hour')).toBe('5 h')
    expect(limitLabel('seven_day_overage_included')).toBe('Fable week')
    expect(limitLabel('seven_day_opus')).toBe('seven_day_opus')
  })
})

describe('usageLines', () => {
  it('shows the whole percent left of each limit', () => {
    const lines = usageLines([fig('seven_day', 0.22), fig('seven_day_overage_included', 0.37), fig('five_hour', 1)], NOW)
    expect(Object.fromEntries(lines.map((l) => [l.label, l.percentLeft]))).toEqual({ Week: 78, 'Fable week': 63, '5 h': 0 })
  })

  it('orders the known limits by period, then other names alphabetically', () => {
    const lines = usageLines(
      [fig('zeta_window', 0.1), fig('seven_day_opus', 0.1), fig('seven_day_overage_included', 0.37), fig('seven_day', 0.22), fig('five_hour', 0.1)],
      NOW,
    )
    expect(lines.map((l) => l.label)).toEqual(['5 h', 'Week', 'Fable week', 'seven_day_opus', 'zeta_window'])
  })

  it('leaves out a figure whose period has ended and keeps the others', () => {
    const ended = Math.floor(NOW / 1000)
    const lines = usageLines([fig('five_hour', 0.5, { resets_at: ended }), fig('seven_day', 0.22)], NOW)
    expect(lines.map((l) => l.limit)).toEqual(['seven_day'])
  })

  it('is empty when no figure is known or every period has ended', () => {
    expect(usageLines([], NOW)).toEqual([])
    expect(usageLines(undefined, NOW)).toEqual([])
    const past = Math.floor(NOW / 1000) - 60
    expect(usageLines([fig('seven_day', 0.22, { resets_at: past }), fig('five_hour', null, { reached: true, resets_at: past })], NOW)).toEqual([])
  })

  it('shows a reached limit with its reset time and no percentage', () => {
    const [line] = usageLines([fig('five_hour', null, { reached: true, resets_at: RESETS - 3600 })], NOW)
    expect(line).toEqual({ limit: 'five_hour', label: '5 h', percentLeft: null, resetsAt: RESETS - 3600, readAt: '2026-11-25T14:00:00Z' })
  })
})

describe('formatResetTime', () => {
  it('shows the weekday, day and time of the reset in the given time zone', () => {
    const utc = formatResetTime(RESETS, { locale: 'en-GB', timeZone: 'UTC' })
    for (const part of ['Sun', '29', '23:00']) expect(utc).toContain(part)
    const tokyo = formatResetTime(RESETS, { locale: 'en-GB', timeZone: 'Asia/Tokyo' })
    for (const part of ['Mon', '30', '08:00']) expect(tokyo).toContain(part)
  })
})
