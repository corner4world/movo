import { t } from '../composables/i18n';
import { pathObjectDescription, sampleArrayItem, schemaDescriptionForValue } from './toolSchemaDescriptions';
import type { SchemaType } from './toolSchemaDescriptions';
export type ParamLocation = 'Header' | 'Query' | 'Body' | 'Path'
export type ResponseMode = 'summarized' | 'original' | 'answer'

export interface SchemaNode {
  id: string
  name: string
  description: string
  type: SchemaType
  location?: ParamLocation
  required?: boolean
  responseMode?: ResponseMode
  children?: SchemaNode[]
}

export interface FlatSchemaNode extends SchemaNode {
  depth: number
}


export function createToolSchemaInference(newSchemaNode: (partial?: Partial<SchemaNode>) => SchemaNode) {
function inferSchemaType(value: unknown): SchemaType {
  if (Array.isArray(value)) return 'Array'
  if (value === null || value === undefined) return 'String'
  if (typeof value === 'boolean') return 'Boolean'
  if (typeof value === 'number') return Number.isInteger(value) ? 'Integer' : 'Number'
  if (typeof value === 'object') return 'Object'
  return 'String'
}

function inferNodesFromRecord(record: Record<string, unknown>, prefix = ''): SchemaNode[] {
  return Object.entries(record)
    .filter(([name]) => String(name || '').trim())
    .map(([name, value]) => inferNodeFromValue(name, value, prefix ? `${prefix}.${name}` : name))
}

function inferNodeFromValue(name: string, value: unknown, path = name): SchemaNode {
  const type = inferSchemaType(value)
  const node = newSchemaNode({
    name,
    type,
    location: undefined,
    required: false,
    responseMode: type === 'Object' || type === 'Array' ? 'summarized' : 'original',
    description: schemaDescriptionForValue(name, value, type, path),
    children: [],
  })
  if (type === 'Object' && value && typeof value === 'object' && !Array.isArray(value)) {
    node.children = inferNodesFromRecord(value as Record<string, unknown>, path)
  } else if (type === 'Array' && Array.isArray(value)) {
    const sample = sampleArrayItem(value)
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      node.children = inferNodesFromRecord(sample as Record<string, unknown>, `${path}[]`)
    }
  }
  return node
}

function parseResultPath(path: string): string[] {
  return String(path || '')
    .replace(/\[(\d+)\]/g, '.$1')
    .split('.')
    .map((part) => part.trim())
    .filter(Boolean)
}

function resolvePath(value: unknown, path: string): unknown {
  let current = value
  for (const part of parseResultPath(path)) {
    if (Array.isArray(current)) {
      const index = Number(part)
      if (!Number.isInteger(index) || index < 0 || index >= current.length) return undefined
      current = current[index]
    } else if (current && typeof current === 'object') {
      const record = current as Record<string, unknown>
      if (!(part in record)) return undefined
      current = record[part]
    } else {
      return undefined
    }
  }
  return current
}

function wrapNodesWithResultPath(nodes: SchemaNode[], value: unknown, path: string): SchemaNode[] {
  const parts = parseResultPath(path).filter((part) => !/^\d+$/.test(part))
  if (!parts.length) return nodes
  let childNodes = nodes
  let childValue = value
  for (let index = parts.length - 1; index >= 0; index -= 1) {
    const isLeaf = index === parts.length - 1
    const nodeValue = isLeaf ? childValue : {}
    childNodes = [
      newSchemaNode({
        name: parts[index],
        type: isLeaf ? inferSchemaType(nodeValue) : 'Object',
        location: undefined,
        required: false,
        responseMode: 'summarized',
        description: isLeaf
          ? schemaDescriptionForValue(parts[index], nodeValue, inferSchemaType(nodeValue), parts.slice(0, index + 1).join('.'))
          : pathObjectDescription(parts.slice(0, index + 1).join('.')),
        children: childNodes,
      }),
    ]
    childValue = {}
  }
  return childNodes
}


  return { inferSchemaType, inferNodesFromRecord, inferNodeFromValue, parseResultPath, resolvePath, wrapNodesWithResultPath };
}
