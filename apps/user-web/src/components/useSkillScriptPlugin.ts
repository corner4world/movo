import type { ComputedRef, Ref } from 'vue';
import { useMessage } from 'naive-ui';
import { t } from '../composables/i18n';
import { checkScriptPlugin, fixScriptPlugin, generateScriptPlugin, type SkillItem, type ScriptPluginCheckIssue, type ScriptPluginCheckResult, type WorkflowNodeDraft, type WorkflowNodeType } from '../api/skills';

export interface WorkflowStep {
  id: string;
  type: WorkflowNodeType;
  title: string;
  text: string;
  businessConfig: Record<string, any>;
  boundWritingSkillId?: string;
  outputAlias?: string;
}

interface ScriptPluginContext {
  skill: Ref<SkillItem | null>;
  scriptCheckResults: Ref<Record<string, ScriptPluginCheckResult & { signature?: string }>>;
  activeScriptStepId: Ref<string>;
  activeStepId: Ref<string>;
  scriptAdvancedDrawerVisible: Ref<boolean>;
  generatingScriptStepId: Ref<string>;
  checkingScriptStepId: Ref<string>;
  fixingScriptStepId: Ref<string>;
  workflowSteps: Ref<WorkflowStep[]>;
  activeScriptStep: ComputedRef<WorkflowStep | null>;
  scriptDrawerSaving: Ref<boolean>;
  message: ReturnType<typeof useMessage>;
  serializeWorkflowNodes: () => WorkflowNodeDraft[];
}

