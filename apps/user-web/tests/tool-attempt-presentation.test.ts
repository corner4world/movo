import assert from 'node:assert/strict'
import test from 'node:test'
import { toolAttemptStateKey, toolGroupFailureKey } from '../src/features/execution-v3/domain/toolAttemptPresentation'

test('an intermediate tool failure does not label a completed task as failed', () => {
  assert.equal(toolAttemptStateKey('completed'), 'execution.v3.tool_attempt_continued')
  assert.equal(toolGroupFailureKey('completed'), 'execution.v3.tool_group_completed_with_attempts')
})

test('running and failed tasks retain distinct attempt context', () => {
  assert.equal(toolAttemptStateKey('running'), 'execution.v3.tool_attempt_adjusting')
  assert.equal(toolGroupFailureKey('failed'), 'execution.v3.repeated_failed')
})
