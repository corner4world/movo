// Verbatim matches for historical provider names and server messages.
export const qwenNameFragment = '通义';
export const customProviderNameFragment = '自定义';
export const timeoutMessagePattern = /timeout|timed out|超时/i;

export const accountRoleValues = {
  platformAdmin: '平台管理员',
  organizationAdmin: '组织管理员',
  auditor: '审计员',
  operator: '运营人员',
} as const;

export const legacyEnglishRoleValues: Record<string, string> = {
  'Platform Admin': accountRoleValues.platformAdmin,
  'Organization Admin': accountRoleValues.organizationAdmin,
  Auditor: accountRoleValues.auditor,
  Operator: accountRoleValues.operator,
};

export const dashboardMessagePatterns = {
  toolConnections: /^(\d+) 个工具连接需要检查。$/,
  toolsUntested: /^(\d+) 个工具尚未测试连通性。$/,
  modelsFailed: /^(\d+) 个模型最近测试失败。$/,
  callsFailed: /^(\d+) 次调用失败，建议查看 Token 统计。$/,
} as const;

const generatedDescriptions = new Set([
  '测试响应字段',
  '测试响应中的对象字段',
  '测试响应中的数组字段',
  '测试响应中的数组字段，子项结构来自样例数据',
  '主要结果路径中的对象字段',
  'Object field in the primary result path',
]);
const generatedDescriptionPrefixes = [
  '响应字段 `', '对象字段 `', '数组字段 `',
  'Response field `', 'Object field `', 'Array field `',
];

export function isLegacyGeneratedDescription(text: string): boolean {
  return generatedDescriptions.has(text) || generatedDescriptionPrefixes.some((prefix) => text.startsWith(prefix));
}
