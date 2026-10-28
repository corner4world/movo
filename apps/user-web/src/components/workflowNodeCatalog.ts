import readMaterialIcon from '../assets/workflow-node-icons/read-material.svg?raw';
import extractInfoIcon from '../assets/workflow-node-icons/extract-info.svg?raw';
import reviewCheckIcon from '../assets/workflow-node-icons/review-check.svg?raw';
import extractResourcesIcon from '../assets/workflow-node-icons/extract-resources.svg?raw';
import understandImageIcon from '../assets/workflow-node-icons/understand-image.svg?raw';
import computeMetricIcon from '../assets/workflow-node-icons/compute-metric.svg?raw';
import dataCollectIcon from '../assets/workflow-node-icons/data-collect.svg?raw';
import internalSearchIcon from '../assets/workflow-node-icons/internal-search.svg?raw';
import externalSearchIcon from '../assets/workflow-node-icons/external-search.svg?raw';
import callToolIcon from '../assets/workflow-node-icons/call-tool.svg?raw';
import dataProcessingIcon from '../assets/workflow-node-icons/data-processing.svg?raw';
import generateContentIcon from '../assets/workflow-node-icons/generate-content.svg?raw';
import translateRewriteIcon from '../assets/workflow-node-icons/translate-rewrite.svg?raw';
import fillTableIcon from '../assets/workflow-node-icons/fill-table.svg?raw';
import exportDeliveryIcon from '../assets/workflow-node-icons/export-delivery.svg?raw';
import { browserAutomationNodeMeta } from '../workflow/browserAutomationNode';
import { t } from '../composables/i18n';
import type { WorkflowNodeType } from '../api/skills';

