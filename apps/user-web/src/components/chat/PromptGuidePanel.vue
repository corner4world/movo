<script setup lang="ts">
import type { PromptGuideCategory, PromptGuideConfigTarget, PromptGuideItem } from './promptGuideConfig'
import { promptGuideUiIcons } from './promptGuideConfig'
import { t, translateSourceText } from '../../composables/i18n'

defineProps<{
  activeKey: string | null
  categories: PromptGuideCategory[]
  activeCategory: PromptGuideCategory | null
  notice: { title: string; description: string; target: PromptGuideConfigTarget } | null
  selectCategory: (key: string) => void
  cancelClose: () => void
  scheduleClose: () => void
  useItem: (item: PromptGuideItem) => unknown
  openConfig: (target: PromptGuideConfigTarget) => void
}>()
</script>

<template>
  <div
    class="prompt-guide"
    @mouseenter="cancelClose"
    @mouseleave="scheduleClose"
  >
    <div class="prompt-guide-tabs" role="tablist" :aria-label="t('legacy.task_guide')">
      <button
        v-for="category in categories"
        :key="category.key"
        type="button"
        class="prompt-guide-tab"
        :class="[category.tone, { 'is-active': activeKey === category.key }]"
        role="tab"
        :aria-selected="activeKey === category.key"
        @mouseenter="selectCategory(category.key)"
        @focus="selectCategory(category.key)"
        @click="selectCategory(category.key)"
      >
        <span class="prompt-guide-tab-icon">
          <span v-html="category.icon"></span>
        </span>
        <span>{{ translateSourceText(category.label) }}</span>
      </button>
    </div>
    <transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-1"
    >
      <div
        v-if="activeCategory"
        :key="activeCategory.key"
        class="prompt-guide-panel"
        @mouseenter="cancelClose"
        @mouseleave="scheduleClose"
      >
        <div class="prompt-guide-arc">
          <button
            v-for="item in activeCategory.items"
            :key="item.label"
            type="button"
            class="prompt-guide-item"
            :class="{ 'is-locked': !item.available }"
            @click="useItem(item)"
          >
            <span class="prompt-guide-item-icon">
              <span v-html="item.icon"></span>
            </span>
            <span class="prompt-guide-item-label">{{ translateSourceText(item.label) }}</span>
            <span v-if="!item.available" class="prompt-guide-lock">
              <span v-html="promptGuideUiIcons.lock"></span>
              {{ t('legacy.setup_required') }}
            </span>
          </button>
        </div>
        <div v-if="notice" class="prompt-guide-notice" role="status">
          <div class="prompt-guide-notice-icon">
            <span v-html="promptGuideUiIcons.settings"></span>
          </div>
          <div class="min-w-0 flex-1">
            <div class="prompt-guide-notice-title">{{ translateSourceText(notice.title) }}</div>
            <div class="prompt-guide-notice-desc">{{ translateSourceText(notice.description) }}</div>
          </div>
          <button
            type="button"
            class="prompt-guide-config-btn"
            @click="openConfig(notice.target)"
          >
            {{ t('legacy.configure') }}
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped src="./promptGuide.css"></style>
