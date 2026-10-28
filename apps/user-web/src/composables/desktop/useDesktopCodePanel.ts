import type { Ref } from 'vue'
import type { DshTaskChangeSet } from '../../platform/types'

type CodePanelMode = 'changes' | 'files' | 'terminal'

export function useDesktopCodePanel(options: {
  activeKind: () => string | null | undefined
  hasSession: () => boolean
  reviewPath: Ref<string>
  reviewChanges: Ref<DshTaskChangeSet | null>
  filePath: Ref<string>
  hide: () => void
  reveal: (mode: CodePanelMode) => void
  openFile: (path: string) => void
  openDiff: (path: string, changes: DshTaskChangeSet) => void
}) {
  function clearSelection(): void {
    options.reviewPath.value = ''
    options.reviewChanges.value = null
    options.filePath.value = ''
  }

  function toggle(mode: CodePanelMode): void {
    if (options.activeKind() === mode) {
      options.hide()
      return
    }
    clearSelection()
    options.reveal(mode)
  }

  function reviewChanges(changes: DshTaskChangeSet, path?: string): void {
    if (!options.hasSession()) return
    options.reviewChanges.value = changes
    options.reviewPath.value = path || ''
    options.filePath.value = ''
    if (path) options.openDiff(path, changes)
    else options.reveal('changes')
  }

  function openFile(path: string): void {
    if (!options.hasSession()) return
    options.reviewChanges.value = null
    options.reviewPath.value = ''
    options.filePath.value = path
    options.openFile(path)
  }

  return { toggle, reviewChanges, openFile }
}
