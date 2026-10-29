export const skillDependencyMessages = {
  'skillDeps.status.preparing': { zh: '环境准备中', en: 'Preparing environment' },
  'skillDeps.status.ready': { zh: '环境已就绪', en: 'Environment ready' },
  'skillDeps.status.failed': { zh: '环境准备失败', en: 'Environment failed' },
  'skillDeps.status.unavailable': { zh: '环境状态不可用', en: 'Environment unavailable' },
  'skillDeps.status.disabled': { zh: '环境不可用', en: 'Environment disabled' },
  'skillDeps.retry': { zh: '重试准备', en: 'Retry preparation' },
  'skillDeps.preparing': { zh: '正在准备 Skill 依赖，完成后即可在对话中使用。', en: 'Preparing Skill dependencies. The Skill will be ready for chat when this finishes.' },
  'skillDeps.ready': { zh: 'Skill 依赖已准备完成，可以使用。', en: 'Skill dependencies are ready.' },
  'skillDeps.failed': { zh: 'Skill 依赖准备失败。请联系管理员检查沙箱服务日志并重试安装。', en: 'Skill dependency preparation failed. Ask an administrator to check sandbox logs and retry installation.' },
  'skillDeps.unavailable': { zh: '暂时无法确认 Skill 依赖状态，请稍后重试。', en: 'Skill dependency status is temporarily unavailable. Try again later.' },
  'skillDeps.disabled': { zh: '沙箱模式未启用，自动依赖安装不可用。', en: 'Sandbox mode is disabled; automatic dependency installation is unavailable.' },
} as const
