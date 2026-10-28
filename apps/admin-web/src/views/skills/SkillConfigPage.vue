<template src="./SkillConfigPageTemplate.html"></template>

<script setup lang="ts">
import { useSkillWritingStyle } from './useSkillWritingStyle';
import { useSkillScriptPlugin, type WorkflowStep } from './useSkillScriptPlugin';

import { createSectionNode, normalizeStringArray, parseMultilineItems, hydrateSectionStructure, serializeSectionStructure, flattenSectionTitles, flattenSectionPreview, type SectionNode, type SectionPreviewItem } from './workflowSectionStructure';

import { workflowNodeTypes } from './workflowNodeCatalog';
import { workflowTextInferenceRules } from '@/locales/workflowTextInferenceRules';
import { publishChannelSuggestions, contentFormSuggestions, targetAudienceSuggestions, preferredStyleSuggestions, type LocalizedSelectOption } from '@/locales/workflowSelectOptions';
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, onUpdated, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useMessage } from 'naive-ui';
import { t, translateSourceText, useLocale } from '@/composables/i18n';
import { localizedServerText } from '@/utils/serverText';
import { localizeWorkflowDefaults } from './workflowDefaultLocale';
import { useTheme } from '@/composables/theme';
import { workflowAccent, workflowButtonColors } from '@/theme/workflow-colors';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import {
  checkWorkflowNodes,
  fetchSkill,
  fetchSkills,
  generateWorkflowNodes,
  polishWorkflowNode,
  updateSkill,
  type SkillItem,
  type SkillType,
  type ScriptPluginCheckResult,
  type WorkflowNodeDraft,
  type WorkflowNodeType,
} from '@/api/skills';
import { fetchTools, type ExternalToolItem } from '@/api/tools';
import KnowledgeDocumentSourceConfig from '@/components/workflow/KnowledgeDocumentSourceConfig.vue';
import ReviewCheckNodeConfig from '@/components/workflow/ReviewCheckNodeConfig.vue';
import { bindReviewSources } from '@/components/workflow/reviewSourceBinding';
import SkillPublishDialog from './SkillPublishDialog.vue';
import { missingWorkflowSelection } from './workflowRequiredSelections';

const PythonCodeEditor = defineAsyncComponent(() => import('@/components/PythonCodeEditor.vue'));
const { activeTheme } = useTheme();

interface CoverageItem {
  key: string;
  label: string;
  covered: boolean;
}

interface ReadinessItem {
  key: string;
  label: string;
  ready: boolean;
}

interface WorkflowTestResult {
  testedAt: string;
  pass: boolean;
  logic: {
    label: string;
    level: 'success' | 'warning';
    summary: string;
  };
  coverage: CoverageItem[];
  readiness: ReadinessItem[];
  suggestions: string[];
  conclusion: string;
}

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { locale } = useLocale();

const loading = ref(false);
const headerTeleportReady = ref(false);
const headerActionsElement = ref<HTMLElement | null>(null);
const detailRequestSequence = ref(0);
const saving = ref(false);
const publishVisible = ref(false);
const testing = ref(false);
const optimizing = ref(false);
const generatingSteps = ref(false);
const supplementingStep = ref(false);
const polishingStepId = ref('');
const styleEnriching = ref(false);
const skill = ref<SkillItem | null>(null);
const workflowSteps = ref<WorkflowStep[]>([]);
const workflowAiUndoStack = ref<Array<{ label: string; steps: WorkflowStep[]; activeStepId: string }>>([]);
const activeStepId = ref('');
const draggingStepId = ref('');
const dragOverStepId = ref('');
const newStepText = ref('');
const testResult = ref<WorkflowTestResult | null>(null);
const stepGenerationError = ref('');
const restoringWorkflow = ref(false);
const checkingScriptStepId = ref('');
const fixingScriptStepId = ref('');
const generatingScriptStepId = ref('');
const scriptAdvancedDrawerVisible = ref(false);
const activeScriptStepId = ref('');
const scriptDrawerSaving = ref(false);
const scriptCheckResults = ref<Record<string, ScriptPluginCheckResult & { signature?: string }>>({});
const publishChannelInput = ref<string[]>([]);
const contentFormInput = ref<string[]>([]);
const targetAudienceInput = ref<string[]>([]);
const preferredStyleInput = ref<string[]>([]);
const targetLengthMin = ref<number | null>(null);
const targetLengthMax = ref<number | null>(null);
const targetLengthUnit = ref('chinese_chars');
const sectionStructure = ref<SectionNode[]>([]);
const requiredElementsText = ref('');
const forbiddenElementsText = ref('');
const styleInputProfile = ref<Record<string, any>>({});
const styleContractJson = ref<Record<string, any>>({});
const styleSkillMarkdown = ref('');
const writingSkillOptions = ref<Array<{ label: string; value: string }>>([]);
const toolRows = ref<ExternalToolItem[]>([]);
const toolOptionsLoading = ref(false);
const activeScriptStep = computed(() => workflowSteps.value.find((item) => item.id === activeScriptStepId.value && item.type === 'script_plugin') || null);
const toolOptions = computed(() => toolRows.value.map((item) => ({
  label: `${item.name} (${item.type.toUpperCase()})${item.status === 'disabled' ? ` - ${t('legacy.disabled_6c7dcbb')}` : ''}`,
  value: item.id,
  disabled: item.status === 'disabled',
})));



