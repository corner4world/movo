<script setup lang="ts">
import { t, type Locale } from '../composables/i18n'
import { formatExactTokenAmount, formatTokenAmount } from '../utils/tokenNumberFormat'
import type { TenantCandidate } from '../api/auth'

defineProps<{
  open: boolean
  loggedIn: boolean
  desktop: boolean
  avatarUrl: string
  avatarText: string
  displayName: string
  maskedPhone: string
  accountTierLabel: string
  billingSummary: unknown
  billingSummaryLoading: boolean
  billingSummaryLoaded: boolean
  quotaRemaining: number
  quotaTotal: number
  quotaTotalLabel: string
  quotaUsedPercent: number
  quotaUsedPercentLabel: string
  availableTenants: TenantCandidate[]
  mainId: string
  switchingTenant: boolean
  adminSsoStarting: boolean
  canCreateOrganization: boolean
  canUpgradePlan: boolean
  orgName?: string
  locale: Locale
  canAccessAdmin: (tenant: TenantCandidate) => boolean
  isEnterpriseTenant: (tenant: TenantCandidate) => boolean
}>()
const emit = defineEmits<{
  (e: 'avatar-error', event: Event): void
  (e: 'profile'): void
  (e: 'usage'): void
  (e: 'switch-tenant', mainId: string): void
  (e: 'admin', mainId: string): void
  (e: 'create-organization'): void
  (e: 'billing'): void
  (e: 'personalization'): void
  (e: 'settings'): void
  (e: 'logout'): void
}>()
function formatTokenCount(value: number, locale: Locale) {
  return formatTokenAmount(value, locale)
}
</script>

