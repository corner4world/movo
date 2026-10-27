import { defaultPromptGuidePrompts } from './promptGuidePrompts'
import { t } from '../../composables/i18n'

export type PromptGuideConfigTarget = 'skills' | 'tools' | 'knowledge'

export type PromptGuideItem = {
  label: string
  prompt?: string
  icon: string
  available: boolean
  categoryKey?: string
  shortcutType?: 'prompt' | 'skill' | 'agent'
  resourceId?: string
  configTarget?: PromptGuideConfigTarget
  configTitle?: string
  configDescription?: string
}

export type PromptGuideCategory = {
  key: string
  label: string
  icon: string
  tone: string
  requiresConfig?: boolean
  configTarget?: PromptGuideConfigTarget
  configTitle?: string
  configDescription?: string
  items: PromptGuideItem[]
}

function svgIcon(paths: string): string {
  return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`
}

export const promptGuideIcons = {
  albums: svgIcon('<rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="M7 3h10"></path><path d="M8 9h8"></path><path d="M8 13h5"></path>'),
  analytics: svgIcon('<path d="M4 19V5"></path><path d="M4 19h16"></path><path d="M8 15l3-4 3 2 5-7"></path><path d="M18 6h2v2"></path>'),
  briefcase: svgIcon('<rect x="3" y="7" width="18" height="13" rx="2"></rect><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><path d="M3 12h18"></path>'),
  build: svgIcon('<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-3 3-3-3 3-3Z"></path>'),
  cart: svgIcon('<circle cx="9" cy="20" r="1"></circle><circle cx="18" cy="20" r="1"></circle><path d="M2 3h3l3 12h10l2-8H7"></path>'),
  create: svgIcon('<path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path>'),
  document: svgIcon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path><path d="M14 2v6h6"></path><path d="M8 13h8"></path><path d="M8 17h6"></path>'),
  earth: svgIcon('<circle cx="12" cy="12" r="10"></circle><path d="M2 12h20"></path><path d="M12 2a15.3 15.3 0 0 1 0 20"></path><path d="M12 2a15.3 15.3 0 0 0 0 20"></path>'),
  easel: svgIcon('<rect x="4" y="3" width="16" height="10" rx="2"></rect><path d="M12 13v8"></path><path d="M8 21h8"></path><path d="M8 17l-3 4"></path><path d="M16 17l3 4"></path>'),
  files: svgIcon('<path d="M5 4h11l3 3v13H5Z"></path><path d="M16 4v4h4"></path><path d="M8 12h8"></path><path d="M8 16h5"></path>'),
  globe: svgIcon('<circle cx="12" cy="12" r="10"></circle><path d="M2 12h20"></path><path d="M12 2c3 3 4 6 4 10s-1 7-4 10"></path><path d="M12 2C9 5 8 8 8 12s1 7 4 10"></path>'),
  grid: svgIcon('<rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect>'),
  image: svgIcon('<rect x="3" y="3" width="18" height="18" rx="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><path d="M21 15l-5-5L5 21"></path>'),
  language: svgIcon('<path d="M4 5h8"></path><path d="M8 3v2"></path><path d="M10 5c-.7 3.5-2.6 6-6 8"></path><path d="M5 9c1.2 1.6 2.8 2.8 5 4"></path><path d="M14 21l4-10 4 10"></path><path d="M16 17h4"></path>'),
  library: svgIcon('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5Z"></path><path d="M8 6h8"></path><path d="M8 10h7"></path>'),
  lock: svgIcon('<rect x="4" y="10" width="16" height="10" rx="2"></rect><path d="M8 10V7a4 4 0 0 1 8 0v3"></path>'),
  newspaper: svgIcon('<path d="M4 5h13a3 3 0 0 1 3 3v11H6a2 2 0 0 1-2-2Z"></path><path d="M8 9h7"></path><path d="M8 13h8"></path><path d="M8 17h5"></path>'),
  people: svgIcon('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path>'),
  qa: svgIcon('<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z"></path><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"></path><path d="M12 17h.01"></path>'),
  search: svgIcon('<circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path>'),
  server: svgIcon('<rect x="3" y="4" width="18" height="6" rx="2"></rect><rect x="3" y="14" width="18" height="6" rx="2"></rect><path d="M7 7h.01"></path><path d="M7 17h.01"></path>'),
  settings: svgIcon('<circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6V21h-4v-1a1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1H3v-4h1a1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6V3h4v1a1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.18.37.39.7.6 1h1v4h-1a1.7 1.7 0 0 0-.6 1Z"></path>'),
  shield: svgIcon('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"></path><path d="M9 12l2 2 4-5"></path>'),
  stats: svgIcon('<path d="M4 19V5"></path><path d="M4 19h16"></path><rect x="7" y="11" width="3" height="5"></rect><rect x="12" y="8" width="3" height="8"></rect><rect x="17" y="5" width="3" height="11"></rect>'),
}

export const promptGuideUiIcons = {
  lock: promptGuideIcons.lock,
  settings: promptGuideIcons.settings,
}

export const promptGuideCategories: PromptGuideCategory[] = [
  {
    key: 'content',
    get label() { return t('legacy.content_generation') },
    icon: promptGuideIcons.create,
    tone: 'guide-tone-content',
    items: [
      {
        get label() { return t('legacy.wechat_red') },
        icon: promptGuideIcons.newspaper,
        available: true,
        prompt: defaultPromptGuidePrompts['content.wechat'],
      },
      {
        get label() { return t('legacy.report_plan') },
        icon: promptGuideIcons.document,
        available: true,
        prompt: defaultPromptGuidePrompts['content.report'],
      },
      {
        get label() { return t('legacy.ppt_generation') },
        icon: promptGuideIcons.easel,
        available: true,
        prompt: defaultPromptGuidePrompts['content.ppt'],
      },
      {
        get label() { return t('legacy.image_to_prd') },
        icon: promptGuideIcons.image,
        available: true,
        prompt: defaultPromptGuidePrompts['content.image_prd'],
      },
      {
        get label() { return t('legacy.translate_document') },
        icon: promptGuideIcons.language,
        available: true,
        prompt: defaultPromptGuidePrompts['content.translate'],
      },
      {
        get label() { return t('legacy.fill_forms_from_documents') },
        icon: promptGuideIcons.grid,
        available: true,
        prompt: defaultPromptGuidePrompts['content.fill_form'],
      },
    ],
  },
  {
    key: 'external',
    get label() { return t('legacy.web_search') },
    icon: promptGuideIcons.globe,
    tone: 'guide-tone-external',
    items: [
      {
        get label() { return t('legacy.web_research') },
        icon: promptGuideIcons.search,
        available: true,
        prompt: defaultPromptGuidePrompts['external.web'],
      },
      {
        get label() { return t('legacy.industry_research') },
        icon: promptGuideIcons.earth,
        available: true,
        prompt: defaultPromptGuidePrompts['external.industry'],
      },
      {
        get label() { return t('legacy.competitive_analysis') },
        icon: promptGuideIcons.analytics,
        available: true,
        prompt: defaultPromptGuidePrompts['external.competitor'],
      },
      {
        get label() { return t('legacy.policy_news') },
        icon: promptGuideIcons.shield,
        available: true,
        prompt: defaultPromptGuidePrompts['external.policy_news'],
      },
      {
        get label() { return t('legacy.literature_overview') },
        icon: promptGuideIcons.albums,
        available: true,
        prompt: defaultPromptGuidePrompts['external.overview'],
      },
      {
        get label() { return t('legacy.fact_check') },
        icon: promptGuideIcons.stats,
        available: true,
        prompt: defaultPromptGuidePrompts['external.fact_check'],
      },
    ],
  },
  {
    key: 'internal',
    get label() { return t('legacy.internal_knowledge') },
    icon: promptGuideIcons.library,
    tone: 'guide-tone-internal',
    requiresConfig: true,
    configTarget: 'knowledge',
    get configTitle() { return t('legacy.set_up_internal_knowledge_first') },
    get configDescription() { return t('legacy.set_up_a_knowledge_base_or_upload_internal_material') },
    items: [
      { get label() { return t('legacy.search_knowledge') }, icon: promptGuideIcons.qa, available: true, prompt: defaultPromptGuidePrompts['internal.search'] },
      { get label() { return t('legacy.search_past_documents') }, icon: promptGuideIcons.files, available: true, prompt: defaultPromptGuidePrompts['internal.history'] },
      { get label() { return t('legacy.search_policies') }, icon: promptGuideIcons.briefcase, available: true, prompt: defaultPromptGuidePrompts['internal.policy'] },
      { get label() { return t('legacy.search_project_files') }, icon: promptGuideIcons.albums, available: true, prompt: defaultPromptGuidePrompts['internal.project'] },
      { get label() { return t('legacy.search_customer_files') }, icon: promptGuideIcons.people, available: true, prompt: defaultPromptGuidePrompts['internal.customer'] },
      { get label() { return t('legacy.search_training_materials') }, icon: promptGuideIcons.document, available: true, prompt: defaultPromptGuidePrompts['internal.training'] },
    ],
  },
  {
    key: 'systems',
    get label() { return t('legacy.connected_systems') },
    icon: promptGuideIcons.server,
    tone: 'guide-tone-systems',
    requiresConfig: true,
    configTarget: 'tools',
    get configTitle() { return t('legacy.set_up_a_connected_system_first') },
    get configDescription() { return t('legacy.set_up_an_http_tool_or_mcp_service_first') },
    items: [
      { get label() { return t('legacy.sales_query') }, icon: promptGuideIcons.cart, available: true, prompt: defaultPromptGuidePrompts['systems.sales'] },
      { get label() { return t('legacy.root_cause_analysis') }, icon: promptGuideIcons.analytics, available: true, prompt: defaultPromptGuidePrompts['systems.root_cause'] },
      { get label() { return t('legacy.inventory_query') }, icon: promptGuideIcons.files, available: true, prompt: defaultPromptGuidePrompts['systems.inventory'] },
      { get label() { return t('legacy.customer_query') }, icon: promptGuideIcons.people, available: true, prompt: defaultPromptGuidePrompts['systems.customer'] },
      { get label() { return t('legacy.daily_operations_report') }, icon: promptGuideIcons.document, available: true, prompt: defaultPromptGuidePrompts['systems.daily'] },
      { get label() { return t('legacy.call_mcp') }, icon: promptGuideIcons.build, available: true, prompt: defaultPromptGuidePrompts['systems.mcp'] },
    ],
  },
]
