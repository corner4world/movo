export const skillDependencyMessages = {
  'skillDeps.preparing': { 'zh-CN': '正在准备 Skill 依赖，完成后即可在对话中使用。', 'en-US': 'Preparing Skill dependencies. The Skill will be ready for chat when this finishes.' },
  'skillDeps.ready': { 'zh-CN': 'Skill 依赖已准备完成，可以使用。', 'en-US': 'Skill dependencies are ready.' },
  'skillDeps.failed': { 'zh-CN': 'Skill 依赖准备失败。请检查沙箱管理服务日志后重新安装。', 'en-US': 'Skill dependency preparation failed. Check sandbox manager logs and reinstall.' },
  'skillDeps.unavailable': { 'zh-CN': '暂时无法确认 Skill 依赖状态，请稍后重试。', 'en-US': 'Skill dependency status is temporarily unavailable. Try again later.' },
  'skillDeps.disabled': { 'zh-CN': '沙箱模式未启用，自动依赖安装不可用。', 'en-US': 'Sandbox mode is disabled; automatic dependency installation is unavailable.' },
} as const;
