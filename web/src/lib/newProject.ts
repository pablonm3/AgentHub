import type { GithubStatus } from '../api'

export const NO_NAME_ERROR = 'Give the new project a name.'
export const NO_URL_ERROR = 'Enter the repo URL: this machine cannot create a GitHub repository.'

/** True only when the server said this machine can create a GitHub repository. */
export function canCreateRepo(github: GithubStatus | undefined): boolean {
  return github?.can_create === true
}

export type NewProjectInput =
  | { ok: true; new_project: { name: string; repo_url?: string } }
  | { ok: false; error: string }

/** What "New project" sends, or the error the form shows instead of sending anything. */
export function newProjectInput(name: string, repoUrl: string, canCreate: boolean): NewProjectInput {
  const trimmedName = name.trim()
  const url = repoUrl.trim()
  if (!trimmedName) return { ok: false, error: NO_NAME_ERROR }
  if (!url && !canCreate) return { ok: false, error: NO_URL_ERROR }
  return { ok: true, new_project: url ? { name: trimmedName, repo_url: url } : { name: trimmedName } }
}
