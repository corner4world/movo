export const toolActivationMessages = {
  'shortcuts.skillPromptDefault': { zh: '请使用 Skill「{name}」完成以下任务：', en: 'Use the Skill “{name}” to complete this task:' },
  'toolActivation.selectRequired': { zh: '请先选择允许 Agent 使用的 MCP 工具，最多 {limit} 个。', en: 'Select MCP tools for the Agent first, up to {limit} tools.' },
  'toolActivation.overLimit': { zh: 'MCP 已选择 {count} 个工具，超过上限 {limit} 个，请减少后再启用。', en: '{count} MCP tools are selected, exceeding the limit of {limit}. Remove some before enabling.' },
  'toolActivation.selectionLimit': { zh: '最多只能选择 {limit} 个 MCP 工具。', en: 'You can select at most {limit} MCP tools.' },
  'toolActivation.unnamed': { zh: '未命名工具', en: 'Unnamed tool' },
  'toolActivation.enableConfirm': { zh: '确认启用「{name}」吗？启用后会参与 Agent / Skill 的工具选择。', en: 'Enable “{name}”? Agents and Skills will be able to select it.' },
  'toolActivation.disableConfirm': { zh: '确认禁用「{name}」吗？禁用后 Agent / Skill 将无法继续调用。', en: 'Disable “{name}”? Agents and Skills will no longer be able to call it.' },
} as const
