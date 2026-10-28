import { t, useLocale } from '@/composables/i18n';
import { isLegacyGeneratedDescription } from '@/locales/legacyRecognitionValues';
export type SchemaType = 'String' | 'Integer' | 'Number' | 'Boolean' | 'Object' | 'Array' | 'ArrayObject';
export type ParamLocation = 'Header' | 'Query' | 'Body' | 'Path';
export type ResponseMode = 'summarized' | 'original' | 'answer';

export interface SchemaNode {
  id: string;
  name: string;
  description: string;
  type: SchemaType;
  location?: ParamLocation;
  required?: boolean;
  responseMode?: ResponseMode;
  children?: SchemaNode[];
}

export interface FlatInputNode extends SchemaNode {
  depth: number;
}


export function createToolSchemaInference(newSchemaNode: (partial?: Partial<SchemaNode>) => SchemaNode) {
function normalizeType(value: unknown): SchemaType {
  return ['String', 'Integer', 'Number', 'Boolean', 'Object', 'Array', 'ArrayObject'].includes(String(value))
    ? String(value) as SchemaType
    : 'String';
}

function normalizeLocation(value: unknown): ParamLocation {
  return ['Header', 'Query', 'Body', 'Path'].includes(String(value)) ? String(value) as ParamLocation : 'Query';
}

function normalizeResponseMode(value: unknown): ResponseMode {
  return ['summarized', 'original', 'answer'].includes(String(value)) ? String(value) as ResponseMode : 'summarized';
}

function inferSchemaType(value: unknown): SchemaType {
  if (Array.isArray(value)) return 'Array';
  if (value === null || value === undefined) return 'String';
  if (typeof value === 'boolean') return 'Boolean';
  if (typeof value === 'number') return Number.isInteger(value) ? 'Integer' : 'Number';
  if (typeof value === 'object') return 'Object';
  return 'String';
}

function readableType(type: SchemaType) {
  const labels: Record<SchemaType, string> = {
    String: t('legacy.text_f1573e7'),
    Integer: t('legacy.integer_2a59217'),
    Number: t('legacy.number_5c785eb'),
    Boolean: t('legacy.boolean_0defa35'),
    Object: t('legacy.object_7db0748'),
    Array: t('legacy.array_d166572'),
    ArrayObject: t('legacy.array_of_objects'),
  };
  return labels[type] || type;
}

function splitFieldTokens(value: string) {
  return String(value || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .split(/[^a-zA-Z0-9]+/)
    .map((part) => part.toLowerCase())
    .filter(Boolean);
}

function commonFieldMeaning(name: string, path: string) {
  const tokens = splitFieldTokens(`${path}_${name}`);
  const tokenSet = new Set(tokens);
  const joined = tokens.join('_');
  if (tokenSet.has('id') || joined.endsWith('_id')) return t('legacy.usually_identifies_a_record_or_entity');
  if (tokenSet.has('name')) return t('legacy.usually_represents_a_name');
  if (tokenSet.has('title')) return t('legacy.usually_represents_a_title');
  if (tokenSet.has('status') || tokenSet.has('state')) return t('legacy.usually_represents_a_status');
  if (tokenSet.has('type') || tokenSet.has('category')) return t('legacy.usually_represents_a_type_or_category');
  if (tokenSet.has('count') || tokenSet.has('total') || tokenSet.has('num') || tokenSet.has('quantity')) return t('legacy.usually_represents_a_count_or_metric');
  if (tokenSet.has('amount') || tokenSet.has('price') || tokenSet.has('cost') || tokenSet.has('fee')) return t('legacy.usually_represents_an_amount_or_price');
  if (tokenSet.has('date') || tokenSet.has('time') || tokenSet.has('created') || tokenSet.has('updated')) return t('legacy.usually_represents_a_date_or_time');
  if (tokenSet.has('url') || tokenSet.has('link') || tokenSet.has('uri')) return t('legacy.usually_represents_a_link_or_address');
  if (tokenSet.has('desc') || tokenSet.has('description') || tokenSet.has('summary')) return t('legacy.usually_represents_a_description_or_summary');
  if (tokenSet.has('content') || tokenSet.has('text')) return t('legacy.usually_represents_body_content');
  if (tokenSet.has('message') || tokenSet.has('msg')) return t('legacy.usually_represents_message_text');
  if (tokenSet.has('code')) return t('legacy.usually_represents_a_code_or_return_code');
  if (tokenSet.has('score') || tokenSet.has('rate') || tokenSet.has('ratio')) return t('legacy.usually_represents_a_score_ratio_or_rating');
  return '';
}

function childFieldSummary(value: unknown) {
  let record: Record<string, unknown> | null = null;
  if (Array.isArray(value)) {
    const sample = sampleArrayItem(value);
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      record = sample as Record<string, unknown>;
    }
  } else if (value && typeof value === 'object') {
    record = value as Record<string, unknown>;
  }
  if (!record) return '';
  const keys = Object.keys(record).filter(Boolean).slice(0, 6);
  if (!keys.length) return '';
  const separator = useLocale().locale.value === 'zh-CN' ? '、' : ', ';
  const more = Object.keys(record).length > keys.length ? t('schema.childMore') : '';
  return t('schema.childSummary', { keys: keys.join(separator), more });
}

function schemaDescriptionForValue(name: string, value: unknown, path = name) {
  const type = inferSchemaType(value);
  const fieldPath = path || name;
  const meaning = commonFieldMeaning(name, fieldPath);
  if (Array.isArray(value)) {
    return t('schema.arrayDescription', { path: fieldPath, children: childFieldSummary(value) });
  }
  if (value && typeof value === 'object') {
    return t('schema.objectDescription', { path: fieldPath, children: childFieldSummary(value) });
  }
  return t('schema.fieldDescription', { path: fieldPath, type: readableType(type), meaning: meaning ? t('schema.fieldMeaning', { meaning }) : '' });
}

function isAutoGeneratedDescription(value: unknown) {
  const text = String(value || '').trim();
  if (!text) return true;
  return isLegacyGeneratedDescription(text);
}

function sampleArrayItem(values: unknown[]): unknown {
  const objectItems = values.filter((item) => item && typeof item === 'object' && !Array.isArray(item));
  if (!objectItems.length) return values.find((item) => item !== null && item !== undefined);
  return objectItems.slice(0, 10).reduce<Record<string, unknown>>((merged, item) => {
    Object.assign(merged, item as Record<string, unknown>);
    return merged;
  }, {});
}

function inferNodesFromRecord(record: Record<string, unknown>, prefix = ''): SchemaNode[] {
  return Object.entries(record)
    .filter(([name]) => String(name || '').trim())
    .map(([name, value]) => inferNodeFromValue(name, value, prefix ? `${prefix}.${name}` : name));
}

function inferNodeFromValue(name: string, value: unknown, path = name): SchemaNode {
  const type = inferSchemaType(value);
  const node = newSchemaNode({
    name,
    type,
    location: undefined,
    required: false,
    responseMode: type === 'Object' || type === 'Array' ? 'summarized' : 'original',
    description: schemaDescriptionForValue(name, value, path),
    children: [],
  });
  if (type === 'Object' && value && typeof value === 'object' && !Array.isArray(value)) {
    node.children = inferNodesFromRecord(value as Record<string, unknown>, path);
  } else if (type === 'Array' && Array.isArray(value)) {
    const sample = sampleArrayItem(value);
    if (sample && typeof sample === 'object' && !Array.isArray(sample)) {
      node.children = inferNodesFromRecord(sample as Record<string, unknown>, `${path}[]`);
    }
  }
  return node;
}

function parseResultPath(path: string): string[] {
  return String(path || '')
    .replace(/\[(\d+)\]/g, '.$1')
    .split('.')
    .map((part) => part.trim())
    .filter(Boolean);
}

function resolvePath(value: unknown, path: string): unknown {
  let current = value;
  for (const part of parseResultPath(path)) {
    if (Array.isArray(current)) {
      const index = Number(part);
      if (!Number.isInteger(index) || index < 0 || index >= current.length) return undefined;
      current = current[index];
    } else if (current && typeof current === 'object') {
      const record = current as Record<string, unknown>;
      if (!(part in record)) return undefined;
      current = record[part];
    } else {
      return undefined;
    }
  }
  return current;
}

function wrapNodesWithResultPath(nodes: SchemaNode[], value: unknown, path: string): SchemaNode[] {
  const parts = parseResultPath(path).filter((part) => !/^\d+$/.test(part));
  if (!parts.length) return nodes;
  let childNodes = nodes;
  let childValue = value;
  for (let index = parts.length - 1; index >= 0; index -= 1) {
    const isLeaf = index === parts.length - 1;
    const nodeValue = isLeaf ? childValue : {};
    childNodes = [
      newSchemaNode({
        name: parts[index],
        type: isLeaf ? inferSchemaType(nodeValue) : 'Object',
        location: undefined,
        required: false,
        responseMode: 'summarized',
        description: isLeaf
          ? schemaDescriptionForValue(parts[index], nodeValue, parts.slice(0, index + 1).join('.'))
          : t('schema.pathObjectDescription', { path: parts.slice(0, index + 1).join('.') }),
        children: childNodes,
      }),
    ];
  }
  return childNodes;
}


  return { readableType, normalizeType, normalizeLocation, normalizeResponseMode, inferSchemaType, splitFieldTokens, commonFieldMeaning, childFieldSummary, schemaDescriptionForValue, isAutoGeneratedDescription, sampleArrayItem, inferNodesFromRecord, inferNodeFromValue, parseResultPath, resolvePath, wrapNodesWithResultPath };
}
