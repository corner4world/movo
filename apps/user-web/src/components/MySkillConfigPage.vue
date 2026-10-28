<template src="./MySkillConfigPageTemplate.html"></template>

<script setup lang="ts">
import { useSkillWritingStyle } from './useSkillWritingStyle';
import { useSkillScriptPlugin, type WorkflowStep } from './useSkillScriptPlugin';

import { createSectionNode, normalizeStringArray, parseMultilineItems, hydrateSectionStructure, serializeSectionStructure, flattenSectionTitles, flattenSectionPreview, type SectionNode, type SectionPreviewItem } from './workflowSectionStructure';

import { workflowNodeTypes } from './workflowNodeCatalog';
import { workflowTextInferenceRules } from '../locales/workflowTextInferenceRules';
import { publishChannelSuggestions, contentFormSuggestions, targetAudienceSuggestions, preferredStyleSuggestions, type LocalizedSelectOption } from '../locales/workflowSelectOptions';
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue';
import { t, translateSourceText, useLocale } from '../composables/i18n';
import { localizeWorkflowDefaults } from './workflowDefaultLocale';
import { workflowResponseText } from './workflowResponseText';
import { formatAppDateTime } from '../composables/appTimezone';
import {
  NButton,
  NDrawer,
  NDrawerContent,
  NEmpty,
  NInput,
  NInputNumber,
  NPopover,
  NSelect,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui';
import {
  checkWorkflowNodes,
  fetchSkills,
  generateWorkflowNodes,
  updateSkill,
  type SkillItem,
  type SkillType,
  type ScriptPluginCheckResult,
  type WorkflowNodeDraft,
  type WorkflowNodeType,
} from '../api/skills';
import { skillSourceLabel } from './skills/skillSourceLabel';
import { fetchTools, type ExternalToolItem } from '../api/tools';
import BrowserAutomationNodeConfig from './workflow/BrowserAutomationNodeConfig.vue';
import KnowledgeDocumentSourceConfig from './workflow/KnowledgeDocumentSourceConfig.vue';
import ReviewCheckNodeConfig from './workflow/ReviewCheckNodeConfig.vue';
import { bindReviewSources } from './workflow/reviewSourceBinding';
import { looksLikeBrowserAutomation } from '../workflow/browserAutomationNode';
import SkillPublishDialog from './skills/SkillPublishDialog.vue';

const PythonCodeEditor = defineAsyncComponent(() => import('./PythonCodeEditor.vue'));

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

const props = defineProps<{
  skill: SkillItem | null
  userId: string | null
  mainId: string
}>();

const emit = defineEmits<{
  back: []
  saved: [skill: SkillItem]
}>();

const message = useMessage();
const { locale } = useLocale();

const loading = ref(false);
const saving = ref(false);
const publishVisible = ref(false);
const testing = ref(false);
const optimizing = ref(false);
const generatingSteps = ref(false);
const supplementingStep = ref(false);
const styleEnriching = ref(false);
const skill = ref<SkillItem | null>(props.skill ? { ...props.skill } : null);
const packageAuthored = computed(() => (
  skill.value?.lifecycle?.authoringMode === 'package' || Boolean(skill.value?.package)
));
const packageSourceLabel = computed(() => skill.value ? skillSourceLabel(skill.value) : '');
const workflowSteps = ref<WorkflowStep[]>([]);
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
const styleMarkdownContractSnapshot = ref('');
const writingSkillOptions = ref<Array<{ label: string; value: string }>>([]);
const activeScriptStep = computed(() => workflowSteps.value.find((item) => item.id === activeScriptStepId.value && item.type === 'script_plugin') || null);
const toolRows = ref<ExternalToolItem[]>([]);
const toolOptionsLoading = ref(false);
const toolOptions = computed(() => toolRows.value
  .filter((item) => item.status !== 'disabled')
  .map((item) => ({
    label: `${item.name} (${item.type.toUpperCase()})`,
    value: item.id,
  })));



const localizedOptionLabel = (item: LocalizedSelectOption) => (locale.value === 'zh' ? item.zh : item.en);
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
    : t('workflow.not_configured')
);
const toSelectOptions = (items: LocalizedSelectOption[]) => computed(() => (
  items.map((item) => ({ label: localizedOptionLabel(item), value: item.value }))
));
const publishChannelOptions = toSelectOptions(publishChannelSuggestions);
const contentFormOptions = toSelectOptions(contentFormSuggestions);
const targetAudienceOptions = toSelectOptions(targetAudienceSuggestions);
const preferredStyleOptions = toSelectOptions(preferredStyleSuggestions);

