import type { TaskLink, TaskStatus } from '../api'
import { statusLook } from '../theme'

type StatusOf = Pick<TaskLink, 'status' | 'waiting_on'>

/** A waiting task with no `waiting_on` waits on Pablo; one with it waits on another AI user's task. */
export function waitsOnPablo(task: StatusOf): boolean {
  return task.status === 'waiting_on_user' && !task.waiting_on
}

export function statusLabel(task: StatusOf, nameOf: (userId: string) => string): string {
  if (task.status === 'waiting_on_user' && task.waiting_on) return `Waiting on ${nameOf(task.waiting_on.ai_user_id)}`
  return (statusLook[task.status] ?? statusLook.done).label
}

const RANK: Record<TaskStatus, number> = { waiting_on_user: 0, running: 1, done: 2, archived: 3 }

/** Waiting on Pablo first; a task waiting on an AI user ranks with the running ones. */
export function listRank(task: StatusOf): number {
  return task.status === 'waiting_on_user' && task.waiting_on ? RANK.running : RANK[task.status]
}
