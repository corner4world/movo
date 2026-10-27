import type { DshWorkspaceSummary } from '../../platform/types'
import { commitSuggestionMessages } from '../../locales/codePresentationMessages'

function displayPath(path: string): string {
  const parts = path.split('/').filter(Boolean)
  return parts.at(-1) || path
}

export function suggestCommitMessage(summary: DshWorkspaceSummary, locale: 'zh' | 'en' = 'zh'): string {
  const copy = (key: keyof typeof commitSuggestionMessages, values: Record<string, string | number>) =>
    commitSuggestionMessages[key][locale].replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? `{${name}}`))
  const changes = summary.changes
  if (!changes.length) return ''
  const first = displayPath(changes[0].path)
  const added = changes.filter(item => item.status === '??' || item.status.includes('A')).length
  const deleted = changes.filter(item => item.status.includes('D')).length
  const onlyAdded = added === changes.length
  const onlyDeleted = deleted === changes.length

  if (changes.length === 1) {
    if (onlyAdded) return copy('addOne', { name: first })
    if (onlyDeleted) return copy('removeOne', { name: first })
    return copy('updateOne', { name: first })
  }
  if (onlyAdded) return copy('addMany', { count: changes.length })
  if (onlyDeleted) return copy('removeMany', { count: changes.length })
  return copy('updateMany', { name: first, count: changes.length, related: changes.length - 1 })
}