const localizedOptionLabel = (item: LocalizedSelectOption) => (locale.value === 'zh-CN' ? item.zh : item.en);
const localizedValueMap = computed(() => {
  const entries = [
    ...publishChannelSuggestions,
    ...contentFormSuggestions,
    ...targetAudienceSuggestions,
    ...preferredStyleSuggestions,
  ];
  return new Map(entries.flatMap((item) => [
    [item.value, localizedOptionLabel(item)],
    [item.zh, localizedOptionLabel(item)],
    [item.en, localizedOptionLabel(item)],
    ...(item.aliases || []).map((alias) => [alias, localizedOptionLabel(item)] as [string, string]),
  ] as [string, string][]));
});
const formatLocalizedValues = (items: string[], separator = '、') => (
  items.length
    ? items.map((item) => localizedValueMap.value.get(item) || item).join(separator)
    : t('legacy.not_configured')
);
const toSelectOptions = (items: LocalizedSelectOption[]) => computed(() => (
  items.map((item) => ({ label: localizedOptionLabel(item), value: item.value }))
));
const publishChannelOptions = toSelectOptions(publishChannelSuggestions);
const contentFormOptions = toSelectOptions(contentFormSuggestions);
const targetAudienceOptions = toSelectOptions(targetAudienceSuggestions);
const preferredStyleOptions = toSelectOptions(preferredStyleSuggestions);

const workflowTypeMap = computed(() => Object.fromEntries(workflowNodeTypes.value.map((item) => [item.type, item])));
function reviewSourceOptions(index: number): Array<{ id: string; alias: string }> {
  return workflowSteps.value.slice(0, index).map(item => ({
    id: item.id, alias: String(item.outputAlias || item.businessConfig?.outputAlias || '').trim(),
  })).filter(item => item.alias);
}
const normalizedStepText = computed(() => workflowSteps.value.map((item) => buildNodeText(item).trim()).filter(Boolean).join('\n'));
const workflowPreviewNodes = computed(() => workflowSteps.value.map((item) => ({
  id: item.id,
  label: workflowTypeLabel(item.type),
  type: item.type,
  color: workflowTypeMeta(item.type).color,
  icon: workflowTypeMeta(item.type).icon,
})));
const stepListLoadingText = computed(() => {
  if (optimizing.value) return t('legacy.optimizing_current_business_steps');
  if (supplementingStep.value) return t('legacy.supplementing_business_steps');
  return t('legacy.generating_business_logic_steps');
});
const canEnrichWritingStyle = computed(() => {
  if (!skill.value?.name?.trim()) return false;
  return Boolean(skill.value.description?.trim() || skill.value.scenario?.trim());
});
const requiredElementsItems = computed(() => parseMultilineItems(requiredElementsText.value));
const requiredSectionsItems = computed(() => flattenSectionTitles(sectionStructure.value));
const forbiddenElementsItems = computed(() => parseMultilineItems(forbiddenElementsText.value));
const sectionStructurePreview = computed(() => flattenSectionPreview(sectionStructure.value));
const targetLengthLabel = computed(() => {
  const min = Number(targetLengthMin.value || 0);
  const max = Number(targetLengthMax.value || 0);
  if (min > 0 && max > 0) return t('legacy.words', { min, max });
  if (min > 0) return t('legacy.min_words', { min });
  if (max > 0) return t('legacy.max_words', { max });
  return t('legacy.not_configured');
});

watch(normalizedStepText, () => {
  if (restoringWorkflow.value) {
    restoringWorkflow.value = false;
    return;
  }
  if (testResult.value) {
    testResult.value = null;
  }
});

function typeLabel(type: SkillType): string {
  return type === 'workflow' ? t('legacy.workflow') : t('legacy.writing_guidelines');
}

