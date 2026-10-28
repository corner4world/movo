import { computed, type Ref } from 'vue'
import { fetchOrgBilling, type UserProfile } from '../api/auth'
import { t } from './i18n'
import { formatQuotaUsagePercent, quotaUsagePercent } from '../utils/tokenNumberFormat'

type BillingSummary = {
  edition?: string
  tier?: string
  totalPoints?: number
  usedPoints?: number
  remainingPoints?: number
  quotaSource?: string
} | null

type BillingSummaryOptions = {
  profile: Ref<UserProfile | null>
  token: Ref<string>
  summary: Ref<BillingSummary>
  loading: Ref<boolean>
  loaded: Ref<boolean>
  enterpriseSpace: Ref<boolean>
}

export function useBillingSummary(options: BillingSummaryOptions) {
  const accountTierLabel = computed(() => {
    if (options.profile.value?.edition === 'community' || options.summary.value?.edition === 'community') {
      return t('ui.community_edition')
    }
    if (options.enterpriseSpace.value) {
      return options.profile.value?.canAccessAdmin ? t('ui.enterprise_admin') : t('ui.enterprise_member')
    }
    const tier = options.summary.value?.tier || options.profile.value?.tier
    if (tier === 'plus') return t('app.tier.plus')
    if (tier === 'pro') return t('app.tier.pro')
    if (tier === 'enterprise') return t('app.tier.enterprise')
    return t('app.tier.free')
  })

  const quotaTotal = computed(() => Number(options.summary.value?.totalPoints || 0))
  const quotaUsed = computed(() => Number(options.summary.value?.usedPoints || 0))
  const quotaRemaining = computed(() => Math.max(0, Number(options.summary.value?.remainingPoints ?? quotaTotal.value - quotaUsed.value)))
  const quotaUsedPercent = computed(() => quotaUsagePercent(quotaUsed.value, quotaTotal.value))
  const quotaUsedPercentLabel = computed(() => formatQuotaUsagePercent(quotaUsed.value, quotaTotal.value))
  const quotaTotalLabel = computed(() => options.summary.value?.quotaSource === 'enterprise_allocation'
    ? t('ui.quota_enterprise_allocation')
    : t('ui.quota_gift'))

  async function loadBillingSummary(): Promise<void> {
    if (!options.token.value || options.loading.value) return
    options.loading.value = true
    try {
      const result = await fetchOrgBilling(options.token.value)
      if (result.ok) options.summary.value = result.data
    } finally {
      options.loading.value = false
      options.loaded.value = true
    }
  }

  return { accountTierLabel, quotaTotal, quotaRemaining, quotaUsedPercent, quotaUsedPercentLabel, quotaTotalLabel, loadBillingSummary }
}