<template>
        <Teleport to="body">
          <div
            v-if="open && loggedIn"
            class="fixed bottom-20 z-[80] w-[360px] max-w-[calc(100vw-2rem)] rounded-2xl border border-gray-200 bg-white p-3 text-sm text-gray-700 shadow-[0_18px_56px_rgba(15,23,42,0.14)] animate-in fade-in slide-in-from-bottom-2 duration-200"
            :class="desktop ? 'left-[72px]' : 'left-4'"
            data-user-menu
          >
          <div class="flex items-center gap-3 px-2 pb-3 pt-1">
            <div class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-blue-600 font-bold text-white">
              <img v-if="avatarUrl" :src="avatarUrl" alt="" class="h-full w-full object-cover" @error="emit('avatar-error', $event)" />
              <span v-else>{{ avatarText }}</span>
            </div>
            <div class="min-w-0 flex-1">
              <div class="truncate font-semibold text-gray-900">{{ displayName }}</div>
              <div class="mt-0.5 text-xs text-gray-500">
                {{ maskedPhone || accountTierLabel }}
                <span v-if="maskedPhone" class="mx-1 text-gray-300">·</span>
                <span v-if="maskedPhone">{{ accountTierLabel }}</span>
              </div>
            </div>
            <button
               type="button"
               class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
               :aria-label="t('ui.edit_profile')"
               :title="t('ui.edit_profile')"
               @click.stop="emit('profile')"
             >
               <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                 <path d="M12 20h9"/>
                 <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
               </svg>
             </button>
           </div>

           <div class="mb-3 rounded-xl bg-slate-50 px-3 py-3">
             <div class="flex items-start justify-between gap-3">
               <div>
                 <div class="text-[11px] font-medium text-slate-500">{{ t('ui.quota_remaining') }}</div>
                 <div v-if="billingSummary" class="mt-1 text-xl font-bold text-slate-900" :title="`${formatExactTokenAmount(quotaRemaining, locale)} Token`">
                   {{ formatTokenCount(quotaRemaining, locale) }}
                 </div>
                 <div v-else-if="billingSummaryLoading || !billingSummaryLoaded" class="mt-2 h-6 w-20 animate-pulse rounded bg-slate-200"></div>
                 <div v-else class="mt-1 text-sm font-medium text-slate-500">{{ t('ui.quota_unavailable') }}</div>
               </div>
               <div v-if="billingSummary" class="text-right text-[11px] leading-5 text-slate-500">
                 <div :title="`${formatExactTokenAmount(quotaTotal, locale)} Token`">{{ quotaTotalLabel }} {{ formatTokenCount(quotaTotal, locale) }}</div>
                 <div>{{ t('ui.quota_used') }} {{ quotaUsedPercentLabel }}%</div>
               </div>
             </div>
             <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200" :aria-label="t('ui.quota_usage_progress')">
               <div
                 class="h-full rounded-full bg-blue-600 transition-all duration-300"
                 :style="{ width: `${quotaUsedPercent}%` }"
               ></div>
             </div>
             <button
               type="button"
               class="mt-2 flex min-h-[32px] w-full items-center justify-between text-xs font-medium text-slate-600 transition-colors hover:text-slate-900"
               @click="emit('usage')"
             >
               <span>{{ t('ui.view_usage_history') }}</span>
               <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                 <path d="m9 18 6-6-6-6"/>
               </svg>
             </button>
           </div>

           <div class="px-1 py-1">
             <div class="mb-1 text-[10px] font-bold text-gray-400 uppercase tracking-widest">{{ t('app.organization') }}</div>
             <div v-if="availableTenants.length" class="space-y-1 max-h-40 overflow-auto pr-1">
               <div
                 v-for="tenant in availableTenants"
                 :key="tenant.mainId"
                 class="flex min-h-[48px] w-full items-center gap-1 rounded-xl px-2 transition-colors"
                 :class="tenant.mainId === mainId ? 'bg-blue-50 text-blue-700' : 'hover:bg-gray-50 text-gray-700'"
               >
                 <button
                   type="button"
                   class="min-w-0 flex-1 px-1 py-2 text-left leading-5 disabled:cursor-wait disabled:opacity-60"
                   :disabled="switchingTenant || adminSsoStarting"
                   @click="emit('switch-tenant', tenant.mainId)"
                 >
                   <span class="block whitespace-normal break-words font-medium">{{ tenant.orgName || tenant.mainId }}</span>
                   <span v-if="isEnterpriseTenant(tenant)" class="mt-0.5 block text-[11px] font-normal text-slate-400">
                     {{ t('ui.enterprise_space') }}
                   </span>
                 </button>
                 <button
                   v-if="canAccessAdmin(tenant)"
                   type="button"
                   class="flex min-h-9 shrink-0 items-center gap-1 rounded-lg px-2 text-xs font-medium text-slate-500 transition-colors hover:bg-white hover:text-blue-600 disabled:cursor-wait disabled:opacity-50"
                   :aria-label="t('ui.enter_tenant_admin', { org: tenant.orgName || tenant.mainId })"
                   :title="t('ui.enter_tenant_admin', { org: tenant.orgName || tenant.mainId })"
                   :disabled="switchingTenant || adminSsoStarting"
                   @click.stop="emit('admin', tenant.mainId)"
                 >
                   <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                     <rect x="3" y="4" width="18" height="14" rx="2"/>
                     <path d="M8 21h8M12 18v3M7 9h4M7 13h7"/>
                   </svg>
                   <span>{{ t('ui.admin_short') }}</span>
                 </button>
               </div>
             </div>
             <div v-else class="rounded-xl bg-blue-50 px-3 py-2.5 font-medium text-blue-700">
               {{ orgName || t('ui.personal_space') }}
             </div>
             <button
               v-if="canCreateOrganization"
               type="button"
               class="mt-1 flex min-h-[40px] w-full items-center gap-2 rounded-xl px-3 text-left font-medium text-blue-600 transition-colors hover:bg-blue-50"
               @click="emit('create-organization')"
             >
               <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                 <path d="M12 5v14M5 12h14"/>
               </svg>
               {{ t('ui.create_enterprise') }}
             </button>
           </div>
           <button v-if="canUpgradePlan" @click="emit('billing')" class="mt-1 flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50">
             <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/></svg>
             {{ t('app.account.upgrade') }}
           </button>
           <button class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50" @click="emit('profile')">
             <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
               <path d="M20 21a8 8 0 0 0-16 0"/>
               <circle cx="12" cy="7" r="4"/>
             </svg>
             {{ t('ui.edit_profile') }}
           </button>
          <button class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50" @click="emit('personalization')">
            <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>
              <circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>
              <circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>
              <circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>
              <path d="M12 22a10 10 0 1 1 10-10c0 2.2-1.8 4-4 4h-1.8a1.8 1.8 0 0 0-1.4 3l.2.3A1.7 1.7 0 0 1 13.6 22Z"/>
            </svg>
            {{ t('app.account.personalization') }}
          </button>
          <button
            v-if="desktop"
            class="flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-gray-50"
            @click="emit('settings')"
          >
            <svg class="h-4 w-4 shrink-0 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.18.37.39.7.6 1 .26.35.4.77.4 1.2v1.6c0 .43-.14.85-.4 1.2-.21.3-.42.63-.6 1Z"/>
            </svg>
            {{ t('app.account.settings') }}
          </button>
          <div class="h-px bg-gray-100 my-2"></div>
          <button class="w-full rounded-xl px-3 py-2.5 text-left font-medium text-red-600 transition-colors hover:bg-red-50" @click="emit('logout')">
            {{ t('app.account.logout') }}
          </button>
          </div>
        </Teleport>
</template>
