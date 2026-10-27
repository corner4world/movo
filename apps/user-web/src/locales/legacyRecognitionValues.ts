// These values recognize historical Chinese input and generated descriptions.
export const browserAutomationKeywords = [
  '浏览器', '打开网站', '打开网页', '进入后台', '登录后台', '网页操作',
  '草稿箱', '公众号后台', '知乎', '小红书', '淘宝', '京东',
] as const

export const generatedSchemaPrefixes = [
  '响应字段 `', '对象字段 `', '数组字段 `',
  'Response field `', 'Object field `', 'Array field `',
] as const

export const timeoutMessagePattern = /timeout|timed out|超时/i
export const tableTargetNumberPattern = /\d+(?:\.\d+)?(?:天|年|月|日|个|次|%|元)?/g
export const internalKnowledgeBaseName = { zh: '内部知识库', en: 'internal knowledge base' } as const

export const scheduledTaskErrorKeys: Record<string, string> = {
  '目标会话无效': 'scheduled.error.invalidSession',
  '目标会话不存在或无权访问': 'scheduled.error.sessionUnavailable',
  '定时任务不存在': 'scheduled.error.jobMissing',
  '任务已在本次时间点触发': 'scheduled.error.alreadyTriggered',
  '单次任务的执行时间不能早于当前时间': 'scheduled.error.pastTime',
  '固定会话模式必须选择目标会话': 'scheduled.error.sessionRequired',
  '每周任务必须选择有效星期': 'scheduled.error.weekdayRequired',
}
