import { describe, expect, it } from 'vitest'
import { NO_NAME_ERROR, NO_URL_ERROR, canCreateRepo, newProjectInput } from './newProject'

describe('canCreateRepo', () => {
  it('is true only when the server said so', () => {
    expect(canCreateRepo({ can_create: true, reason: null })).toBe(true)
    expect(canCreateRepo({ can_create: false, reason: 'not_installed' })).toBe(false)
    expect(canCreateRepo({ can_create: false, reason: 'not_logged_in' })).toBe(false)
    expect(canCreateRepo({ can_create: false, reason: 'unknown' })).toBe(false)
    expect(canCreateRepo(undefined)).toBe(false) // a server without the key
  })
})

describe('newProjectInput', () => {
  it('asks for a name first, in both states', () => {
    expect(newProjectInput('  ', '', true)).toEqual({ ok: false, error: NO_NAME_ERROR })
    expect(newProjectInput('', 'git@github.com:o/r.git', false)).toEqual({ ok: false, error: NO_NAME_ERROR })
  })

  it('asks for the repo URL when this machine cannot create a repository', () => {
    expect(newProjectInput('proj', '  ', false)).toEqual({ ok: false, error: NO_URL_ERROR })
    expect(NO_URL_ERROR).toContain('repo URL')
  })

  it('sends the name alone when this machine can create the repository', () => {
    expect(newProjectInput(' proj ', '', true)).toEqual({ ok: true, new_project: { name: 'proj' } })
  })

  it('sends a trimmed URL in both states', () => {
    const expected = { ok: true, new_project: { name: 'proj', repo_url: 'git@github.com:o/r.git' } }
    expect(newProjectInput('proj', ' git@github.com:o/r.git ', true)).toEqual(expected)
    expect(newProjectInput('proj', ' git@github.com:o/r.git ', false)).toEqual(expected)
  })
})