const workflowTypeMap = computed(() => Object.fromEntries(workflowNodeTypes.map((item) => [item.type, item])));
function reviewSourceOptions(index: number): Array<{ id: string; alias: string }> {
  return workflowSteps.value.slice(0, index).map(item => ({
    id: item.id, alias: String(item.outputAlias || item.businessConfig?.outputAlias || '').trim(),
  })).filter(item => item.alias);
}
const normalizedStepText = computed(() => workflowSteps.value.map((item) => buildNodeText(item).trim()).filter(Boolean).join('\n'));
const workflowPreviewNodes = computed(() => workflowSteps.value.map((item) => ({
  id: item.id,
  label: item.outputAlias || item.businessConfig?.outputAlias || item.title || workflowTypeLabel(item.type),
  type: item.type,
  color: workflowTypeMeta(item.type).color,
  icon: workflowTypeMeta(item.type).icon,
})));
const stepListLoadingText = computed(() => {
  if (optimizing.value) return t('workflow.optimizing');
  if (supplementingStep.value) return t('workflow.supplementing');
  return t('workflow.generating_steps');
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
  if (min > 0 && max > 0) return t('workflow.word_count_range_value', { min, max });
  if (min > 0) return t('workflow.word_count_min_value', { min });
  if (max > 0) return t('workflow.word_count_max_value', { max });
  return t('workflow.not_configured');
});

async function persistSkill(payload: {
  name: string
  description: string
  scenario: string
  type: SkillType
  config: Record<string, any>
  enabled: boolean
}): Promise<SkillItem | null> {
  if (!skill.value || !props.userId) return null;
  const updated = await updateSkill(skill.value.id, props.userId, props.mainId, payload);
  skill.value = updated;
  emit('saved', updated);
  return updated;
}

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
  return type === 'workflow' ? t('skills.type.workflow') : t('skills.type.style');
}

