import { translateSourceText } from '@/composables/i18n';

export function localizeWorkflowDefaults(config: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(config).map(([key, value]) => [
    key,
    typeof value === 'string' ? translateSourceText(value) : value,
  ]));
}
