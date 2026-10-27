import { t, translateSourceText } from '@/composables/i18n';
import { dashboardMessagePatterns } from '@/locales/legacyRecognitionValues';

/** Translate dashboard messages that are returned as legacy human-readable text. */
export function translateDashboardText(value: string | null | undefined): string {
  const text = String(value || '');
  if (!text) return '';

  let match = text.match(dashboardMessagePatterns.toolConnections);
  if (match) return t('legacy.tool_connections_need_attention', { count: match[1] });

  match = text.match(dashboardMessagePatterns.toolsUntested);
  if (match) return t('legacy.tools_have_not_been_connectivity_tested', { count: match[1] });

  match = text.match(dashboardMessagePatterns.modelsFailed);
  if (match) return t('legacy.models_failed_their_recent_health_checks', { count: match[1] });

  match = text.match(dashboardMessagePatterns.callsFailed);
  if (match) return t('legacy.calls_failed_review_token_statistics', { count: match[1] });

  return translateSourceText(text);
}
