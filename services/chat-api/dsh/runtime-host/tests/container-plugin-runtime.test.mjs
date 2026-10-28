import assert from 'node:assert/strict'
import test from 'node:test'

import { rewritePluginProfile } from '../src/container-plugin-runtime.mjs'

test('container profile only receives scoped relay credentials', () => {
  const original = {
    gatewayUrl: 'http://chat-api:8000/internal/dsh/model/generate',
    accessToken: 'original-secret',
    toolProfile: {
      gatewayUrl: 'http://chat-api:8000/internal/dsh/tools',
      accessToken: 'tool-secret',
      tools: [],
    },
    bundleGatewayUrl: 'http://chat-api:8000/internal/dsh/skill-bundles',
    pluginGatewayUrl: 'http://chat-api:8000/internal/dsh/plugin-archives',
  }
  const rewritten = rewritePluginProfile(original, { lease_id: 'a'.repeat(32), token: 'scoped-token' })
  assert.equal(rewritten.accessToken, 'scoped-token')
  assert.equal(rewritten.toolProfile.accessToken, 'scoped-token')
  assert.match(rewritten.gatewayUrl, /sandbox-relay\/a{32}\/model$/)
  assert.match(rewritten.toolProfile.gatewayUrl, /sandbox-relay\/a{32}\/tools$/)
  assert.equal(original.accessToken, 'original-secret')
  assert.equal(original.toolProfile.accessToken, 'tool-secret')
})
