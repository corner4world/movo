import assert from 'node:assert/strict'
import test from 'node:test'
import { parseChartPayload } from '../src/components/chat/chartPayload'

test('accepts JSON and compact label/value chart payloads', () => {
  assert.deepEqual(parseChartPayload('{"type":"bar","labels":["A"],"series":[{"name":"S","data":[2]}]}'), {
    type: 'bar',
    labels: ['A'],
    series: [{ name: 'S', data: [2] }],
  })
  assert.deepEqual(parseChartPayload('type: bar\nlabels: ["A", "B"]\nvalues: [2, 3]'), {
    type: 'bar',
    title: 'Chart',
    labels: ['A', 'B'],
    series: [{ name: 'Series', data: [2, 3] }],
  })
})

test('rejects payloads without a chart series', () => {
  assert.equal(parseChartPayload('not a chart'), null)
  assert.equal(parseChartPayload(''), null)
})
