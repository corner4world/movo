import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { searchSessions, type SessionSearchResult } from '../api/sessions'

type SessionSearchOptions = {
  getUserId: () => string | null
  getMainId: () => string
  authToken: Ref<string>
}

export function useSessionSearch({ getUserId, getMainId, authToken }: SessionSearchOptions) {
  const sessionSearchOpen = ref(false)
  const sessionSearchQuery = ref('')
  const sessionSearchResults = ref<SessionSearchResult[]>([])
  const sessionSearchLoading = ref(false)
  const sessionSearchHasMore = ref(false)
  const sessionSearchDidRun = ref(false)
  const trimmedSessionSearchQuery = computed(() => sessionSearchQuery.value.trim())
  const sessionSearchPageSize = 20
  let sessionSearchTimer: ReturnType<typeof setTimeout> | null = null

  function closeSessionSearch() {
    sessionSearchOpen.value = false
    sessionSearchQuery.value = ''
    sessionSearchResults.value = []
    sessionSearchHasMore.value = false
    sessionSearchLoading.value = false
    sessionSearchDidRun.value = false
  }

  async function runSessionSearch(reset = true) {
    const userId = getUserId()
    const queryText = trimmedSessionSearchQuery.value
    if (!userId || !queryText) {
      sessionSearchResults.value = []
      sessionSearchHasMore.value = false
      sessionSearchDidRun.value = false
      sessionSearchLoading.value = false
      return
    }
    sessionSearchLoading.value = true
    try {
      const page = await searchSessions(userId, getMainId(), queryText, {
        limit: sessionSearchPageSize,
        offset: reset ? 0 : sessionSearchResults.value.length,
      }, authToken.value || null)
      sessionSearchResults.value = reset ? page.items : [...sessionSearchResults.value, ...page.items]
      sessionSearchHasMore.value = page.has_more
      sessionSearchDidRun.value = true
    } finally {
      sessionSearchLoading.value = false
    }
  }

  function scheduleSessionSearch() {
    if (sessionSearchTimer) {
      clearTimeout(sessionSearchTimer)
      sessionSearchTimer = null
    }
    const queryText = trimmedSessionSearchQuery.value
    if (!queryText) {
      sessionSearchResults.value = []
      sessionSearchHasMore.value = false
      sessionSearchDidRun.value = false
      sessionSearchLoading.value = false
      return
    }
    sessionSearchTimer = setTimeout(() => {
      runSessionSearch(true).catch(() => {
        sessionSearchLoading.value = false
      })
    }, 250)
  }

  watch(sessionSearchQuery, scheduleSessionSearch)

  onBeforeUnmount(() => {
    if (sessionSearchTimer) clearTimeout(sessionSearchTimer)
  })

  return {
    sessionSearchOpen, sessionSearchQuery, sessionSearchResults,
    sessionSearchLoading, sessionSearchHasMore, sessionSearchDidRun,
    trimmedSessionSearchQuery, closeSessionSearch, runSessionSearch,
  }
}
