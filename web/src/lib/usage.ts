// What the header shows of the Claude account's usage left: one line per limit the server reported.

import type { UsageFigure } from '../api'

/** The limits the header names, shortest period first; any other limit follows under its own name. */
const KNOWN_LIMITS: ReadonlyArray<readonly [limit: string, label: string]> = [
  ['five_hour', '5 h'],
  ['seven_day', 'Week'],
  ['seven_day_overage_included', 'Fable week'],
]

export interface UsageLine {
  limit: string
  label: string
  /** Whole percent of the limit still unused; null when the limit is reached. */
  percentLeft: number | null
  /** Epoch seconds. */
  resetsAt: number
  readAt: string
}

export function limitLabel(limit: string): string {
  return KNOWN_LIMITS.find(([name]) => name === limit)?.[1] ?? limit
}

function rank(limit: string): number {
  const i = KNOWN_LIMITS.findIndex(([name]) => name === limit)
  return i === -1 ? KNOWN_LIMITS.length : i
}

/**
 * The figures whose period has not ended at `now` (ms), the known limits in period order, then the
 * others alphabetically. An empty list means the usage left is not known.
 */
export function usageLines(figures: UsageFigure[] | undefined, now: number): UsageLine[] {
  return (figures ?? [])
    .filter((f) => f.resets_at * 1000 > now && (f.reached || typeof f.used === 'number'))
    .sort((a, b) => rank(a.limit) - rank(b.limit) || (a.limit < b.limit ? -1 : a.limit > b.limit ? 1 : 0))
    .map((f) => ({
      limit: f.limit,
      label: limitLabel(f.limit),
      percentLeft: f.reached ? null : Math.min(100, Math.max(0, 100 - Math.round((f.used ?? 0) * 100))),
      resetsAt: f.resets_at,
      readAt: f.read_at,
    }))
}

/** "Sun 29 Nov, 23:00" in the browser's locale and time zone; both can be given for tests. */
export function formatResetTime(epochSeconds: number, opts: { locale?: string; timeZone?: string } = {}): string {
  return new Date(epochSeconds * 1000).toLocaleString(opts.locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: opts.timeZone,
  })
}
