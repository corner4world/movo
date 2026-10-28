import { ref } from 'vue'
import type { EvidenceBundleItem, EvidenceSourceItem } from '../../features/execution-v3/domain/delivery'
import type { ExecutionStoreV3 } from '../../features/execution-v3/stores/executionStore'
import { evidenceSourceStats } from '../../features/execution-v3/domain/evidenceSourceGroups'
import { mergeEvidenceBundles } from '../../composables/evidenceBundles'
import { t, useLocale } from '../../composables/i18n'
import { chatChromeMessages } from '../../locales/chatChromeMessages'

export function useEvidenceViewer<Message extends { content: string }>(options: {
  store: (message: Message) => ExecutionStoreV3
  isGenerating: (index: number, message: Message) => boolean
}) {
  const { locale } = useLocale()
  const activeEvidenceBundle = ref<EvidenceBundleItem | null>(null)
  const activeKnowledgeSourceBundle = ref<EvidenceBundleItem | null>(null)
  const evidenceDrawerOpen = ref(false)
  const knowledgeSourceViewerOpen = ref(false)

  function latestEvidenceBundle(message: Message): EvidenceBundleItem | null {
    return mergeEvidenceBundles(options.store(message).state.evidenceBundles)
  }

  function shouldShowEvidenceTrigger(index: number, message: Message): boolean {
    return Boolean(
      latestEvidenceBundle(message) &&
      String(message.content || '').trim() &&
      !options.isGenerating(index, message),
    )
  }

  function evidenceTriggerTextForMessage(message: Message): string {
    const bundle = latestEvidenceBundle(message)
    if (!bundle) return t('evidence.view')
    const stats = evidenceSourceStats(bundle.sources)
    return chatChromeMessages.evidence[locale.value](stats.total, stats.fragments)
  }

  function openLatestEvidenceDrawer(message: Message): void {
    const bundle = latestEvidenceBundle(message)
    if (!bundle) return
    activeEvidenceBundle.value = bundle
    evidenceDrawerOpen.value = true
  }

  function closeEvidenceDrawer(): void {
    evidenceDrawerOpen.value = false
  }

  function closeKnowledgeSourceViewer(): void {
    knowledgeSourceViewerOpen.value = false
    activeKnowledgeSourceBundle.value = null
  }

  function openKnowledgeSourceFromDrawer(source: EvidenceSourceItem): void {
    const bundle = activeEvidenceBundle.value
    if (!bundle || !source.document_id || !source.chunk_id) return
    activeKnowledgeSourceBundle.value = {
      ...bundle,
      id: `${bundle.id}_${source.id || source.chunk_id}_${Date.now()}`,
      sources: bundle.sources.filter(item => (
        item.document_id === source.document_id && Boolean(item.chunk_id)
      )),
    }
    knowledgeSourceViewerOpen.value = true
  }

  return {
    activeEvidenceBundle,
    activeKnowledgeSourceBundle,
    evidenceDrawerOpen,
    knowledgeSourceViewerOpen,
    shouldShowEvidenceTrigger,
    evidenceTriggerTextForMessage,
    openLatestEvidenceDrawer,
    closeEvidenceDrawer,
    closeKnowledgeSourceViewer,
    openKnowledgeSourceFromDrawer,
  }
}
