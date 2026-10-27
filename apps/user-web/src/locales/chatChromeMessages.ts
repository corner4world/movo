export const chatChromeMessages = {
  loadFailed: { zh: '对话界面加载失败。', en: 'The chat view could not load.' },
  reload: { zh: '刷新重试', en: 'Reload' },
  stopping: { zh: '正在停止…', en: 'Stopping…' },
  stop: { zh: '停止', en: 'Stop' },
  send: { zh: '发送', en: 'Send' },
  noModel: { zh: '未配置模型', en: 'No model configured' },
  openTestBrowser: { zh: '打开测试浏览器', en: 'Open test browser' },
  manualTestBrowser: { zh: '打开浏览器进行人工测试', en: 'Open browser for manual testing' },
  testBrowser: { zh: '测试浏览器', en: 'Test browser' },
  evidence: {
    zh: (total: number, fragments: number) => fragments ? `查看依据 · ${total} 个来源 / ${fragments} 个片段` : total ? `查看依据 · ${total} 个来源` : '查看依据',
    en: (total: number, fragments: number) => fragments ? `View sources · ${total} sources / ${fragments} excerpts` : total ? `View sources · ${total}` : 'View sources',
  },
  chartItem: { zh: '项', en: 'Item' },
  chartContent: { zh: '内容', en: 'Content' },
  document: { zh: (kind: string) => `${kind} 文档`, en: (kind: string) => `${kind} Document` },
} as const