function createId(): string {
  return `step_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function workflowTypeMeta(type: WorkflowNodeType | string) {
  return workflowTypeMap.value[String(type)] || workflowTypeMap.value.generate_content || workflowNodeTypes.value[0];
}

function workflowTypeLabel(type: WorkflowNodeType | string): string {
  return workflowTypeMeta(type).label;
}

function serializeWorkflowNodeCatalog() {
  return workflowNodeTypes.value.map((item) => ({
    type: item.type,
    name: item.label,
    usageDescription: String(item.usageDescription || ''),
    usageExample: String(item.usageExample || ''),
  }));
}

function createWorkflowNode(type: WorkflowNodeType = 'extract_info', seed: Partial<WorkflowStep> = {}): WorkflowStep {
  const meta = workflowTypeMeta(type);
  const businessConfig = {
    ...localizeWorkflowDefaults(meta.defaultConfig || {}),
    ...(seed.businessConfig || {}),
  };
  const outputAlias = seed.outputAlias || (seed.businessConfig?.outputAlias
    ? String(businessConfig.outputAlias).trim()
    : translateSourceText(String(businessConfig.outputAlias || '')).trim());
  businessConfig.outputAlias = outputAlias;
  return {
    id: seed.id || createId(),
    type,
    title: seed.title || translateSourceText(meta.defaultTitle),
    text: seed.text || '',
    businessConfig,
    boundWritingSkillId: seed.boundWritingSkillId || '',
    outputAlias,
  };
}

function buildNodeText(node: Partial<WorkflowStep>): string {
  const title = String(node.title || '').trim();
  const desc = String(node.text || '').trim();
  if (title && desc) return `${title}：${desc}`;
  return desc || title;
}

function serializeWorkflowNodes(): WorkflowNodeDraft[] {
  return workflowSteps.value
    .map((item) => ({
      id: item.id,
      type: item.type,
      title: item.title.trim(),
      description: item.type === 'script_plugin'
        ? String(item.businessConfig?.processingInstruction || '').trim()
        : item.text.trim(),
      businessConfig: {
        ...(item.businessConfig || {}),
        outputAlias: item.outputAlias || item.businessConfig?.outputAlias || '',
      },
      boundWritingSkillId: item.type === 'generate_content' ? item.boundWritingSkillId || '' : '',
      outputAlias: item.outputAlias || item.businessConfig?.outputAlias || '',
    }))
    .filter((item) => item.title || item.description);
}

function serializeWorkflowSteps() {
  return serializeWorkflowNodes().map((item) => ({
    id: item.id || createId(),
    text: [item.title, item.description].filter(Boolean).join('：'),
  }));
}

function normalizeWorkflowNode(value: any, index = 0): WorkflowStep | null {
  if (typeof value === 'string') {
    const text = value.trim();
    const type = inferWorkflowNodeTypeFromText(text);
    return text ? createWorkflowNode(type, { id: createId(), text, title: translateSourceText(workflowTypeMeta(type).defaultTitle) }) : null;
  }
  if (!value || typeof value !== 'object') return null;
  const rawText = String(value.description || value.text || value.instruction || '').trim();
  const type = workflowNodeTypes.value.some((item) => item.type === value.type)
    ? value.type as WorkflowNodeType
    : inferWorkflowNodeTypeFromText(`${value.title || value.name || ''} ${rawText}`);
  const config = value.businessConfig && typeof value.businessConfig === 'object'
    ? value.businessConfig
    : value.business_config && typeof value.business_config === 'object'
      ? value.business_config
      : {};
  return createWorkflowNode(type, {
    id: String(value.id || createId()),
    title: String(value.title || value.name || '').trim(),
    text: rawText,
    businessConfig: type === 'script_plugin' && !config.processingInstruction
      ? { ...config, processingInstruction: rawText }
      : config,
    boundWritingSkillId: String(value.boundWritingSkillId || value.bound_writing_skill_id || '').trim(),
    outputAlias: String(value.outputAlias || value.output_alias || config.outputAlias || config.output_alias || '').trim(),
  });
}

function inferWorkflowNodeTypeFromText(text: string): WorkflowNodeType {
  const normalized = text.toLowerCase();
  const rules: ReadonlyArray<{ type: WorkflowNodeType; keywords: readonly string[] }> = workflowTextInferenceRules;
  return rules.find((rule) => rule.keywords.some((keyword) => normalized.includes(keyword)))?.type || 'generate_content';
}

function beginRestoreWorkflow() {
  restoringWorkflow.value = true;
  window.setTimeout(() => {
    restoringWorkflow.value = false;
  }, 0);
}

function cloneWorkflowStep(step: WorkflowStep): WorkflowStep {
  return {
    ...step,
    businessConfig: JSON.parse(JSON.stringify(step.businessConfig || {})),
  };
}

function snapshotWorkflowSteps(): WorkflowStep[] {
  return workflowSteps.value.map((step) => cloneWorkflowStep(step));
}

function pushWorkflowAiUndo(label: string) {
  workflowAiUndoStack.value = [
    {
      label,
      steps: snapshotWorkflowSteps(),
      activeStepId: activeStepId.value,
    },
    ...workflowAiUndoStack.value,
  ].slice(0, 10);
}

function undoLastAiWorkflowChange() {
  const [latest, ...rest] = workflowAiUndoStack.value;
  if (!latest) return;
  beginRestoreWorkflow();
  workflowSteps.value = latest.steps.map((step) => cloneWorkflowStep(step));
  activeStepId.value = latest.activeStepId || workflowSteps.value[0]?.id || '';
  workflowAiUndoStack.value = rest;
  testResult.value = null;
  message.success(t('legacy.last_ai_change_undone'));
}

function currentStepSnapshot(): string[] {
  return workflowSteps.value.map((item) => item.text.trim()).filter(Boolean);
}

function normalizeStoredCheck(value: any): WorkflowTestResult | null {
  const result = value?.result || value;
  if (!result || typeof result !== 'object') return null;
  const logic = result.logic && typeof result.logic === 'object' ? result.logic : {};
  return {
    testedAt: String(result.testedAt || value?.checkedAt || ''),
    pass: Boolean(result.pass),
    logic: {
      label: String(logic.label || t('legacy.clarify_needed')),
      level: logic.level === 'success' ? 'success' : 'warning',
      summary: String(logic.summary || t('legacy.no_logical_explanation_saved')),
    },
    coverage: Array.isArray(result.coverage) ? result.coverage : [],
    readiness: Array.isArray(result.readiness) ? result.readiness : [],
    suggestions: Array.isArray(result.suggestions) ? result.suggestions : [],
    conclusion: String(result.conclusion || t('legacy.no_clear_conclusion_was_saved')),
  };
}

const { addSection, moveSection, removeSection, buildWritingStyleContractJson, buildWritingStyleDraft, applyWritingStyleContract, hydrateWritingStyle, enrichWritingStyle, saveWritingStyle } = useSkillWritingStyle({ skill, saving, styleEnriching, publishChannelInput, contentFormInput, targetAudienceInput, preferredStyleInput, targetLengthMin, targetLengthMax, targetLengthUnit, sectionStructure, requiredElementsItems, forbiddenElementsItems, requiredElementsText, forbiddenElementsText, styleInputProfile, styleContractJson, styleSkillMarkdown, message });

function isSameStepSnapshot(left: unknown, right: string[]): boolean {
  if (!Array.isArray(left)) return false;
  const normalized = left.map((item) => String(item || '').trim()).filter(Boolean);
  return normalized.length === right.length && normalized.every((item, index) => item === right[index]);
}

function hydrateWorkflow(source: SkillItem): boolean {
  const rawNodes = source.config?.workflowNodes;
  if (Array.isArray(rawNodes) && rawNodes.length) {
    const hydrated = rawNodes
      .map((item: any, index: number) => normalizeWorkflowNode(item, index))
      .filter(Boolean) as WorkflowStep[];
    if (hydrated.length) {
      beginRestoreWorkflow();
      workflowAiUndoStack.value = [];
      workflowSteps.value = hydrated;
      activeStepId.value = workflowSteps.value[0]?.id || '';
      const lastCheck = source.config?.lastWorkflowCheck || source.config?.lastFrontendTest;
      testResult.value = isSameStepSnapshot(lastCheck?.stepsSnapshot, currentStepSnapshot())
        ? normalizeStoredCheck(lastCheck)
        : null;
      stepGenerationError.value = '';
      return true;
    }
  }
  const rawSteps = source.config?.workflowSteps;
  if (Array.isArray(rawSteps) && rawSteps.length) {
    const hydrated = rawSteps
      .map((item: any, index: number) => normalizeWorkflowNode(
        typeof item === 'object'
          ? { ...item, description: item?.text || item?.description || '' }
          : String(item || ''),
        index,
      ))
      .filter(Boolean) as WorkflowStep[];
    if (hydrated.length) {
      beginRestoreWorkflow();
      workflowAiUndoStack.value = [];
      workflowSteps.value = hydrated;
      activeStepId.value = workflowSteps.value[0]?.id || '';
      const lastCheck = source.config?.lastWorkflowCheck || source.config?.lastFrontendTest;
      testResult.value = isSameStepSnapshot(lastCheck?.stepsSnapshot, currentStepSnapshot())
        ? normalizeStoredCheck(lastCheck)
        : null;
      stepGenerationError.value = '';
      return true;
    }
  }
  beginRestoreWorkflow();
  workflowAiUndoStack.value = [];
  workflowSteps.value = [];
  activeStepId.value = workflowSteps.value[0]?.id || '';
  testResult.value = null;
  stepGenerationError.value = '';
  return false;
}

function moveStep(index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= workflowSteps.value.length) return;
  const next = [...workflowSteps.value];
  const [item] = next.splice(index, 1);
  next.splice(nextIndex, 0, item);
  workflowSteps.value = next;
}

function onDragStart(stepId: string, event: DragEvent) {
  draggingStepId.value = stepId;
  dragOverStepId.value = '';
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.dropEffect = 'move';
    event.dataTransfer.setData('text/plain', stepId);
  }
}

function onDragOver(stepId: string) {
  if (!draggingStepId.value || draggingStepId.value === stepId) return;
  dragOverStepId.value = stepId;
}

function onDrop(targetStepId: string) {
  const sourceStepId = draggingStepId.value;
  draggingStepId.value = '';
  dragOverStepId.value = '';
  if (!sourceStepId || sourceStepId === targetStepId) return;
  const current = [...workflowSteps.value];
  const fromIndex = current.findIndex((item) => item.id === sourceStepId);
  const toIndex = current.findIndex((item) => item.id === targetStepId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return;
  const [dragged] = current.splice(fromIndex, 1);
  current.splice(toIndex, 0, dragged);
  workflowSteps.value = current;
}

function onDragEnd() {
  draggingStepId.value = '';
  dragOverStepId.value = '';
}

function removeStep(stepId: string) {
  if (workflowSteps.value.length <= 1) {
    message.warning(t('legacy.keep_at_least_one_business_step'));
    return;
  }
  workflowSteps.value = workflowSteps.value.filter((item) => item.id !== stepId);
  if (activeStepId.value === stepId) {
    activeStepId.value = workflowSteps.value[0]?.id || '';
  }
}

function handleNodeTypeChange(step: WorkflowStep, newType: WorkflowNodeType) {
  step.type = newType;
  const meta = workflowTypeMeta(newType);
  if (meta.defaultConfig) {
    if (!step.businessConfig) {
      step.businessConfig = {};
    }
    const defaults = localizeWorkflowDefaults(meta.defaultConfig);
    for (const key of Object.keys(defaults)) {
      if (step.businessConfig[key] === undefined) {
        step.businessConfig[key] = JSON.parse(JSON.stringify(defaults[key]));
      }
    }
  }
}

function appendNodeByType(type: WorkflowNodeType) {
  const text = newStepText.value.trim();
  const next = createWorkflowNode(type, text ? { text } : {});
  const used = new Set(workflowSteps.value.map(item => item.outputAlias || item.businessConfig?.outputAlias));
  const base = next.outputAlias || next.title || t('skills.nodeOutput');
  let index = 2;
  while (used.has(next.outputAlias)) next.outputAlias = `${base}${index++}`;
  next.businessConfig.outputAlias = next.outputAlias;
  workflowSteps.value = [...workflowSteps.value, next];
  activeStepId.value = next.id;
  if (text) newStepText.value = '';
  testResult.value = null;
}

function mapGeneratedNodes(items: WorkflowNodeDraft[]): WorkflowStep[] {
  return (items || [])
    .map((item, index) => {
      const normalized = normalizeWorkflowNode(item, index);
      if (!normalized) return null;
      return normalized;
    })
    .filter(Boolean) as WorkflowStep[];
}

function buildCheckRecord(result: WorkflowTestResult) {
  return {
    id: `check_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
    checkedAt: result.testedAt,
    stepsSnapshot: currentStepSnapshot(),
    result,
  };
}

