import { computed } from 'vue';
import { t } from '@/composables/i18n';
import type { WorkflowNodeType } from '@/api/skills';
import readMaterialIcon from '@/assets/workflow-node-icons/read-material.svg';
import extractInfoIcon from '@/assets/workflow-node-icons/extract-info.svg';
import reviewCheckIcon from '@/assets/workflow-node-icons/review-check.svg';
import extractResourcesIcon from '@/assets/workflow-node-icons/extract-resources.svg';
import understandImageIcon from '@/assets/workflow-node-icons/understand-image.svg';
import computeMetricIcon from '@/assets/workflow-node-icons/compute-metric.svg';
import dataCollectIcon from '@/assets/workflow-node-icons/data-collect.svg';
import internalSearchIcon from '@/assets/workflow-node-icons/internal-search.svg';
import externalSearchIcon from '@/assets/workflow-node-icons/external-search.svg';
import callToolIcon from '@/assets/workflow-node-icons/call-tool.svg';
import dataProcessingIcon from '@/assets/workflow-node-icons/data-processing.svg';
import generateContentIcon from '@/assets/workflow-node-icons/generate-content.svg';
import translateRewriteIcon from '@/assets/workflow-node-icons/translate-rewrite.svg';
import fillTableIcon from '@/assets/workflow-node-icons/fill-table.svg';
import exportDeliveryIcon from '@/assets/workflow-node-icons/export-delivery.svg';

