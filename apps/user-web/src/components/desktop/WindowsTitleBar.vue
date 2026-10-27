<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { desktopChromeMessages } from '../../locales/desktopChromeMessages'

type MenuName = 'file' | 'edit' | 'view'
type Action = 'new-chat' | 'add-project' | 'toggle-sidebar'
interface TitlebarBridge {
  openMenu(name: MenuName, point: { x: number; y: number }): Promise<void>
  setDark(dark: boolean): Promise<void>
  onAction(listener: (action: Action) => void): () => void
}

const props = defineProps<{ collapsed: boolean; dark: boolean; locale: 'zh' | 'en' }>()
const copy = (key: keyof typeof desktopChromeMessages) => desktopChromeMessages[key][props.locale]
const emit = defineEmits<{
  (event: 'toggle-sidebar'): void
  (event: 'new-chat'): void
  (event: 'add-project'): void
}>()

const bridge = (globalThis as typeof globalThis & { __ASKAI_ELECTRON__?: { windowTitlebar?: TitlebarBridge } })
  .__ASKAI_ELECTRON__?.windowTitlebar
let unsubscribe: (() => void) | undefined

function openMenu(name: MenuName, event: MouseEvent): void {
  const button = event.currentTarget as HTMLElement
  const rect = button.getBoundingClientRect()
  void bridge?.openMenu(name, { x: rect.left, y: rect.bottom })
}

onMounted(() => {
  unsubscribe = bridge?.onAction((action) => {
    if (action === 'toggle-sidebar') emit('toggle-sidebar')
    else if (action === 'new-chat') emit('new-chat')
    else if (action === 'add-project') emit('add-project')
  })
})
onBeforeUnmount(() => unsubscribe?.())
watch(() => props.dark, (dark) => { void bridge?.setDark(dark) }, { immediate: true })
</script>

<template>
  <div class="windows-titlebar" :class="{ 'windows-titlebar--dark': dark }" aria-label="Windows title bar">
    <button
      type="button"
      class="windows-titlebar__toggle"
      :aria-label="collapsed ? (copy('showSidebar')) : (copy('hideSidebar'))"
      :aria-expanded="!collapsed"
      @click="emit('toggle-sidebar')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M9 4v16" />
      </svg>
    </button>
    <div class="windows-titlebar__menus" role="menubar">
      <button v-for="menu in (['file', 'edit', 'view'] as const)" :key="menu" type="button" role="menuitem" @click="openMenu(menu, $event)">
        {{ copy(({ file: 'fileMenu', edit: 'editMenu', view: 'viewMenu' } as const)[menu]) }}
      </button>
    </div>
    <div class="windows-titlebar__drag" aria-hidden="true"></div>
  </div>
</template>

<style scoped>
.windows-titlebar { position:absolute; inset:0 0 auto; z-index:50; display:flex; align-items:center; height:40px; padding-right:138px; border-bottom:1px solid #dbe3ef; background:#f8fafc; color:#475569; user-select:none; -webkit-app-region:drag; }
.windows-titlebar__toggle, .windows-titlebar__menus button { height:32px; border:0; border-radius:7px; background:transparent; color:inherit; cursor:pointer; -webkit-app-region:no-drag; }
.windows-titlebar__toggle { display:grid; flex:none; width:40px; margin-left:2px; place-items:center; }
.windows-titlebar__toggle svg { width:18px; height:18px; }
.windows-titlebar__menus { display:flex; align-items:center; gap:2px; -webkit-app-region:no-drag; }
.windows-titlebar__menus button { min-width:40px; padding:0 9px; font-size:12px; }
.windows-titlebar__toggle:hover, .windows-titlebar__menus button:hover { background:#e8eef7; color:#1d4ed8; }
.windows-titlebar__toggle:focus-visible, .windows-titlebar__menus button:focus-visible { outline:2px solid #2563eb; outline-offset:-2px; }
.windows-titlebar__drag { flex:1; align-self:stretch; }
.windows-titlebar--dark { border-color:#334155; background:#0b1220; color:#cbd5e1; }
.windows-titlebar--dark .windows-titlebar__toggle:hover, .windows-titlebar--dark .windows-titlebar__menus button:hover { background:#1e293b; color:#bfdbfe; }
.windows-titlebar--dark .windows-titlebar__toggle:focus-visible, .windows-titlebar--dark .windows-titlebar__menus button:focus-visible { outline-color:#93c5fd; }
</style>