export function useSkillScriptPlugin(context: ScriptPluginContext) {
  const { skill, scriptCheckResults, activeScriptStepId, activeStepId, scriptAdvancedDrawerVisible, generatingScriptStepId, checkingScriptStepId, fixingScriptStepId, workflowSteps, activeScriptStep, scriptDrawerSaving, message, serializeWorkflowNodes } = context;

function scriptPluginInstructionSignature(step: WorkflowStep): string {
  return String(step.businessConfig?.processingInstruction || '').trim();
}

function scriptPluginSignature(step: WorkflowStep): string {
  const payload = [
    step.id,
    scriptPluginInstructionSignature(step),
    String(step.businessConfig?.pluginCode || ''),
  ].join('\u0000');
  let hashA = 2166136261;
  let hashB = 5381;
  for (let index = 0; index < payload.length; index += 1) {
    const code = payload.charCodeAt(index);
    hashA = Math.imul(hashA ^ code, 16777619);
    hashB = Math.imul(hashB, 33) ^ code;
  }
  return `v1:${payload.length}:${(hashA >>> 0).toString(16)}:${(hashB >>> 0).toString(16)}`;
}

function isScriptPluginGenerated(step: WorkflowStep): boolean {
  const instruction = scriptPluginInstructionSignature(step);
  return Boolean(
    instruction
    && String(step.businessConfig?.pluginCode || '').trim()
    && String(step.businessConfig?.generatedInstructionSignature || '') === instruction,
  );
}

function isScriptPluginCheckPassed(step: WorkflowStep): boolean {
  const result = scriptCheckResults.value[step.id] as (ScriptPluginCheckResult & { signature?: string }) | undefined;
  const signature = scriptPluginSignature(step);
  return Boolean(
    (result?.pass && result.signature === signature)
    || String(step.businessConfig?.pluginCheckSignature || '') === signature,
  );
}

function persistScriptPluginCheck(step: WorkflowStep, result?: ScriptPluginCheckResult): void {
  if (result?.pass) {
    step.businessConfig.pluginCheckSignature = scriptPluginSignature(step);
    return;
  }
  delete step.businessConfig.pluginCheckSignature;
}

function scriptCheckIssueItems(step: WorkflowStep): ScriptPluginCheckIssue[] {
  const result = scriptCheckResults.value[step.id];
  if (!result) return [];
  const issues = [
    ...((result.errors || []) as ScriptPluginCheckIssue[]),
    ...((result.warnings || []) as ScriptPluginCheckIssue[]),
  ];
  if (issues.length || result.pass) return issues;
  return [{
    level: 'error',
    code: 'CHECK_FAILED',
    message: result.message || t('legacy.validation_failed_without_details_use_ai_fix_code_or'),
    line: null,
  }];
}

function invalidateScriptPluginCheck(stepId: string) {
  if (scriptCheckResults.value[stepId]) {
    const next = { ...scriptCheckResults.value };
    delete next[stepId];
    scriptCheckResults.value = next;
  }
}

function openScriptAdvancedDrawer(step: WorkflowStep) {
  activeScriptStepId.value = step.id;
  activeStepId.value = step.id;
  scriptAdvancedDrawerVisible.value = true;
}

function scriptPluginContextNodes(): WorkflowNodeDraft[] {
  return serializeWorkflowNodes().map((node) => {
    return {
      id: node.id,
      type: node.type,
      title: node.title,
      description: '',
      businessConfig: {},
      outputAlias: node.outputAlias || node.businessConfig?.outputAlias || '',
      boundWritingSkillId: '',
    };
  });
}

async function generateScriptPluginStep(step: WorkflowStep, options: { confirmOverwrite?: boolean; silent?: boolean } = {}): Promise<boolean> {
  if (!skill.value) return false;
  const instruction = String(step.businessConfig?.processingInstruction || '').trim();
  if (!instruction) {
    if (!options.silent) message.warning(t('legacy.enter_processing_instructions_first'));
    return false;
  }
  const existingCode = String(step.businessConfig?.pluginCode || '').trim();
  if (existingCode && options.confirmOverwrite && !window.confirm(t('legacy.regenerating_will_overwrite_the_current_advanced_code_continue'))) {
    return false;
  }
  generatingScriptStepId.value = step.id;
  try {
    const result = await generateScriptPlugin({
      processingInstruction: instruction,
      nodeTitle: step.title,
      nodeDescription: '',
      skillName: '',
      skillDescription: '',
      scenario: '',
      selectedInputSource: String(step.businessConfig?.selectedInputSource || 'all'),
      selectedInputTypes: Array.isArray(step.businessConfig?.selectedInputTypes) ? step.businessConfig.selectedInputTypes : [],
      workflowNodes: scriptPluginContextNodes(),
    });
    if (!result.code?.trim()) {
      message.error(t('legacy.ai_did_not_return_usable_code'));
      return false;
    }
    step.businessConfig.pluginCode = result.code;
    step.businessConfig.generatedInstructionSignature = scriptPluginInstructionSignature(step);
    const check = result.check as (ScriptPluginCheckResult | undefined);
    if (check) {
      scriptCheckResults.value = {
        ...scriptCheckResults.value,
        [step.id]: { ...check, signature: scriptPluginSignature(step) },
      };
      persistScriptPluginCheck(step, check);
    } else {
      invalidateScriptPluginCheck(step.id);
      persistScriptPluginCheck(step);
    }
    const firstNote = (result.notes || [])[0];
    if (check?.pass) {
      if (!options.silent) message.success(firstNote || t('legacy.code_generated_and_validated'));
      return true;
    }
    if (!options.silent) message.warning(check?.errors?.[0]?.message || firstNote || t('legacy.code_generated_fix_validation_issues_before_saving'));
    return true;
  } catch (error: any) {
    if (!options.silent) message.error(error?.response?.data?.detail || error?.message || t('legacy.ai_code_generation_failed'));
    return false;
  } finally {
    generatingScriptStepId.value = '';
  }
}

async function checkScriptPluginStep(step: WorkflowStep): Promise<boolean> {
  const code = String(step.businessConfig?.pluginCode || '').trim();
  if (!code) {
    message.warning(t('legacy.enter_script_code_first'));
    return false;
  }
  checkingScriptStepId.value = step.id;
  try {
    const result = await checkScriptPlugin({
      code,
      nodeTitle: step.title,
      nodeDescription: String(step.businessConfig?.processingInstruction || ''),
    });
    scriptCheckResults.value = {
      ...scriptCheckResults.value,
      [step.id]: { ...result, signature: scriptPluginSignature(step) },
    };
    persistScriptPluginCheck(step, result);
    if (result.pass) {
      step.businessConfig.generatedInstructionSignature = scriptPluginInstructionSignature(step);
      message.success(result.llm?.summary || t('legacy.script_validation_passed'));
      return true;
    }
    return false;
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.script_validation_failed'));
    return false;
  } finally {
    checkingScriptStepId.value = '';
  }
}

async function fixScriptPluginStep(step: WorkflowStep): Promise<boolean> {
  const code = String(step.businessConfig?.pluginCode || '').trim();
  if (!code) {
    message.warning(t('legacy.enter_script_code_first'));
    return false;
  }
  fixingScriptStepId.value = step.id;
  try {
    const current = scriptCheckResults.value[step.id];
    const issues = [
      ...((current?.errors || []) as any[]),
      ...((current?.warnings || []) as any[]),
    ];
    const result = await fixScriptPlugin({
      code,
      nodeTitle: step.title,
      nodeDescription: String(step.businessConfig?.processingInstruction || ''),
      issues,
    });
    if (!result.code?.trim()) {
      message.error(t('legacy.ai_did_not_return_usable_code'));
      return false;
    }
    step.businessConfig.pluginCode = result.code;
    const check = result.check as (ScriptPluginCheckResult | undefined);
    if (check) {
      scriptCheckResults.value = {
        ...scriptCheckResults.value,
        [step.id]: { ...check, signature: scriptPluginSignature(step) },
      };
      persistScriptPluginCheck(step, check);
    } else {
      invalidateScriptPluginCheck(step.id);
      persistScriptPluginCheck(step);
    }
    if (check?.pass) {
      step.businessConfig.generatedInstructionSignature = scriptPluginInstructionSignature(step);
    }
    message.success((result.notes || [])[0] || t('legacy.ai_fix_complete_review_the_code_again'));
    return Boolean(check?.pass);
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.ai_code_fix_failed'));
    return false;
  } finally {
    fixingScriptStepId.value = '';
  }
}

async function ensureScriptPluginsChecked(): Promise<boolean> {
  const scriptSteps = workflowSteps.value.filter((item) => item.type === 'script_plugin');
  for (const step of scriptSteps) {
    if (!String(step.businessConfig?.processingInstruction || '').trim()) {
      activeStepId.value = step.id;
      message.warning(t('legacy.enter_processing_instructions_for_the_data_processing_step_first'));
      return false;
    }
    if (!String(step.businessConfig?.pluginCode || '').trim()) {
      activeStepId.value = step.id;
      message.warning(t('legacy.write_or_generate_script_code_first'));
      return false;
    }
    if (!isScriptPluginCheckPassed(step)) {
      activeStepId.value = step.id;
      message.warning(t('legacy.code_has_changed_or_has_not_passed_validation_validate'));
      return false;
    }
  }
  return true;
}

async function ensureScriptPluginStepReady(step: WorkflowStep): Promise<boolean> {
  if (!String(step.businessConfig?.processingInstruction || '').trim()) {
    message.warning(t('legacy.enter_processing_instructions_first'));
    return false;
  }
  if (!String(step.businessConfig?.pluginCode || '').trim()) {
    message.warning(t('legacy.write_or_generate_script_code_first'));
    return false;
  }
  if (!isScriptPluginCheckPassed(step)) {
    message.warning(t('legacy.code_has_changed_or_has_not_passed_validation_validate'));
    return false;
  }
  return true;
}

async function saveScriptAdvancedDrawer() {
  const step = activeScriptStep.value;
  if (!step) return;
  scriptDrawerSaving.value = true;
  try {
    const ready = await ensureScriptPluginStepReady(step);
    if (ready) {
      scriptAdvancedDrawerVisible.value = false;
    }
  } finally {
    scriptDrawerSaving.value = false;
  }
}

  return { scriptPluginInstructionSignature, scriptPluginSignature, isScriptPluginGenerated, isScriptPluginCheckPassed, persistScriptPluginCheck, scriptCheckIssueItems, invalidateScriptPluginCheck, openScriptAdvancedDrawer, scriptPluginContextNodes, generateScriptPluginStep, checkScriptPluginStep, fixScriptPluginStep, ensureScriptPluginsChecked, ensureScriptPluginStepReady, saveScriptAdvancedDrawer };
}
