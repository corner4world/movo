<template>
  <div class="flex h-full items-center justify-center bg-white px-6 text-center text-slate-600">
    <div>
      <p>{{ chatChromeMessages.loadFailed[locale] }}</p>
      <button class="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-white" @click="reload">
        {{ chatChromeMessages.reload[locale] }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useLocale } from '../composables/i18n'
import { chatChromeMessages } from '../locales/chatChromeMessages'

const { locale } = useLocale()
function reload() { window.location.reload() }
</script>
