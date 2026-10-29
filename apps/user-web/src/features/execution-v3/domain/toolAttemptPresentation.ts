import type { ExecutionStateV3 } from './model'

type RunStatus = ExecutionStateV3['runStatus']

/** A failed tool attempt is not the same as a failed assistant task. */
export function toolAttemptStateKey(runStatus: RunStatus): string {
  if (runStatus === 'completed') return 'execution.v3.tool_attempt_continued'
  if (runStatus === 'running') return 'execution.v3.tool_attempt_adjusting'
  return 'execution.v3.tool_attempt_failed'
}

export function toolGroupFailureKey(runStatus: RunStatus): string {
  if (runStatus === 'completed') return 'execution.v3.tool_group_completed_with_attempts'
  if (runStatus === 'running') return 'execution.v3.tool_group_adjusting'
  return 'execution.v3.repeated_failed'
}
