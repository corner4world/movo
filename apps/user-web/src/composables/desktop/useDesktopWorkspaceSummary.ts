import { ref, watch } from 'vue'
import { getDshWorkspaceSummary } from '../../platform'
import type { DshTaskChangeSet, DshWorkspaceSummary } from '../../platform/types'

type WorkspaceSummaryOptions = {
  codeInspector: boolean
  sessionId: () => string | undefined
  eventCount: () => number
  latestEvent: () => { item_kind?: string; type?: string } | undefined
}

export function useDesktopWorkspaceSummary(options: WorkspaceSummaryOptions) {
  const reviewPath = ref('')
  const reviewChanges = ref<DshTaskChangeSet | null>(null)
  const filePath = ref('')
  const summary = ref<DshWorkspaceSummary | null>(null)

  function clearSelection(): void {
    reviewPath.value = ''
    reviewChanges.value = null
    filePath.value = ''
  }

  async function refresh(): Promise<void> {
    const sessionId = options.sessionId()
    if (!sessionId || !options.codeInspector) return
    try { summary.value = await getDshWorkspaceSummary(sessionId) }
    catch { /* Retain the last known summary on transient failures. */ }
  }

  let workspaceSummaryRequest = 0
  watch(options.sessionId, async (sessionId) => {
    const request = ++workspaceSummaryRequest
    clearSelection()
    summary.value = null
    if (!sessionId || !options.codeInspector) return
    try {
      const next = await getDshWorkspaceSummary(sessionId)
      if (request === workspaceSummaryRequest) summary.value = next
    } catch { /* The unavailable capability stays hidden. */ }
  }, { immediate: true })

  watch(options.eventCount, async (length, previous) => {
    const sessionId = options.sessionId()
    if (!sessionId || length <= previous) return
    const latest = options.latestEvent()
    if (latest?.item_kind !== 'tool' || !['item.completed', 'item.failed'].includes(latest.type || '')) return
    try { summary.value = await getDshWorkspaceSummary(sessionId) }
    catch { /* Retain the last known summary on transient failures. */ }
  })

  return { reviewPath, reviewChanges, filePath, summary, clearSelection, refresh }
}
