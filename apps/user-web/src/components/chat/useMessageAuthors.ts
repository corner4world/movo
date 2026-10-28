import { computed, ref, watch } from 'vue'
import type { ChatMessageAuthor } from '../../api/sessions'
import { listSessionParticipants } from '../../api/sessionSharing'
import { t } from '../../composables/i18n'

type AuthorMessage = {
  role: 'user' | 'assistant'
  user_id?: string
  author?: ChatMessageAuthor | null
}

type MessageAuthorOptions = {
  sessionId: () => string | undefined
  userId: () => string | undefined
  foreignRunInitiatorId: () => string | undefined
}

export function useMessageAuthors(options: MessageAuthorOptions) {
  const memberNamesBySession = ref(new Map<string, Map<string, string>>())
  let participantsFetchSequence = 0

  watch(options.sessionId, (sessionId) => {
    if (!sessionId || memberNamesBySession.value.has(sessionId)) return
    const sequence = ++participantsFetchSequence
    void (async () => {
      const result = await listSessionParticipants(sessionId)
      if (sequence !== participantsFetchSequence || result.ok === false) return
      const names = new Map<string, string>()
      for (const item of result.data.items) names.set(item.user_id, item.display_name)
      memberNamesBySession.value.set(sessionId, names)
    })()
  }, { immediate: true })

  function isOwnMessage(message: AuthorMessage): boolean {
    const userId = options.userId()
    return !message.user_id || !userId || message.user_id === userId
  }

  function authorLabel(message: AuthorMessage): string {
    if (message.role !== 'user' || isOwnMessage(message)) return ''
    const sessionId = options.sessionId()
    const known = sessionId ? memberNamesBySession.value.get(sessionId)?.get(message.user_id || '') : undefined
    return known?.trim() || t('session.share.unknown_member')
  }

  function sharedAuthorName(message: AuthorMessage): string | null {
    const projected = message.author?.display_name?.trim()
    if (projected) return projected
    const id = message.user_id || ''
    const sessionId = options.sessionId()
    const known = sessionId ? memberNamesBySession.value.get(sessionId)?.get(id)?.trim() : undefined
    return known || (id ? id.slice(0, 8) : null)
  }

  function sharedAuthorAvatar(message: AuthorMessage): string | null {
    return message.author?.avatar_url ?? null
  }

  const foreignRunSpeakerName = computed(() => {
    const sessionId = options.sessionId()
    const id = options.foreignRunInitiatorId() || ''
    const known = sessionId ? memberNamesBySession.value.get(sessionId)?.get(id)?.trim() : ''
    return known || t('session.run.another_member')
  })

  return { isOwnMessage, authorLabel, sharedAuthorName, sharedAuthorAvatar, foreignRunSpeakerName }
}
