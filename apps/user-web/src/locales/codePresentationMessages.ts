export const changeStatusMessages = {
  untracked: { zh: '尚未被 Git 跟踪的新文件', en: 'Untracked file' },
  conflict: { zh: '存在尚未解决的合并冲突', en: 'Merge conflict' },
  deleted: { zh: '已删除的文件', en: 'Deleted file' },
  renamed: { zh: '已重命名的文件', en: 'Renamed file' },
  added: { zh: '已添加到 Git 的新文件', en: 'Added file' },
  modified: { zh: '内容已修改的文件', en: 'Modified file' },
  changed: { zh: '变更', en: 'Changed' },
  changedFile: { zh: '发生变更的文件', en: 'Changed file' },
} as const

export const commitSuggestionMessages = {
  addOne: { zh: '新增 {name}', en: 'Add {name}' },
  removeOne: { zh: '删除 {name}', en: 'Remove {name}' },
  updateOne: { zh: '更新 {name}', en: 'Update {name}' },
  addMany: { zh: '新增 {count} 个项目文件', en: 'Add {count} project files' },
  removeMany: { zh: '删除 {count} 个旧文件', en: 'Remove {count} obsolete files' },
  updateMany: { zh: '更新 {name} 等 {count} 个文件', en: 'Update {name} and {related} related files' },
} as const

export const durationMessages = {
  hours: { zh: '{hours}小时{minutes}分{seconds}秒', en: '{hours}h {minutes}m {seconds}s' },
  minutes: { zh: '{minutes}分{seconds}秒', en: '{minutes}m {seconds}s' },
  seconds: { zh: '{seconds}秒', en: '{seconds}s' },
} as const
