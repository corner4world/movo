export const workspaceChoiceMessages = {
  chooseProject: { en: 'Choose a project', zh: '选择已有项目' },
  addOnce: { en: 'Projects only need to be added once.', zh: '项目只需添加一次，后续可直接选择。' },
  loading: { en: 'Loading projects…', zh: '正在加载项目…' },
  empty: { en: 'No projects added yet.', zh: '还没有添加过项目。' },
  unavailable: { en: 'Folder unavailable on this device', zh: '此设备上的目录不可用' },
  addProject: { en: 'Add a new project…', zh: '添加新项目…' },
} as const

export const branchContextMessages = {
  noBranch: { en: (source: string) => `Based on ${source} · no branch`, zh: (source: string) => `基于 ${source} · 未建分支` },
  start: { en: (source: string) => `Start: ${source}`, zh: (source: string) => `起始：${source}` },
  branch: { en: 'Branch', zh: '分支' },
  locked: { en: 'The branch context is fixed after this task starts.', zh: '任务开始后，分支上下文保持固定。' },
  worktree: { en: 'Choose the Worktree starting branch', zh: '选择 Worktree 的起始分支' },
  local: { en: 'Switch or create a local branch', zh: '切换或创建本地分支' },
} as const

export const workspacePreviewMessages = {
  loadingFile: { en: 'Loading…', zh: '正在读取…' },
  binary: { en: 'Binary files cannot be previewed.', zh: '该二进制文件暂不支持预览。' },
  selectFile: { en: 'Select a file to preview it.', zh: '选择文件后在此预览。' },
  truncatedFile: { en: 'Preview truncated for safety.', zh: '文件较大，仅显示安全范围内的内容。' },
  loadingDiff: { en: 'Loading diff…', zh: '正在读取变更…' },
  noDiff: { en: 'No diff is available.', zh: '暂无可显示的变更。' },
  truncatedDiff: { en: 'Diff truncated for safety.', zh: '变更较大，仅显示安全范围内的内容。' },
} as const

export const taskReviewMessages = {
  title: { en: 'This task', zh: '本次任务' },
  files: { en: 'files', zh: '个文件' },
  filter: { en: 'Filter files…', zh: '筛选变更文件…' },
  noMatch: { en: 'No matching files', zh: '没有匹配的文件' },
  loading: { en: 'Loading task diff…', zh: '正在读取本次任务的变更…' },
  select: { en: 'Select a file to review.', zh: '选择文件后查看本次任务的具体变更。' },
  resizePanel: { en: 'Resize panel', zh: '调整面板宽度' },
} as const

export const gitPublishMessages = {
  pushed: { en: 'Committed and pushed', zh: '已提交并推送' },
  committed: { en: 'Committed locally', zh: '已提交到本地' },
  ahead: { en: (count: number | undefined) => `${count} local commit(s) not pushed`, zh: (count: number | undefined) => `有 ${count} 个本地提交尚未推送` },
  noRemote: { en: 'No Git remote is configured', zh: '当前仓库尚未配置远程地址' },
  pushing: { en: 'Pushing…', zh: '正在推送…' },
  retry: { en: 'Retry push', zh: '重新推送' },
  push: { en: 'Push', zh: '推送' },
} as const

export const taskChangeCardMessages = {
  undone: { en: 'Changes undone', zh: '已撤销本次变更' },
  edited: { en: (count: number) => `Edited ${count} file(s)`, zh: (count: number) => `已更新 ${count} 个文件` },
  undoing: { en: 'Undoing…', zh: '正在撤销…' },
  confirmUndo: { en: 'Confirm undo', zh: '确认撤销' },
  undo: { en: 'Undo', zh: '撤销' },
  review: { en: 'Review', zh: '评审' },
  showLess: { en: 'Show less', zh: '收起' },
  showMore: { en: (count: number) => `Show ${count} more`, zh: (count: number) => `再显示 ${count} 个文件` },
} as const
