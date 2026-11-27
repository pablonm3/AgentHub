// The values of a Project dropdown that are not project names
export const NOT_CHOSEN = '' // the value `Select` shows its placeholder for
export const NEW_PROJECT = '__new__'
export const NO_PROJECT = '__none__'

/** The project a picked option stands for: null for "No project", else the registered name. */
export function pickedProject(option: string): string | null {
  return option === NO_PROJECT ? null : option
}

/** The project part of a new ticket's request, for every option but "New project". */
export function newTicketProject(option: string): { project: string | null } | { project_chosen: false } {
  return option === NOT_CHOSEN ? { project_chosen: false } : { project: pickedProject(option) }
}
