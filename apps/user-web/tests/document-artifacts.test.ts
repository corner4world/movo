import assert from 'node:assert/strict'
import test from 'node:test'
import { findMarkdownDocument, upsertDocumentEverywhere } from '../src/components/chat/documentArtifacts'
import type { DocumentInfo } from '../src/components/chat/types'
import { ensureMessageExecutionV3 } from '../src/features/execution-v3/stores/messageExecution'

test('replacing an exported document updates the existing message and artifact', () => {
  const previous: DocumentInfo = { id: 'doc-1', type: 'docx', url: '/old', filename: 'report.docx' }
  const next: DocumentInfo = { ...previous, url: '/new', signed_url: '/signed' }
  const message = { documents: [previous] }
  ensureMessageExecutionV3(message)
  upsertDocumentEverywhere(message, previous, next)
  assert.equal(message.documents.length, 1)
  assert.equal(message.documents[0].url, '/new')
  const artifacts = ensureMessageExecutionV3(message).state.artifacts
  assert.equal(artifacts.length, 1)
  assert.equal(artifacts[0].url, '/new')
})

test('markdown stays in message documents without duplicating a delivery artifact', () => {
  const markdown: DocumentInfo = { id: 'markdown-1', type: 'md', url: '/report.md' }
  const message = { documents: [] as DocumentInfo[] }
  ensureMessageExecutionV3(message)
  upsertDocumentEverywhere(message, null, markdown)
  assert.deepEqual(findMarkdownDocument(message), markdown)
  assert.equal(ensureMessageExecutionV3(message).state.artifacts.length, 0)
})