export const workflowNodeTypes = computed<Array<{
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
}>>(() => [
  {
    type: 'read_material',
    label: t('legacy.read_material'),
    shortLabel: t('legacy.material'),
    color: '#2f6bff',
    bg: '#eef4ff',
    icon: readMaterialIcon,
    defaultTitle: t('legacy.read_uploaded_material'),
    placeholder: t('legacy.example_read_communication_data_documents_and_raw_materials_uploaded'),
    defaultConfig: { sourceType: 'upload', source: t('legacy.uploaded_material'), outputAlias: t('legacy.raw_material') },
    usageDescription: t('legacy.read_uploaded_material_or_an_authorized_organization_knowledge_document'),
    usageExample: t('legacy.read_the_uploaded_east_china_project_progress_report_and'),
  },
  {
    type: 'extract_resources',
    label: t('legacy.extract_resources'),
    shortLabel: t('legacy.resource'),
    color: '#0891b2',
    bg: '#ecfeff',
    icon: extractResourcesIcon,
    defaultTitle: t('legacy.extract_processable_resources'),
    placeholder: t('legacy.example_extract_images_urls_and_attachments_from_uploaded_documents'),
    defaultConfig: { resourceTypes: ['images', 'urls', 'attachments'], outputAlias: t('legacy.resource_list') },
    usageDescription: t('legacy.separate_images_web_links_and_attachments_from_upstream_materials'),
    usageExample: t('legacy.extract_all_embedded_screenshots_http_https_links_and_attachment'),
  },
  {
    type: 'understand_image',
    label: t('legacy.image_understanding'),
    shortLabel: t('legacy.ocr'),
    color: '#4f46e5',
    bg: '#eef2ff',
    icon: understandImageIcon,
    defaultTitle: t('legacy.understand_image_content'),
    placeholder: t('legacy.example_perform_multimodal_recognition_on_the_images_extracted_from'),
    defaultConfig: { input: t('legacy.upstream_image_resources'), outputAlias: t('legacy.image_understanding_results') },
    usageDescription: t('legacy.recognize_text_objects_interfaces_charts_and_key_visual_details'),
    usageExample: t('legacy.analyze_eight_upstream_social_platform_screenshots_and_extract_the'),
  },
  {
    type: 'extract_info',
    label: t('legacy.extract_info'),
    shortLabel: t('legacy.extract'),
    color: '#2563eb',
    bg: '#edf5ff',
    icon: extractInfoIcon,
    defaultTitle: t('legacy.extract_key_info'),
    placeholder: t('legacy.example_extract_total_readership_plays_and_interactions_from_uploaded'),
    defaultConfig: { target: t('legacy.key_fields_facts_metrics'), method: t('legacy.auto_identify'), outputAlias: t('legacy.extraction_results') },
    usageDescription: t('legacy.extract_specified_fields_facts_and_metrics_from_upstream_text'),
    usageExample: t('legacy.extract_the_project_name_owner_dates_contract_amount_current'),
  },
  {
    type: 'compute_metric',
    label: t('legacy.calculate_metrics'),
    shortLabel: t('legacy.stats'),
    color: '#16a36f',
    bg: '#effaf4',
    icon: computeMetricIcon,
    defaultTitle: t('legacy.calculate_core_metrics'),
    placeholder: t('legacy.example_aggregate_data_from_various_channels_calculate_proportions_sort'),
    defaultConfig: { method: t('legacy.sum_share_sort_anomaly_detection'), outputAlias: t('legacy.metrics_analysis') },
    usageDescription: t('legacy.run_defined_calculations_on_upstream_structured_data_such_as'),
    usageExample: t('legacy.aggregate_q1_2026_contract_and_collection_amounts_by_region'),
  },
  {
    type: 'data_collect',
    label: t('legacy.collect_data'),
    shortLabel: t('legacy.collect'),
    color: '#0d9488',
    bg: '#ecfdf5',
    icon: dataCollectIcon,
    defaultTitle: t('legacy.collect_web_data'),
    placeholder: t('legacy.example_collect_body_text_from_the_web_links_extracted'),
    defaultConfig: { source: t('legacy.web_links_upstream_urls'), outputAlias: t('legacy.collected_content') },
    usageDescription: t('legacy.visit_upstream_web_links_and_collect_page_titles_body'),
    usageExample: t('legacy.collect_news_pages_from_the_upstream_url_list_keeping'),
  },
  {
    type: 'internal_search',
    label: t('legacy.internal_search_304b39b'),
    shortLabel: t('legacy.internal_search'),
    color: '#a16207',
    bg: '#fff8e8',
    icon: internalSearchIcon,
    defaultTitle: t('legacy.query_internal_information'),
    placeholder: t('legacy.example_search_for_company_history_review_caliber_and_internal'),
    defaultConfig: { source: t('legacy.knowledge_regulation_base_history'), outputAlias: t('legacy.internal_basis') },
    usageDescription: t('legacy.search_configured_enterprise_knowledge_bases_policy_libraries_or_historical'),
    usageExample: t('legacy.search_the_project_management_policy_library_for_project_delay'),
  },
  {
    type: 'external_search',
    label: t('legacy.web_search_b84b2fd'),
    shortLabel: t('legacy.web_search_5742069'),
    color: '#d97706',
    bg: '#fff7ed',
    icon: externalSearchIcon,
    defaultTitle: t('legacy.search_external_info'),
    placeholder: t('legacy.example_search_public_industry_data_and_news_background_to'),
    defaultConfig: { source: t('legacy.public_webpages_news_industry_info'), outputAlias: t('legacy.external_info') },
    usageDescription: t('legacy.search_public_web_pages_news_and_industry_materials_by'),
    usageExample: t('legacy.search_official_statistics_and_industry_reports_on_china_s'),
  },
  {
    type: 'call_tool',
    label: t('legacy.call_tool'),
    shortLabel: t('legacy.tool'),
    color: '#0f83a5',
    bg: '#eefbff',
    icon: callToolIcon,
    defaultTitle: t('legacy.call_business_tool'),
    placeholder: t('legacy.example_call_mcp_or_corporate_tools_to_query_channel'),
    defaultConfig: { preferredToolId: '', preferredToolName: '', preferredMcpToolName: '', outputAlias: t('legacy.tool_data') },
    usageDescription: t('legacy.call_connected_tools_or_mcp_services_to_query_business'),
    usageExample: t('legacy.call_the_order_query_tool_for_completed_east_china'),
  },
  {
    type: 'script_plugin',
    label: t('legacy.data_processing'),
    shortLabel: t('legacy.processing'),
    color: '#475569',
    bg: '#f1f5f9',
    icon: dataProcessingIcon,
    defaultTitle: t('legacy.process_data'),
    placeholder: t('legacy.example_clean_up_an_uploaded_docx_organize_image_links'),
    defaultConfig: {
      runtime: 'python',
      outputAlias: t('legacy.processing_result'),
      processingInstruction: '',
      selectedInputSource: 'all',
      selectedInputTypes: ['files', 'documents', 'images', 'urls', 'texts', 'data'],
      pluginCode: '',
    },
    usageDescription: t('legacy.generate_and_run_deterministic_processing_code_from_natural_language'),
    usageExample: t('legacy.read_the_project_execution_workbook_normalize_dates_to_yyyy'),
  },
  {
    type: 'generate_content',
    label: t('legacy.generate_content'),
    shortLabel: t('legacy.generate'),
    color: '#7c3aed',
    bg: '#f4f0ff',
    icon: generateContentIcon,
    defaultTitle: t('legacy.generate_business_content'),
    placeholder: t('legacy.example_generate_formal_review_draft_based_on_metrics_analysis_2288fbd'),
    defaultConfig: { input: t('legacy.upstream_result'), outputAlias: t('legacy.draft') },
    usageDescription: t('legacy.write_reports_articles_summaries_and_plans_from_upstream_materials'),
    usageExample: t('legacy.write_a_project_review_under_1_500_chinese_characters'),
  },
  {
    type: 'translate_rewrite',
    label: t('legacy.translate_document'),
    shortLabel: t('legacy.translate'),
    color: '#9333ea',
    bg: '#faf0ff',
    icon: translateRewriteIcon,
    defaultTitle: t('legacy.translate_document_427cb1b'),
    placeholder: t('legacy.example_translate_report_into_target_language_while_keeping_terminology'),
    defaultConfig: { mode: t('legacy.translate_polish_expand_compress'), outputAlias: t('legacy.rewritten_draft') },
    usageDescription: t('legacy.translate_or_rewrite_upstream_documents_while_preserving_meaning_and'),
    usageExample: t('legacy.translate_the_product_release_notes_into_english_while_preserving'),
  },
  {
    type: 'fill_table',
    label: t('legacy.fill_create_table'),
    shortLabel: t('legacy.fill_table'),
    color: '#0f766e',
    bg: '#effdfa',
    icon: fillTableIcon,
    defaultTitle: t('legacy.fill_or_create_table'),
    placeholder: t('legacy.example_fill_statistical_results_into_designated_excel_or_generate'),
    defaultConfig: { target: t('legacy.word_excel_pdf_table'), outputAlias: t('legacy.table_result') },
    usageDescription: t('legacy.write_upstream_structured_results_into_a_specified_spreadsheet_template'),
    usageExample: t('legacy.fill_the_june_ledger_sheet_in_the_monthly_project'),
  },
  {
    type: 'review_check',
    label: t('legacy.review_check'),
    shortLabel: t('legacy.review'),
    color: '#b45309',
    bg: '#fffbeb',
    icon: reviewCheckIcon,
    defaultTitle: t('legacy.review_an_earlier_result'),
    placeholder: t('legacy.example_review_contract_clauses_against_the_rules_and_list'),
    defaultConfig: {
      reviewSubject: '', reviewCriteria: '', reviewCriteriaMode: 'upstream', outputAlias: t('legacy.review_findings'),
    },
    usageDescription: t('legacy.guide_the_agent_to_review_earlier_facts_or_results'),
    usageExample: t('legacy.compare_each_contract_clause_with_the_rules_cite_both'),
  },
  {
    type: 'export_delivery',
    label: t('legacy.export_delivery'),
    shortLabel: t('legacy.export'),
    color: '#ea580c',
    bg: '#fff4ed',
    icon: exportDeliveryIcon,
    defaultTitle: t('legacy.export_delivery_file'),
    placeholder: t('legacy.example_export_review_draft_as_word_and_pdf_for'),
    defaultConfig: { format: 'Word / PDF / Excel / PPT', outputAlias: t('legacy.delivery_file') },
    usageDescription: t('legacy.export_upstream_final_content_to_deliverables_such_as_word'),
    usageExample: t('legacy.export_the_east_china_q1_project_review_as_word'),
  },
]);
