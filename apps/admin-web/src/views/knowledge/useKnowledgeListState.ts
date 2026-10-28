import type { Ref } from 'vue';

const LIST_STATE_CACHE_KEY = 'askai:knowledge-documents:list-state';

export function useKnowledgeListState(context: { selectedDirKeys: Ref<string[]>; pagination: { page: number; pageSize: number }; filters: { searchScope: 'current' | 'all' } }) {
  const { selectedDirKeys, pagination, filters } = context;

function persistListState() {
  try {
    window.localStorage.setItem(
      LIST_STATE_CACHE_KEY,
      JSON.stringify({
        selectedDirKey: selectedDirKeys.value[0] || 'root',
        page: pagination.page,
        pageSize: pagination.pageSize,
        searchScope: filters.searchScope,
      }),
    );
  } catch {
    // localStorage can be unavailable in restricted browser modes.
  }
}

function restoreListState() {
  try {
    const raw = window.localStorage.getItem(LIST_STATE_CACHE_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw) as { selectedDirKey?: unknown; page?: unknown; pageSize?: unknown; searchScope?: unknown };
    const selectedDirKey = typeof parsed.selectedDirKey === 'string' && parsed.selectedDirKey ? parsed.selectedDirKey : 'root';
    const page = Number(parsed.page);
    const pageSize = Number(parsed.pageSize);
    selectedDirKeys.value = [selectedDirKey];
    if (Number.isInteger(page) && page > 0) {
      pagination.page = page;
    }
    if (Number.isInteger(pageSize) && [10, 12, 20, 50].includes(pageSize)) {
      pagination.pageSize = pageSize;
    }
    if (parsed.searchScope === 'current' || parsed.searchScope === 'all') {
      filters.searchScope = parsed.searchScope;
    }
  } catch {
    window.localStorage.removeItem(LIST_STATE_CACHE_KEY);
  }
}

  return { persistListState, restoreListState };
}