async function persistWorkflowCheck(result: WorkflowTestResult) {
  if (!skill.value) return;
  const record = buildCheckRecord(result);
  const existingHistory = Array.isArray(skill.value.config?.workflowCheckHistory)
    ? skill.value.config.workflowCheckHistory
    : [];
  try {
    const updated = await updateSkill(skill.value.id, {
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      type: skill.value.type,
      enabled: skill.value.enabled !== false,
      config: {
        ...(skill.value.config || {}),
        workflowNodes: serializeWorkflowNodes(),
        workflowSteps: serializeWorkflowSteps(),
        lastWorkflowCheck: record,
        workflowCheckHistory: [record, ...existingHistory].slice(0, 10),
      },
    });
    skill.value = updated;
  } catch (error: any) {
    message.warning(error?.response?.data?.detail || t('legacy.failed_to_save_check_result_to_skill'));
  }
}

async function regenerateSteps() {
  if (!skill.value) return;
  generatingSteps.value = true;
  stepGenerationError.value = '';
  try {
    const result = await generateWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      existingNodes: [],
      nodeCatalog: serializeWorkflowNodeCatalog(),
      maxNodes: 12,
      mode: 'generate',
    });
    const generated = mapGeneratedNodes(result.nodes || []);
    if (generated.length) {
      pushWorkflowAiUndo(t('legacy.regenerate_steps'));
      workflowSteps.value = generated;
      activeStepId.value = workflowSteps.value[0]?.id || '';
      testResult.value = null;
      stepGenerationError.value = '';
      message.success(t('legacy.business_logic_steps_generated_successfully'));
    } else {
      stepGenerationError.value = localizedServerText(result.message, t('legacy.no_usable_business_logic_steps_generated'));
      message.warning(localizedServerText(result.message, t('legacy.no_business_logic_steps_generated_please_adjust_the_description')));
    }
  } catch (error: any) {
    stepGenerationError.value = localizedServerText(error?.response?.data?.detail || error?.message, t('legacy.failed_to_generate_steps_please_try_again_later'));
    message.error(stepGenerationError.value);
  } finally {
    generatingSteps.value = false;
  }
}

