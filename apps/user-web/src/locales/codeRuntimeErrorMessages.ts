export const codeRuntimeErrorMessages = {
  permissions: {
    zh: '自定义权限配置无效。请打开 config.toml 检查三个设置项，保存后重试。',
    en: 'Invalid custom permissions. Open config.toml, check the three settings, save, and retry.',
  },
  restoring: {
    zh: '此会话正在恢复中，请稍后重试。若问题持续，请重启桌面端。',
    en: 'This task is already being restored. Retry shortly; restart the desktop app if it persists.',
  },
  otherDevice: {
    zh: '此项目会话绑定在另一台桌面设备。历史记录可查看，但请回到原设备继续执行。',
    en: 'This project task is bound to another desktop device. History remains readable; continue on the original device.',
  },
  missingFolder: {
    zh: '原项目目录已丢失或不可访问。历史记录仍可查看；请恢复原目录后重试。',
    en: 'The original project folder is missing or unavailable. History remains readable; restore the folder and retry.',
  },
  incompatibleProfile: {
    zh: '当前 DSH Runtime Profile 与该历史会话不兼容。为保护原会话，系统未自动切换执行环境。',
    en: 'The current DSH Runtime Profile is incompatible with this historical task. Execution was not silently moved.',
  },
  runtimeUnavailable: {
    zh: '本地 DSH Runtime 当前不可用。历史记录仍可查看，请恢复桌面 Runtime 后重试。',
    en: 'The local DSH Runtime is unavailable. History remains readable; restore the desktop Runtime and retry.',
  },
  taskUnavailable: {
    zh: '本地 Code 会话暂时不可用。',
    en: 'The local Code task is unavailable.',
  },
} as const
