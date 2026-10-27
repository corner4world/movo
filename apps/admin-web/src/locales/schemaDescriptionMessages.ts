export const schemaDescriptionMessages = {
  'schema.childMore': { 'zh-CN': ' 等', 'en-US': ', and others' },
  'schema.childSummary': { 'zh-CN': '，包含 {keys}{more} 子字段', 'en-US': ', with {keys}{more} child fields' },
  'schema.arrayDescription': { 'zh-CN': '数组字段 `{path}`{children}，用于描述列表型响应数据', 'en-US': 'Array field `{path}`{children}, representing list response data' },
  'schema.objectDescription': { 'zh-CN': '对象字段 `{path}`{children}，用于承载结构化响应数据', 'en-US': 'Object field `{path}`{children}, containing structured response data' },
  'schema.fieldMeaning': { 'zh-CN': '，{meaning}', 'en-US': '; {meaning}' },
  'schema.fieldDescription': { 'zh-CN': '响应字段 `{path}`，类型为{type}{meaning}', 'en-US': 'Response field `{path}` of type {type}{meaning}' },
  'schema.pathObjectDescription': { 'zh-CN': '对象字段 `{path}`，主要结果路径中的结构化响应数据', 'en-US': 'Object field `{path}` in the primary result path, containing structured response data' },
} as const
