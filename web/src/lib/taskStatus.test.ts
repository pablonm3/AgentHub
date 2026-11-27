import { describe, expect, it } from 'vitest'
import type { TaskStatus } from '../api'
import { listRank, statusLabel, waitsOnPablo } from './taskStatus'

const nameOf = (id: string) => ({ engineer: 'Engineer', devops: 'DevOps' })[id] ?? id
const onEngineer = { task_id: 3, ai_user_id: 'engineer' }

describe('taskStatus', () => {
  it('says whether a task waits on Pablo', () => {
    expect(waitsOnPablo({ status: 'waiting_on_user', waiting_on: null })).toBe(true)
    expect(waitsOnPablo({ status: 'waiting_on_user', waiting_on: onEngineer })).toBe(false)
    for (const status of ['running', 'done', 'archived'] as TaskStatus[]) {
      expect(waitsOnPablo({ status, waiting_on: null })).toBe(false)
    }
  })

  it('labels a task waiting on an AI user by name and every other status as before', () => {
    expect(statusLabel({ status: 'waiting_on_user', waiting_on: onEngineer }, nameOf)).toBe('Waiting on Engineer')
    expect(statusLabel({ status: 'waiting_on_user', waiting_on: null }, nameOf)).toBe('Waiting on user')
    expect(statusLabel({ status: 'running', waiting_on: null }, nameOf)).toBe('Running')
    expect(statusLabel({ status: 'done', waiting_on: null }, nameOf)).toBe('Done')
    expect(statusLabel({ status: 'archived', waiting_on: null }, nameOf)).toBe('Archived')
  })

  it('ranks waiting on Pablo first and waiting on an AI user with the running tasks', () => {
    expect(listRank({ status: 'waiting_on_user', waiting_on: null })).toBe(0)
    expect(listRank({ status: 'waiting_on_user', waiting_on: onEngineer })).toBe(1)
    expect(listRank({ status: 'running', waiting_on: null })).toBe(1)
    expect(listRank({ status: 'done', waiting_on: null })).toBe(2)
    expect(listRank({ status: 'archived', waiting_on: null })).toBe(3)
  })
})
