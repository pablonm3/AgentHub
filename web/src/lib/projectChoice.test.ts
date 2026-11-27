import { describe, expect, it } from 'vitest'
import { NO_PROJECT, NOT_CHOSEN, newTicketProject, pickedProject } from './projectChoice'

describe('newTicketProject', () => {
  it('sends "not chosen" while nothing is picked', () => {
    expect(newTicketProject(NOT_CHOSEN)).toEqual({ project_chosen: false })
  })

  it('sends no project only when "No project" is picked', () => {
    expect(newTicketProject(NO_PROJECT)).toEqual({ project: null })
  })

  it('sends the name of a registered project', () => {
    expect(newTicketProject('AgentHub')).toEqual({ project: 'AgentHub' })
  })
})

describe('pickedProject', () => {
  it('is null for "No project" and the name for a registered project', () => {
    expect(pickedProject(NO_PROJECT)).toBeNull()
    expect(pickedProject('AgentHub')).toBe('AgentHub')
  })
})
