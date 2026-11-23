import { joinNames } from './format'

interface Delivery {
  delivered_to: { ai_user_id: string }[]
  started: { ai_user_id: string }[]
}

/**
 * The muted line under one of Pablo's comments: "Sent to Engineer", "Started a task for DevOps",
 * both joined with " · ", or "Sent to no task".
 */
export function deliveryLine(comment: Delivery, nameOf: (userId: string) => string): string {
  const names = (refs: { ai_user_id: string }[]) => [...new Set(refs.map((r) => nameOf(r.ai_user_id)))]
  const sent = names(comment.delivered_to ?? [])
  const started = names(comment.started ?? [])
  const pieces: string[] = []
  if (sent.length) pieces.push(`Sent to ${joinNames(sent)}`)
  if (started.length) pieces.push(`Started a task for ${joinNames(started)}`)
  return pieces.length ? pieces.join(' · ') : 'Sent to no task'
}