async function optimizeSteps() {
  if (!skill.value) return;
  const existingNodes = serializeWorkflowNodes();
  if (!existingNodes.length) {
    message.warning(t('legacy.please_generate_or_enter_steps_before_optimizing'));
    return;
  }
  optimizing.value = true;
  stepGenerationError.value = '';
  try {
    const result = await generateWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      existingNodes,
      nodeCatalog: serializeWorkflowNodeCatalog(),
      maxNodes: Math.max(8, Math.min(12, existingNodes.length + 3)),
      mode: 'optimize',
    });
    const optimized = mapGeneratedNodes(result.nodes || []);
    if (!optimized.length) {
      stepGenerationError.value = localizedServerText(result.message, t('legacy.no_usable_optimization_results_returned'));
      message.warning(stepGenerationError.value);
      return;
    }
    pushWorkflowAiUndo(t('legacy.ai_optimize_steps'));
    workflowSteps.value = optimized;
    activeStepId.value = workflowSteps.value[0]?.id || '';
    testResult.value = null;
    message.success(t('legacy.optimization_completed_based_on_current_steps'));
  } catch (error: any) {
    stepGenerationError.value = localizedServerText(error?.response?.data?.detail || error?.message, t('legacy.failed_to_optimize_please_try_again_later'));
    message.error(stepGenerationError.value);
  } finally {
    optimizing.value = false;
  }
}

