export const scheduledTaskErrorMessages = {
  'scheduled.autoSent': { zh: '定时任务自动发送', en: 'Sent automatically by scheduled task' },
  'scheduled.error.invalidSession': { zh: '目标会话无效', en: 'Invalid target session' },
  'scheduled.error.sessionUnavailable': { zh: '目标会话不存在或无权访问', en: 'The target session is unavailable or you do not have access' },
  'scheduled.error.jobMissing': { zh: '定时任务不存在', en: 'Scheduled task not found' },
  'scheduled.error.alreadyTriggered': { zh: '任务已在本次时间点触发', en: 'This task has already run at the scheduled time' },
  'scheduled.error.pastTime': { zh: '单次任务的执行时间不能早于当前时间', en: 'The run time must be in the future' },
  'scheduled.error.sessionRequired': { zh: '固定会话模式必须选择目标会话', en: 'Choose a target session for fixed session mode' },
  'scheduled.error.weekdayRequired': { zh: '每周任务必须选择有效星期', en: 'Choose at least one valid weekday' },
} as const
