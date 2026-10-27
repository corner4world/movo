export const chatRuntimeMessages = {
  enterpriseQuota: {
    zh: '当前企业分派额度已用尽，请联系企业管理员调整额度。',
    en: 'The enterprise allocation is exhausted. Contact your enterprise administrator to adjust the allocation.',
  },
  personalQuota: {
    zh: '个人赠送额度已用尽，请升级或切换到有可用额度的空间。',
    en: 'Your complimentary personal allocation is exhausted. Upgrade or switch to a space with available balance.',
  },
  uploadFailed: { zh: '附件上传失败', en: 'Failed to upload attachments' },
  recovering: { zh: '连接中断，正在恢复进度', en: 'Connection interrupted, recovering progress' },
  admissionDenied: {
    zh: '当前任务被准入规则拦截，请联系管理员。',
    en: 'This topic is outside the allowed scope. Contact your administrator to update the topic rules.',
  },
  requestFailed: { zh: '请求失败', en: 'Request failed' },
} as const
