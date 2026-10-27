import browserAutomationIcon from '../assets/workflow-node-icons/browser-automation.svg?raw'
import { t } from '../composables/i18n'
import { browserAutomationKeywords } from '../locales/legacyRecognitionValues'

export const BROWSER_AUTOMATION_NODE_TYPE = 'browser_automation' as const

export const browserAutomationNodeMeta = {
  type: BROWSER_AUTOMATION_NODE_TYPE,
  get label() { return t('workflow.preset.browser_automation.label') },
  get shortLabel() { return t('workflow.browser.short') },
  color: '#0f766e',
  bg: '#ecfdf5',
  icon: browserAutomationIcon,
  get defaultTitle() { return t('workflow.browser.title') },
  get placeholder() { return t('workflow.preset.browser_automation.placeholder') },
  defaultConfig: { targetName: '', targetUrl: '', get outputAlias() { return t('workflow.browser.output') } },
  get usageDescription() { return t('workflow.browser.description') },
  get usageExample() { return t('workflow.browser.example') },
}

export function looksLikeBrowserAutomation(text: string): boolean {
  const value = String(text || '').toLowerCase()
  return browserAutomationKeywords.some((keyword) => value.includes(keyword))
}
