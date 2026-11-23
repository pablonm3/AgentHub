/** A working timer: `0:42`, `12:05`, `1:02:03`. Negative or missing values read `0:00`. */
export function formatDuration(ms: number): string {
  const total = Number.isFinite(ms) && ms > 0 ? Math.floor(ms / 1000) : 0
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const ss = String(seconds).padStart(2, '0')
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${ss}`
  return `${minutes}:${ss}`
}

const TOKEN_UNITS: ReadonlyArray<readonly [string, number]> = [
  ['k', 1e3],
  ['M', 1e6],
  ['B', 1e9],
]

/** A token count: `0`, `950`, `12.3k`, `1.2M`. One decimal below 100 of a unit, none above. */
export function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '0'
  const value = Math.round(n)
  if (value < 1000) return String(value)
  for (let i = 0; i < TOKEN_UNITS.length; i++) {
    const [suffix, size] = TOKEN_UNITS[i]
    const scaled = value / size
    const text = scaled < 100 ? scaled.toFixed(1).replace(/\.0$/, '') : String(Math.round(scaled))
    // 999,960 rounds to "1000k"; move it to the next unit instead.
    if (Number(text) < 1000 || i === TOKEN_UNITS.length - 1) return text + suffix
  }
  return String(value)
}

/** The timer of a task: time spent running before `running_since`, plus the current run. */
export function taskElapsed(
  task: { running_ms: number; running_since: number | null },
  now: number,
): number {
  const current = task.running_since ? Math.max(0, now - task.running_since) : 0
  return (task.running_ms || 0) + current
}

/** "just now", "5 min ago", "3 h ago", "yesterday", then a short date. */
export function formatRelative(iso: string, now: number): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((now - then) / 1000)
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  if (hours < 48) return 'yesterday'
  return new Date(then).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

/** "A", "A and B", "A, B and C". */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/**
 * A browser link for a repository: `https://` URLs as they are, `git@host:owner/repo.git` and
 * `ssh://git@host/owner/repo.git` as `https://host/owner/repo`; null for anything else.
 */
export function repoWebUrl(repo: string | null | undefined): string | null {
  const text = (repo ?? '').trim()
  if (/^https?:\/\//i.test(text)) return text.replace(/\.git$/, '')
  const scp = /^[\w.-]+@([\w.-]+):(.+?)(?:\.git)?\/?$/.exec(text)
  if (scp) return `https://${scp[1]}/${scp[2]}`
  const ssh = /^ssh:\/\/(?:[\w.-]+@)?([\w.-]+)(?::\d+)?\/(.+?)(?:\.git)?\/?$/i.exec(text)
  if (ssh) return `https://${ssh[1]}/${ssh[2]}`
  return null
}