async function supplementStepWithAi() {
  if (!skill.value) return;
  const supplement = newStepText.value.trim();
  if (!supplement) return;
  supplementingStep.value = true;
  stepGenerationError.value = '';
  try {
    const result = await generateWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      supplement,
      nodeCatalog: serializeWorkflowNodeCatalog(),
      mode: 'supplement_step',
    });
    const supplemented = mapGeneratedNodes(result.nodes || []);
    if (!supplemented.length) {
      stepGenerationError.value = localizedServerText(result.message, t('legacy.no_usable_supplemental_results_returned'));
      message.warning(stepGenerationError.value);
      return;
    }
    const nextStep: WorkflowStep = {
      id: createId(),
      type: supplemented[0]?.type || 'generate_content',
      title: supplemented[0]?.title || t('legacy.supplement_node'),
      text: supplemented[0]?.text || supplement,
      businessConfig: supplemented[0]?.businessConfig || {},
      boundWritingSkillId: supplemented[0]?.boundWritingSkillId || '',
      outputAlias: supplemented[0]?.outputAlias || '',
    };
    pushWorkflowAiUndo(t('legacy.ai_optimize_add'));
    workflowSteps.value = [...workflowSteps.value, nextStep];
    activeStepId.value = nextStep.id;
    newStepText.value = '';
    testResult.value = null;
    message.success(t('legacy.new_step_supplemented_and_added'));
  } catch (error: any) {
    stepGenerationError.value = localizedServerText(error?.response?.data?.detail || error?.message, t('legacy.failed_to_supplement_step_please_try_again_later'));
    message.error(stepGenerationError.value);
  } finally {
    supplementingStep.value = false;
  }
}

async function polishStepRequirement(step: WorkflowStep) {
  if (!skill.value) return;
  const currentText = String(step.text || '').trim();
  if (!currentText) {
    message.warning(t('legacy.please_enter_node_requirement_first'));
    return;
  }
  polishingStepId.value = step.id;
  stepGenerationError.value = '';
  try {
    const result = await polishWorkflowNode({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      node: {
        id: step.id,
        type: step.type,
        title: step.title,
        description: step.text,
        businessConfig: step.businessConfig || {},
        boundWritingSkillId: step.boundWritingSkillId || '',
        outputAlias: step.outputAlias || '',
      },
      existingNodes: serializeWorkflowNodes(),
      nodeCatalog: serializeWorkflowNodeCatalog(),
    });
    const polished = String(result.text || '').trim();
    if (!polished) {
      stepGenerationError.value = localizedServerText(result.message, t('legacy.no_usable_polish_result_returned'));
      message.warning(stepGenerationError.value);
      return;
    }
    if (polished === currentText) {
      message.info(t('legacy.ai_polish_did_not_change_the_content'));
      return;
    }
    pushWorkflowAiUndo(t('legacy.ai_polish'));
    step.text = polished;
    activeStepId.value = step.id;
    testResult.value = null;
    message.success(t('legacy.node_requirement_polished'));
  } catch (error: any) {
    stepGenerationError.value = localizedServerText(error?.response?.data?.detail || error?.message, t('legacy.failed_to_polish_node_requirement_please_try_again_later'));
    message.error(stepGenerationError.value);
  } finally {
    polishingStepId.value = '';
  }
}

