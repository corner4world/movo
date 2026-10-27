export const appLanguageOptions = [
  { value: 'zh' as const, label: '中文' },
  { value: 'en' as const, label: 'English' },
] as const

// Persisted names and request titles are matched exactly for compatibility.
export const personalSpaceName = '个人空间'
export const internalRequestTitles = new Set(['意图路由', 'LLM 调用', 'LLM_Call', '任务规划', '内容生成', '任务执行'])