export const workflowNodeTypes: Array<{
  type: WorkflowNodeType;
  label: string;
  shortLabel: string;
  color: string;
  bg: string;
  icon: string;
  defaultTitle: string;
  placeholder: string;
  defaultConfig: Record<string, any>;
  usageDescription?: string;
  usageExample?: string;
}> = [
  {
    type: 'read_material',
    get label() { return t('workflow.preset.read_material.label') },
    get shortLabel() { return t('workflow.preset.read_material.short') },
    color: '#2f6bff',
    bg: '#eef4ff',
    icon: readMaterialIcon,
    get defaultTitle() { return t('workflow.preset.read_material.title') },
    get placeholder() { return t('workflow.preset.read_material.placeholder') },
    defaultConfig: { sourceType: 'upload', get source() { return t('workflow.preset.read_material.src') }, get outputAlias() { return t('workflow.preset.read_material.out') } },
    get usageDescription() { return t('legacy.read_uploaded_material_or_an_authorized_personal_knowledge_document') },
    get usageExample() { return t('legacy.read_the_uploaded_east_china_project_progress_report_and') },
  },
  {
    type: 'extract_resources',
    get label() { return t('workflow.preset.extract_resources.label') },
    get shortLabel() { return t('workflow.preset.extract_resources.short') },
    color: '#0891b2',
    bg: '#ecfeff',
    icon: extractResourcesIcon,
    get defaultTitle() { return t('workflow.preset.extract_resources.title') },
    get placeholder() { return t('workflow.preset.extract_resources.placeholder') },
    defaultConfig: { resourceTypes: ['images', 'urls', 'attachments'], get outputAlias() { return t('workflow.preset.extract_resources.out') } },
    get usageDescription() { return t('legacy.separate_images_web_links_and_attachments_from_upstream_materials') },
    get usageExample() { return t('legacy.extract_all_embedded_screenshots_http_https_links_and_attachment') },
  },
  {
    type: 'understand_image',
    get label() { return t('workflow.preset.understand_image.label') },
    get shortLabel() { return t('workflow.preset.understand_image.short') },
    color: '#4f46e5',
    bg: '#eef2ff',
    icon: understandImageIcon,
    get defaultTitle() { return t('workflow.preset.understand_image.title') },
    get placeholder() { return t('workflow.preset.understand_image.placeholder') },
    defaultConfig: { get input() { return t('workflow.preset.understand_image.in') }, get outputAlias() { return t('workflow.preset.understand_image.out') } },
    get usageDescription() { return t('legacy.recognize_text_objects_interfaces_charts_and_key_visual_details') },
    get usageExample() { return t('legacy.analyze_eight_upstream_social_platform_screenshots_and_extract_the') },
  },
  {
    type: 'extract_info',
    get label() { return t('workflow.preset.extract_info.label') },
    get shortLabel() { return t('workflow.preset.extract_info.short') },
    color: '#2563eb',
    bg: '#edf5ff',
    icon: extractInfoIcon,
    get defaultTitle() { return t('workflow.preset.extract_info.title') },
    get placeholder() { return t('workflow.preset.extract_info.placeholder') },
    defaultConfig: { get target() { return t('workflow.preset.extract_info.target') }, get method() { return t('workflow.preset.extract_info.method') }, get outputAlias() { return t('workflow.preset.extract_info.out') } },
    get usageDescription() { return t('legacy.extract_specified_fields_facts_and_metrics_from_upstream_text') },
    get usageExample() { return t('legacy.extract_the_project_name_owner_dates_contract_amount_current') },
  },
  {
    type: 'compute_metric',
    get label() { return t('workflow.preset.compute_metric.label') },
    get shortLabel() { return t('workflow.preset.compute_metric.short') },
    color: '#16a36f',
    bg: '#effaf4',
    icon: computeMetricIcon,
    get defaultTitle() { return t('workflow.preset.compute_metric.title') },
    get placeholder() { return t('workflow.preset.compute_metric.placeholder') },
    defaultConfig: { get method() { return t('workflow.preset.compute_metric.method') }, get outputAlias() { return t('workflow.preset.compute_metric.out') } },
    get usageDescription() { return t('legacy.run_defined_calculations_on_upstream_structured_data_such_as') },
    get usageExample() { return t('legacy.aggregate_q1_2026_contract_and_collection_amounts_by_region') },
  },
  {
    type: 'data_collect',
    get label() { return t('workflow.preset.data_collect.label') },
    get shortLabel() { return t('workflow.preset.data_collect.short') },
    color: '#0d9488',
    bg: '#ecfdf5',
    icon: dataCollectIcon,
    get defaultTitle() { return t('workflow.preset.data_collect.title') },
    get placeholder() { return t('workflow.preset.data_collect.placeholder') },
    defaultConfig: { get source() { return t('workflow.preset.data_collect.src') }, get outputAlias() { return t('workflow.preset.data_collect.out') } },
    get usageDescription() { return t('legacy.visit_upstream_web_links_and_collect_page_titles_body') },
    get usageExample() { return t('legacy.collect_news_pages_from_the_upstream_url_list_keeping') },
  },
  browserAutomationNodeMeta,
  {
    type: 'internal_search',
    get label() { return t('workflow.preset.internal_search.label') },
    get shortLabel() { return t('workflow.preset.internal_search.short') },
    color: '#a16207',
    bg: '#fff8e8',
    icon: internalSearchIcon,
    get defaultTitle() { return t('workflow.preset.internal_search.title') },
    get placeholder() { return t('workflow.preset.internal_search.placeholder') },
    defaultConfig: { get source() { return t('workflow.preset.internal_search.src') }, get outputAlias() { return t('workflow.preset.internal_search.out') } },
    get usageDescription() { return t('legacy.search_configured_enterprise_knowledge_bases_policy_libraries_or_historical') },
    get usageExample() { return t('legacy.search_the_project_management_policy_library_for_project_delay') },
  },
  {
    type: 'external_search',
    get label() { return t('workflow.preset.external_search.label') },
    get shortLabel() { return t('workflow.preset.external_search.short') },
    color: '#d97706',
    bg: '#fff7ed',
    icon: externalSearchIcon,
    get defaultTitle() { return t('workflow.preset.external_search.title') },
    get placeholder() { return t('workflow.preset.external_search.placeholder') },
    defaultConfig: { get source() { return t('workflow.preset.external_search.src') }, get outputAlias() { return t('workflow.preset.external_search.out') } },
    get usageDescription() { return t('legacy.search_public_web_pages_news_and_industry_materials_by') },
    get usageExample() { return t('legacy.search_official_statistics_and_industry_reports_on_china_s') },
  },
  {
    type: 'call_tool',
    get label() { return t('workflow.preset.call_mcp.label') },
    get shortLabel() { return t('workflow.preset.call_mcp.short') },
    color: '#0f83a5',
    bg: '#eefbff',
    icon: callToolIcon,
    get defaultTitle() { return t('workflow.preset.call_mcp.title') },
    get placeholder() { return t('workflow.preset.call_mcp.placeholder') },
    defaultConfig: { get toolScope() { return t('workflow.preset.call_mcp.scope') }, get outputAlias() { return t('workflow.preset.call_mcp.out') } },
    get usageDescription() { return t('legacy.call_connected_tools_or_mcp_services_to_query_business') },
    get usageExample() { return t('legacy.call_the_order_query_tool_for_completed_east_china') },
  },
  {
    type: 'script_plugin',
    get label() { return t('workflow.preset.script_plugin.label') },
    get shortLabel() { return t('workflow.preset.script_plugin.short') },
    color: '#475569',
    bg: '#f1f5f9',
    icon: dataProcessingIcon,
    get defaultTitle() { return t('workflow.preset.script_plugin.title') },
    get placeholder() { return t('workflow.preset.script_plugin.placeholder') },
    defaultConfig: {
      runtime: 'python',
      get outputAlias() { return t('workflow.preset.script_plugin.out') },
      processingInstruction: '',
      selectedInputSource: 'all',
      selectedInputTypes: ['files', 'documents', 'images', 'urls', 'texts', 'data'],
      pluginCode: '',
    },
    get usageDescription() { return t('legacy.generate_and_run_deterministic_processing_code_from_natural_language') },
    get usageExample() { return t('legacy.read_the_project_execution_workbook_normalize_dates_to_yyyy') },
  },
  {
    type: 'generate_content',
    get label() { return t('workflow.preset.generate_content.label') },
    get shortLabel() { return t('workflow.preset.generate_content.short') },
    color: '#7c3aed',
    bg: '#f4f0ff',
    icon: generateContentIcon,
    get defaultTitle() { return t('workflow.preset.generate_content.title') },
    get placeholder() { return t('workflow.preset.generate_content.placeholder') },
    defaultConfig: { get input() { return t('workflow.preset.generate_content.in') }, get outputAlias() { return t('workflow.preset.generate_content.out') } },
    get usageDescription() { return t('legacy.write_reports_articles_summaries_and_plans_from_upstream_materials') },
    get usageExample() { return t('legacy.write_a_project_review_under_1_500_chinese_characters') },
  },
  {
    type: 'translate_rewrite',
    get label() { return t('workflow.preset.translate_doc.label') },
    get shortLabel() { return t('workflow.preset.translate_doc.short') },
    color: '#9333ea',
    bg: '#faf0ff',
    icon: translateRewriteIcon,
    get defaultTitle() { return t('workflow.preset.translate_doc.title') },
    get placeholder() { return t('workflow.preset.translate_doc.placeholder') },
    defaultConfig: { get mode() { return t('workflow.preset.translate_doc.mode') }, get outputAlias() { return t('workflow.preset.translate_doc.out') } },
    get usageDescription() { return t('legacy.translate_or_rewrite_upstream_documents_while_preserving_meaning_and') },
    get usageExample() { return t('legacy.translate_the_product_release_notes_into_english_while_preserving') },
  },
  {
    type: 'fill_table',
    get label() { return t('workflow.preset.fill_excel.label') },
    get shortLabel() { return t('workflow.preset.fill_excel.short') },
    color: '#0f766e',
    bg: '#effdfa',
    icon: fillTableIcon,
    get defaultTitle() { return t('workflow.preset.fill_excel.title') },
    get placeholder() { return t('workflow.preset.fill_excel.placeholder') },
    defaultConfig: { get target() { return t('workflow.preset.fill_excel.target') }, get outputAlias() { return t('workflow.preset.fill_excel.out') } },
    get usageDescription() { return t('legacy.write_upstream_structured_results_into_a_specified_spreadsheet_template') },
    get usageExample() { return t('legacy.fill_the_june_ledger_sheet_in_the_monthly_project') },
  },
  {
    type: 'review_check',
    get label() { return t('workflow.preset.review_check.label') },
    get shortLabel() { return t('legacy.review') },
    color: '#b45309',
    bg: '#fffbeb',
    icon: reviewCheckIcon,
    get defaultTitle() { return t('legacy.review_an_earlier_result') },
    get placeholder() { return t('workflow.preset.review_check.placeholder') },
    defaultConfig: {
      reviewSubject: '', reviewCriteria: '', reviewCriteriaMode: 'upstream', get outputAlias() { return t('legacy.review_findings') },
    },
    get usageDescription() { return t('legacy.guide_the_agent_to_review_earlier_facts_or_results') },
    get usageExample() { return t('legacy.compare_each_contract_clause_with_the_rules_cite_both') },
  },
  {
    type: 'export_delivery',
    get label() { return t('workflow.preset.export_deliverable.label') },
    get shortLabel() { return t('workflow.preset.export_deliverable.short') },
    color: '#ea580c',
    bg: '#fff4ed',
    icon: exportDeliveryIcon,
    get defaultTitle() { return t('workflow.preset.export_deliverable.title') },
    get placeholder() { return t('workflow.preset.export_deliverable.placeholder') },
    defaultConfig: { format: 'Word / PDF / Excel / PPT', get outputAlias() { return t('workflow.preset.export_deliverable.out') } },
    get usageDescription() { return t('legacy.export_upstream_final_content_to_deliverables_such_as_word') },
    get usageExample() { return t('legacy.export_the_east_china_q1_project_review_as_word') },
  },
];