async function runWorkflowTest() {
  if (!skill.value) return;
  const steps = workflowSteps.value.map((item) => buildNodeText(item).trim()).filter(Boolean);
  if (!steps.length) {
    message.warning(t('legacy.please_generate_or_enter_steps_first'));
    return;
  }
  testing.value = true;
  try {
    const result = await checkWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      steps,
      nodes: serializeWorkflowNodes(),
    });
    const checkedAt = formatAdminDateTime(new Date().toISOString(), '');
    const nextResult: WorkflowTestResult = {
      testedAt: checkedAt,
      pass: Boolean(result.pass),
      logic: {
        label: result.logic?.label || t('legacy.clarify_needed'),
        level: result.logic?.level === 'success' ? 'success' : 'warning',
        summary: result.logic?.summary || t('legacy.the_backend_did_not_return_a_clear_logic_explanation'),
      },
      coverage: Array.isArray(result.coverage) ? result.coverage : [],
      readiness: Array.isArray(result.readiness) ? result.readiness : [],
      suggestions: Array.isArray(result.suggestions) && result.suggestions.length
        ? result.suggestions
        : [t('legacy.no_suggestions_returned_check_if_steps_cover_goals_inputs')],
      conclusion: result.conclusion || t('legacy.no_conclusion_returned'),
    };
    testResult.value = nextResult;
    await persistWorkflowCheck(nextResult);
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_check_business_logic_please_try_again_later'));
  } finally {
    testing.value = false;
  }
}

const { scriptPluginInstructionSignature, scriptPluginSignature, isScriptPluginGenerated, isScriptPluginCheckPassed, persistScriptPluginCheck, scriptCheckIssueItems, invalidateScriptPluginCheck, openScriptAdvancedDrawer, scriptPluginContextNodes, generateScriptPluginStep, checkScriptPluginStep, fixScriptPluginStep, ensureScriptPluginsChecked, ensureScriptPluginStepReady, saveScriptAdvancedDrawer } = useSkillScriptPlugin({ skill, scriptCheckResults, activeScriptStepId, activeStepId, scriptAdvancedDrawerVisible, generatingScriptStepId, checkingScriptStepId, fixingScriptStepId, workflowSteps, activeScriptStep, scriptDrawerSaving, message, serializeWorkflowNodes });

async function saveWorkflow(): Promise<boolean> {
  if (!skill.value) return false;
  const workflowNodes = serializeWorkflowNodes();
  if (!workflowNodes.length) {
    message.warning(t('legacy.please_fill_in_at_least_one_business_step'));
    return false;
  }
  const missingSelection = missingWorkflowSelection(workflowNodes);
  if (missingSelection) {
    activeStepId.value = missingSelection.nodeId;
    message.warning(t(missingSelection.messageKey));
    return false;
  }
  const aliases = workflowNodes.map(node => String(node.outputAlias || '').trim()).filter(Boolean);
  if (aliases.length !== new Set(aliases).size) {
    message.warning(t('legacy.step_output_names_must_be_unique_give_each_material'));
    return false;
  }
  const invalidReviewId = bindReviewSources(workflowNodes);
  if (invalidReviewId) {
    activeStepId.value = invalidReviewId;
    message.warning(t('legacy.select_a_valid_earlier_result_and_criteria_for_review'));
    return false;
  }
  saving.value = true;
  try {
    if (!(await ensureScriptPluginsChecked())) {
      return false;
    }
    const nodes = workflowNodes;
    const updated = await updateSkill(skill.value.id, {
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      type: skill.value.type,
      enabled: skill.value.enabled !== false,
      config: {
        ...(skill.value.config || {}),
        workflowNodes: nodes,
        workflowSteps: serializeWorkflowSteps(),
      },
    });
    skill.value = updated;
    hydrateWorkflow(updated);
    message.success(t('legacy.workflow_configuration_saved'));
    return true;
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('legacy.failed_to_save_skill'));
    return false;
  } finally {
    saving.value = false;
  }
}

async function prepareWorkflowPublish() { if (await saveWorkflow()) publishVisible.value = true; }
async function prepareStylePublish() { if (await saveWritingStyle()) publishVisible.value = true; }
function handlePublished(updated: SkillItem) { skill.value = updated; }

function goBack() {
  router.push('/skills');
}

function updateHeaderTitle(detail: SkillItem | null) {
  window.dispatchEvent(new CustomEvent('askai-admin-title-change', {
    detail: {
      routeName: 'SkillConfig',
      title: detail?.name || '',
      tag: detail ? typeLabel(detail.type) : '',
    },
  }));
}

