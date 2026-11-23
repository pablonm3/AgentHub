import { describe, expect, it } from 'vitest'
import { formatDuration, formatRelative, formatTokens, joinNames, repoWebUrl, taskElapsed } from './format'
import { deliveryLine } from './delivery'

describe('formatDuration', () => {
  it('shows minutes and seconds under an hour', () => {
    expect(formatDuration(0)).toBe('0:00')
    expect(formatDuration(42_000)).toBe('0:42')
    expect(formatDuration(42_999)).toBe('0:42')
    expect(formatDuration(12 * 60_000 + 5_000)).toBe('12:05')
    expect(formatDuration(59 * 60_000 + 59_000)).toBe('59:59')
  })

  it('shows hours, minutes and seconds from one hour on', () => {
    expect(formatDuration(3_600_000)).toBe('1:00:00')
    expect(formatDuration(3_600_000 + 2 * 60_000 + 3_000)).toBe('1:02:03')
    expect(formatDuration(25 * 3_600_000)).toBe('25:00:00')
  })

  it('reads 0:00 for negative or invalid values', () => {
    expect(formatDuration(-5000)).toBe('0:00')
    expect(formatDuration(Number.NaN)).toBe('0:00')
  })
})

describe('formatTokens', () => {
  it('shows small counts as they are', () => {
    expect(formatTokens(0)).toBe('0')
    expect(formatTokens(7)).toBe('7')
    expect(formatTokens(950)).toBe('950')
    expect(formatTokens(999)).toBe('999')
  })

  it('shows thousands with one decimal', () => {
    expect(formatTokens(1000)).toBe('1k')
    expect(formatTokens(1500)).toBe('1.5k')
    expect(formatTokens(12_345)).toBe('12.3k')
    expect(formatTokens(123_456)).toBe('123k')
  })

  it('shows millions and switches unit instead of reading 1000k', () => {
    expect(formatTokens(1_200_000)).toBe('1.2M')
    expect(formatTokens(999_960)).toBe('1M')
    expect(formatTokens(45_600_000)).toBe('45.6M')
  })

  it('reads 0 for negative or invalid values', () => {
    expect(formatTokens(-3)).toBe('0')
    expect(formatTokens(Number.NaN)).toBe('0')
  })
})

describe('taskElapsed', () => {
  it('adds the current run only while running', () => {
    expect(taskElapsed({ running_ms: 12_000, running_since: null }, 99_999)).toBe(12_000)
    expect(taskElapsed({ running_ms: 12_000, running_since: 1_000 }, 4_000)).toBe(15_000)
  })

  it('never goes back when the clock is behind running_since', () => {
    expect(taskElapsed({ running_ms: 5_000, running_since: 10_000 }, 9_000)).toBe(5_000)
  })
})

describe('formatRelative', () => {
  const now = Date.parse('2026-11-23T12:00:00Z')
  it('describes recent times', () => {
    expect(formatRelative('2026-11-23T11:59:40Z', now)).toBe('just now')
    expect(formatRelative('2026-11-23T11:55:00Z', now)).toBe('5 min ago')
    expect(formatRelative('2026-11-23T09:00:00Z', now)).toBe('3 h ago')
    expect(formatRelative('2026-11-22T10:00:00Z', now)).toBe('yesterday')
  })

  it('returns an empty string for an invalid time', () => {
    expect(formatRelative('not a date', now)).toBe('')
  })
})

describe('joinNames and deliveryLine', () => {
  const names: Record<string, string> = { engineer: 'Engineer', devops: 'DevOps', data_scientist: 'Data Scientist' }
  const nameOf = (id: string) => names[id] ?? id

  it('joins names', () => {
    expect(joinNames([])).toBe('')
    expect(joinNames(['A'])).toBe('A')
    expect(joinNames(['A', 'B'])).toBe('A and B')
    expect(joinNames(['A', 'B', 'C'])).toBe('A, B and C')
  })

  it('says who received a comment and for whom a task was started', () => {
    expect(deliveryLine({ delivered_to: [{ ai_user_id: 'engineer' }], started: [] }, nameOf)).toBe(
      'Sent to Engineer',
    )
    expect(deliveryLine({ delivered_to: [], started: [{ ai_user_id: 'devops' }] }, nameOf)).toBe(
      'Started a task for DevOps',
    )
    expect(
      deliveryLine(
        { delivered_to: [{ ai_user_id: 'engineer' }, { ai_user_id: 'data_scientist' }], started: [{ ai_user_id: 'devops' }] },
        nameOf,
      ),
    ).toBe('Sent to Engineer and Data Scientist · Started a task for DevOps')
    expect(deliveryLine({ delivered_to: [], started: [] }, nameOf)).toBe('Sent to no task')
  })
})

describe('repoWebUrl', () => {
  it('turns clone URLs into browser links', () => {
    expect(repoWebUrl('git@github.com:owner/repo.git')).toBe('https://github.com/owner/repo')
    expect(repoWebUrl('ssh://git@github.com/owner/repo.git')).toBe('https://github.com/owner/repo')
    expect(repoWebUrl('https://github.com/owner/repo.git')).toBe('https://github.com/owner/repo')
    expect(repoWebUrl('https://github.com/owner/repo')).toBe('https://github.com/owner/repo')
  })

  it('returns null for anything that is not a remote URL', () => {
    expect(repoWebUrl('')).toBeNull()
    expect(repoWebUrl(null)).toBeNull()
    expect(repoWebUrl('../local/repo')).toBeNull()
  })
})