function createId(): string {
  return `step_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function workflowTypeMeta(type: WorkflowNodeType | string) {
  return workflowTypeMap.value[String(type)] || workflowTypeMap.value.generate_content || workflowNodeTypes[0];
}

function workflowTypeLabel(type: WorkflowNodeType | string): string {
  return t('workflow.preset.' + workflowTypeMeta(type).type + '.label');
}

function serializeWorkflowNodeCatalog() {
  return workflowNodeTypes.map((item) => ({
    type: item.type,
    name: t('workflow.preset.' + item.type + '.label'),
    usageDescription: translateSourceText(item.usageDescription || ''),
    usageExample: translateSourceText(item.usageExample || ''),
  }));
}

function createWorkflowNode(type: WorkflowNodeType = 'extract_info', seed: Partial<WorkflowStep> = {}): WorkflowStep {
  const meta = workflowTypeMeta(type);
  const businessConfig = {
    ...localizeWorkflowDefaults(meta.defaultConfig || {}),
    ...(seed.businessConfig || {}),
  };
  if (type === 'review_check' && !seed.businessConfig?.outputAlias) {
    businessConfig.outputAlias = t('legacy.review_findings');
  }
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
  const type = workflowNodeTypes.some((item) => item.type === value.type)
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
  if (looksLikeBrowserAutomation(normalized)) return 'browser_automation';
  const rules: ReadonlyArray<{ type: WorkflowNodeType; keywords: readonly string[] }> = workflowTextInferenceRules;
  return rules.find((rule) => rule.keywords.some((keyword) => normalized.includes(keyword)))?.type || 'generate_content';
}

function beginRestoreWorkflow() {
  restoringWorkflow.value = true;
  window.setTimeout(() => {
    restoringWorkflow.value = false;
  }, 0);
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
      label: String(logic.label || t('workflow.to_be_clarified')),
      level: logic.level === 'success' ? 'success' : 'warning',
      summary: String(logic.summary || t('workflow.check_prompt_hint')),
    },
    coverage: Array.isArray(result.coverage) ? result.coverage : [],
    readiness: Array.isArray(result.readiness) ? result.readiness : [],
    suggestions: Array.isArray(result.suggestions) ? result.suggestions : [],
    conclusion: String(result.conclusion || t('workflow.not_checked')),
  };
}

const { addSection, moveSection, removeSection, buildWritingStyleContractJson, buildWritingStyleDraft, applyWritingStyleContract, hydrateWritingStyle, enrichWritingStyle, saveWritingStyle } = useSkillWritingStyle({ skill, saving, styleEnriching, publishChannelInput, contentFormInput, targetAudienceInput, preferredStyleInput, targetLengthMin, targetLengthMax, targetLengthUnit, sectionStructure, requiredElementsItems, forbiddenElementsItems, requiredElementsText, forbiddenElementsText, styleInputProfile, styleContractJson, styleSkillMarkdown, message, props, styleMarkdownContractSnapshot, persistSkill });

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
    message.warning(t('workflow.at_least_one_step'));
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
  const base = next.outputAlias || next.title || t('workflow.outputDefault');
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
    const updated = await persistSkill({
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
    if (!updated) return;
  } catch (error: any) {
    message.warning(error?.response?.data?.detail || t('workflow.check_save_failed'));
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
    workflowSteps.value = generated;
    activeStepId.value = workflowSteps.value[0]?.id || '';
    testResult.value = null;
    stepGenerationError.value = generated.length ? '' : workflowResponseText(result.message, 'workflow.step_generated_empty');
    if (generated.length) {
      message.success(t('workflow.step_generated'));
    } else {
      message.warning(workflowResponseText(result.message, 'workflow.step_generated_empty_hint'));
    }
  } catch (error: any) {
    workflowSteps.value = [];
    activeStepId.value = workflowSteps.value[0]?.id || '';
    testResult.value = null;
    stepGenerationError.value = workflowResponseText(error?.response?.data?.detail || error?.message, 'workflow.step_generated_failed');
    message.error(stepGenerationError.value);
  } finally {
    generatingSteps.value = false;
  }
}

async function optimizeSteps() {
  if (!skill.value) return;
  const existingNodes = serializeWorkflowNodes();
  if (!existingNodes.length) {
    message.warning(t('workflow.optimize_warn_empty'));
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
      stepGenerationError.value = workflowResponseText(result.message, 'workflow.optimize_warn_no_result');
      message.warning(stepGenerationError.value);
      return;
    }
    workflowSteps.value = optimized;
    activeStepId.value = workflowSteps.value[0]?.id || '';
    testResult.value = null;
    message.success(t('workflow.optimize_success'));
  } catch (error: any) {
    stepGenerationError.value = workflowResponseText(error?.response?.data?.detail || error?.message, 'workflow.optimize_failed');
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
      stepGenerationError.value = workflowResponseText(result.message, 'workflow.supplement_warn_no_result');
      message.warning(stepGenerationError.value);
      return;
    }
    const nextStep: WorkflowStep = {
      id: createId(),
      type: supplemented[0]?.type || 'generate_content',
      title: supplemented[0]?.title || t('workflow.supplement_node_title'),
      text: supplemented[0]?.text || supplement,
      businessConfig: supplemented[0]?.businessConfig || {},
      boundWritingSkillId: supplemented[0]?.boundWritingSkillId || '',
      outputAlias: supplemented[0]?.outputAlias || '',
    };
    workflowSteps.value = [...workflowSteps.value, nextStep];
    activeStepId.value = nextStep.id;
    newStepText.value = '';
    testResult.value = null;
    message.success(t('workflow.supplement_added'));
  } catch (error: any) {
    stepGenerationError.value = workflowResponseText(error?.response?.data?.detail || error?.message, 'workflow.supplement_failed');
    message.error(stepGenerationError.value);
  } finally {
    supplementingStep.value = false;
  }
}

async function runWorkflowTest() {
  if (!skill.value) return;
  const steps = workflowSteps.value.map((item) => buildNodeText(item).trim()).filter(Boolean);
  if (!steps.length) {
    message.warning(t('workflow.test_warn_empty'));
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
    const checkedAt = formatAppDateTime(new Date().toISOString(), '');
    const nextResult: WorkflowTestResult = {
      testedAt: checkedAt,
      pass: Boolean(result.pass),
      logic: {
        label: result.logic?.label || t('workflow.needsClarification'),
        level: result.logic?.level === 'success' ? 'success' : 'warning',
        summary: result.logic?.summary || t('workflow.test_logic_empty'),
      },
      coverage: Array.isArray(result.coverage) ? result.coverage : [],
      readiness: Array.isArray(result.readiness) ? result.readiness : [],
      suggestions: Array.isArray(result.suggestions) && result.suggestions.length
        ? result.suggestions
        : [t('workflow.test_suggest_empty')],
      conclusion: result.conclusion || t('workflow.test_conclusion_empty'),
    };
    testResult.value = nextResult;
    await persistWorkflowCheck(nextResult);
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('workflow.test_failed'));
  } finally {
    testing.value = false;
  }
}

const { scriptPluginInstructionSignature, scriptPluginSignature, isScriptPluginGenerated, isScriptPluginCheckPassed, persistScriptPluginCheck, scriptCheckIssueItems, invalidateScriptPluginCheck, openScriptAdvancedDrawer, scriptPluginContextNodes, generateScriptPluginStep, checkScriptPluginStep, fixScriptPluginStep, ensureScriptPluginsChecked, ensureScriptPluginStepReady, saveScriptAdvancedDrawer } = useSkillScriptPlugin({ skill, scriptCheckResults, activeScriptStepId, activeStepId, scriptAdvancedDrawerVisible, generatingScriptStepId, checkingScriptStepId, fixingScriptStepId, workflowSteps, activeScriptStep, scriptDrawerSaving, message, serializeWorkflowNodes });

async function saveWorkflow(): Promise<boolean> {
  if (!skill.value) return false;
  const workflowNodes = serializeWorkflowNodes();
  if (!workflowNodes.length) {
    message.warning(t('workflow.at_least_one_step'));
    return false;
  }
  const missingKnowledge = workflowNodes.find(node => node.type === 'read_material'
    && node.businessConfig?.sourceType === 'knowledge_document'
    && !String(node.businessConfig?.knowledgeSourceId || '').trim());
  if (missingKnowledge) {
    activeStepId.value = String(missingKnowledge.id || '');
    message.warning(t('legacy.select_a_knowledge_document_to_read_first'));
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
    const updated = await persistSkill({
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
    if (!updated) return false;
    hydrateWorkflow(updated);
    message.success(t('workflow.save_success'));
    return true;
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('workflow.save_failed'));
    return false;
  } finally {
    saving.value = false;
  }
}

async function prepareWorkflowPublish() { if (await saveWorkflow()) publishVisible.value = true; }
async function prepareStylePublish() { if (await saveWritingStyle()) publishVisible.value = true; }
function handlePublished(updated: SkillItem) { skill.value = updated; emit('saved', updated); }

function goBack() {
  emit('back');
}

function hydrateDetail(detail: SkillItem | null) {
  skill.value = detail ? { ...detail } : null;
  if (!detail) return;
  if (detail.type === 'workflow') {
    hydrateWorkflow(detail);
  } else {
    hydrateWritingStyle(detail);
  }
}

async function loadWritingSkillOptions() {
  if (!props.userId) {
    writingSkillOptions.value = [];
    return;
  }
  try {
    const rows = await fetchSkills(props.userId, props.mainId);
    writingSkillOptions.value = rows
      .filter((item) => item.type === 'writing_style' && item.enabled !== false)
      .map((item) => ({ label: item.name, value: item.id }));
  } catch {
    writingSkillOptions.value = [];
  }
}

async function loadToolOptions() {
  if (!props.userId) {
    toolRows.value = [];
    return;
  }
  toolOptionsLoading.value = true;
  try {
    toolRows.value = await fetchTools(props.userId, props.mainId);
  } catch {
    toolRows.value = [];
  } finally {
    toolOptionsLoading.value = false;
  }
}

function handleToolSelect(step: WorkflowStep, toolId: string | null) {
  if (!step.businessConfig) step.businessConfig = {};
  const selected = toolRows.value.find((item) => item.id === toolId);
  step.businessConfig.toolId = toolId || '';
  step.businessConfig.toolName = selected?.name || '';
  step.businessConfig.toolType = selected?.type || '';
  step.businessConfig.toolScope = selected ? 'user' : '';
  step.businessConfig.provider = selected?.type === 'mcp' ? 'mcp' : selected?.type === 'http' ? 'http' : '';
}

onMounted(() => {
  hydrateDetail(props.skill);
  loadWritingSkillOptions();
  loadToolOptions();
});

watch(() => props.skill, (next) => {
  hydrateDetail(next);
});

watch(() => [props.userId, props.mainId], () => {
  loadWritingSkillOptions();
  loadToolOptions();
});
</script>

<style scoped src="./MySkillConfigPageShell.css"></style>
<style scoped src="./MySkillConfigPageEditor.css"></style>
<style scoped src="./MySkillConfigPageFeedback.css"></style>