async function loadDetail() {
  const requestSequence = ++detailRequestSequence.value;
  const id = String(route.params.id || '');
  if (!id) {
    skill.value = null;
    return;
  }
  loading.value = true;
  try {
    const detail = await fetchSkill(id);
    if (requestSequence !== detailRequestSequence.value || id !== String(route.params.id || '')) return;
    skill.value = detail;
    updateHeaderTitle(detail);
    if (detail.type === 'workflow') {
      hydrateWorkflow(detail);
    } else {
      hydrateWritingStyle(detail);
    }
  } catch (error: any) {
    if (requestSequence !== detailRequestSequence.value) return;
    skill.value = null;
    updateHeaderTitle(null);
    message.error(error?.response?.data?.detail || t('legacy.failed_to_load_skill_details'));
  } finally {
    if (requestSequence === detailRequestSequence.value) {
      loading.value = false;
    }
  }
}

async function loadWritingSkillOptions() {
  try {
    const rows = await fetchSkills();
    writingSkillOptions.value = rows
      .filter((item) => item.type === 'writing_style' && item.enabled !== false)
      .map((item) => ({ label: item.name, value: item.id }));
  } catch {
    writingSkillOptions.value = [];
  }
}

async function loadToolOptions() {
  toolOptionsLoading.value = true;
  try {
    toolRows.value = await fetchTools();
  } catch {
    toolRows.value = [];
  } finally {
    toolOptionsLoading.value = false;
  }
}

function selectedToolId(step: WorkflowStep): string | null {
  return String(step.businessConfig?.preferredToolId || step.businessConfig?.toolId || '').trim() || null;
}

function selectedTool(step: WorkflowStep): ExternalToolItem | undefined {
  const toolId = selectedToolId(step);
  return toolRows.value.find((item) => item.id === toolId);
}

function selectedMcpToolName(step: WorkflowStep): string | null {
  return String(step.businessConfig?.preferredMcpToolName || step.businessConfig?.mcpToolName || '').trim() || null;
}

function mcpToolOptions(step: WorkflowStep) {
  const tool = selectedTool(step);
  if (!tool || tool.type !== 'mcp') return [];
  const enabled = new Set(
    Array.isArray(tool.config?.enabledToolNames)
      ? tool.config.enabledToolNames.map((item: unknown) => String(item || '').trim()).filter(Boolean)
      : [],
  );
  return (tool.discoveredTools || [])
    .filter((item) => !enabled.size || enabled.has(String(item.name || '').trim()))
    .map((item) => ({
      label: item.description ? `${item.name} - ${item.description}` : item.name,
      value: item.name,
    }));
}

function handleToolSelect(step: WorkflowStep, toolId: string | null) {
  if (!step.businessConfig) step.businessConfig = {};
  const tool = toolRows.value.find((item) => item.id === toolId);
  step.businessConfig.preferredToolId = tool?.id || '';
  step.businessConfig.preferredToolName = tool?.name || '';
  step.businessConfig.preferredToolType = tool?.type || '';
  step.businessConfig.preferredToolScope = tool ? 'organization' : '';
  step.businessConfig.preferredMcpToolName = '';
}

function handleMcpToolSelect(step: WorkflowStep, mcpToolName: string | null) {
  if (!step.businessConfig) step.businessConfig = {};
  step.businessConfig.preferredMcpToolName = String(mcpToolName || '').trim();
}

function removeStaleSkillHeaderActions() {
  if (!headerActionsElement.value) return;
  const target = window.document.querySelector('#header-actions-teleport-target');
  target
    ?.querySelectorAll('[data-header-actions-owner="skill-config"]')
    .forEach((item) => {
      if (item !== headerActionsElement.value) item.remove();
    });
}

function refreshHeaderTeleportReady(attempt = 0) {
  const target = window.document.querySelector('#header-actions-teleport-target');
  headerTeleportReady.value = Boolean(target);
  if (!headerTeleportReady.value && attempt < 5) {
    window.requestAnimationFrame(() => refreshHeaderTeleportReady(attempt + 1));
  }
}

async function reloadSkillDetail() {
  headerTeleportReady.value = false;
  skill.value = null;
  updateHeaderTitle(null);
  await nextTick();
  await loadDetail();
  await nextTick();
  refreshHeaderTeleportReady();
  await nextTick();
  removeStaleSkillHeaderActions();
}

onMounted(async () => {
  await reloadSkillDetail();
  loadWritingSkillOptions();
  loadToolOptions();
});

onUpdated(removeStaleSkillHeaderActions);

watch(() => route.params.id, async (nextId, previousId) => {
  if (String(nextId || '') === String(previousId || '')) return;
  await reloadSkillDetail();
});

onUnmounted(() => {
  detailRequestSequence.value += 1;
  headerTeleportReady.value = false;
  updateHeaderTitle(null);
});
</script>

<style scoped src="./SkillConfigPageShell.css"></style>
<style scoped src="./SkillConfigPageEditor.css"></style>
<style scoped src="./SkillConfigPageFeedback.css"></style>
