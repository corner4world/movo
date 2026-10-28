import type { ComputedRef, Ref } from 'vue';
import { useMessage } from 'naive-ui';
import { t } from '@/composables/i18n';
import { enrichWritingStyleDraft, updateSkill, type SkillItem, type WritingStyleDraft } from '@/api/skills';
import { createSectionNode, flattenSectionTitles, hydrateSectionStructure, normalizeStringArray, parseMultilineItems, serializeSectionStructure, type SectionNode } from './workflowSectionStructure';

interface WritingStyleContext {
  skill: Ref<SkillItem | null>;
  saving: Ref<boolean>;
  styleEnriching: Ref<boolean>;
  publishChannelInput: Ref<string[]>;
  contentFormInput: Ref<string[]>;
  targetAudienceInput: Ref<string[]>;
  preferredStyleInput: Ref<string[]>;
  targetLengthMin: Ref<number | null>;
  targetLengthMax: Ref<number | null>;
  targetLengthUnit: Ref<string>;
  sectionStructure: Ref<SectionNode[]>;
  requiredElementsItems: ComputedRef<string[]>;
  forbiddenElementsItems: ComputedRef<string[]>;
  requiredElementsText: Ref<string>;
  forbiddenElementsText: Ref<string>;
  styleInputProfile: Ref<Record<string, any>>;
  styleContractJson: Ref<Record<string, any>>;
  styleSkillMarkdown: Ref<string>;
  message: ReturnType<typeof useMessage>;
}

export function useSkillWritingStyle(context: WritingStyleContext) {
  const { skill, saving, styleEnriching, publishChannelInput, contentFormInput, targetAudienceInput, preferredStyleInput, targetLengthMin, targetLengthMax, targetLengthUnit, sectionStructure, requiredElementsItems, forbiddenElementsItems, requiredElementsText, forbiddenElementsText, styleInputProfile, styleContractJson, styleSkillMarkdown, message } = context;

function buildWritingStyleContractJson(): Record<string, any> {
  const min = Number(targetLengthMin.value || 0);
  const max = Number(targetLengthMax.value || 0);
  const serializedSections = serializeSectionStructure(sectionStructure.value);
  const sectionTitles = flattenSectionTitles(sectionStructure.value);
  const targetLength = {
    min: min > 0 ? min : undefined,
    max: max > 0 ? max : undefined,
    unit: targetLengthUnit.value || 'chinese_chars',
  };
  return {
    skill_type: 'style',
    name: skill.value?.name || '',
    summary: skill.value?.description || '',
    applicable_scenarios: skill.value?.scenario || '',
    publish_channel: [...publishChannelInput.value],
    content_form: [...contentFormInput.value],
    target_audience: [...targetAudienceInput.value],
    preferred_style: [...preferredStyleInput.value],
    target_length: targetLength,
    targetLength,
    section_structure: serializedSections,
    sectionStructure: serializedSections,
    required_sections: sectionTitles,
    required_elements: [...requiredElementsItems.value],
    forbidden_elements: [...forbiddenElementsItems.value],
  };
}

function buildWritingStyleDraft(): WritingStyleDraft {
  const serializedSections = serializeSectionStructure(sectionStructure.value);
  return {
    publishChannel: [...publishChannelInput.value],
    contentForm: [...contentFormInput.value],
    targetAudience: [...targetAudienceInput.value],
    preferredStyle: [...preferredStyleInput.value],
    targetLength: {
      min: Number(targetLengthMin.value || 0) || undefined,
      max: Number(targetLengthMax.value || 0) || undefined,
      unit: targetLengthUnit.value || 'chinese_chars',
    },
    sectionStructure: serializedSections,
    requiredSections: flattenSectionTitles(sectionStructure.value),
    requiredElements: [...requiredElementsItems.value],
    forbiddenElements: [...forbiddenElementsItems.value],
    inputProfile: styleInputProfile.value,
    contractJson: styleContractJson.value,
    skillMarkdown: styleSkillMarkdown.value,
  };
}

function applyWritingStyleContract(contract: Record<string, any>) {
  publishChannelInput.value = normalizeStringArray(contract.publish_channel);
  contentFormInput.value = normalizeStringArray(contract.content_form);
  targetAudienceInput.value = normalizeStringArray(contract.target_audience);
  preferredStyleInput.value = normalizeStringArray(contract.preferred_style);
  const targetLength = contract.target_length && typeof contract.target_length === 'object'
    ? contract.target_length
    : contract.targetLength && typeof contract.targetLength === 'object'
      ? contract.targetLength
      : {};
  targetLengthMin.value = Number(targetLength.min || targetLength.min_words || 0) || null;
  targetLengthMax.value = Number(targetLength.max || targetLength.max_words || 0) || null;
  targetLengthUnit.value = String(targetLength.unit || 'chinese_chars');
  sectionStructure.value = hydrateSectionStructure(
    contract.section_structure || contract.sectionStructure,
    contract.required_sections || contract.requiredSections,
  );
  requiredElementsText.value = parseMultilineItems(contract.required_elements).join('\n');
  forbiddenElementsText.value = parseMultilineItems(contract.forbidden_elements).join('\n');
  styleContractJson.value = { ...contract };
}

function hydrateWritingStyle(source: SkillItem) {
  const config = source.config && typeof source.config === 'object' ? source.config : {};
  const contract = config.contractJson && typeof config.contractJson === 'object'
    ? config.contractJson
    : config.contract_json && typeof config.contract_json === 'object'
      ? config.contract_json
      : buildWritingStyleContractJson();
  applyWritingStyleContract(contract);
  styleInputProfile.value = config.inputProfile && typeof config.inputProfile === 'object'
    ? { ...config.inputProfile }
    : config.input_profile && typeof config.input_profile === 'object'
      ? { ...config.input_profile }
      : { ...contract };
  styleSkillMarkdown.value = String(config.skillMarkdown || config.skill_markdown || '').trim();
}

async function enrichWritingStyle() {
  if (!skill.value) return;
  styleEnriching.value = true;
  try {
    const result = await enrichWritingStyleDraft({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      draft: buildWritingStyleDraft(),
    });
    styleInputProfile.value = result.inputProfile || {};
    styleSkillMarkdown.value = String(result.skillMarkdown || '').trim();
    applyWritingStyleContract(result.contractJson || buildWritingStyleContractJson());
    message.success(t('legacy.writing_guidelines_completed'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_complete_writing_guidelines'));
  } finally {
    styleEnriching.value = false;
  }
}

async function saveWritingStyle(): Promise<boolean> {
  if (!skill.value) return false;
  saving.value = true;
  try {
    const contractJson = buildWritingStyleContractJson();
    const inputProfile = {
      ...(styleInputProfile.value || {}),
      ...contractJson,
    };
    const updated = await updateSkill(skill.value.id, {
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      type: skill.value.type,
      enabled: skill.value.enabled !== false,
      config: {
        ...(skill.value.config || {}),
        inputProfile,
        contractJson,
        skillMarkdown: styleSkillMarkdown.value,
      },
    });
    skill.value = updated;
    hydrateWritingStyle(updated);
    message.success(t('legacy.writing_guidelines_saved'));
    return true;
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_save_skill'));
    return false;
  } finally {
    saving.value = false;
  }
}

function addSection(parent?: SectionNode) {
  const next = createSectionNode();
  if (parent) {
    parent.children.push(next);
    return;
  }
  sectionStructure.value.push(next);
}

function moveSection(list: SectionNode[], index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= list.length) return;
  const [item] = list.splice(index, 1);
  list.splice(nextIndex, 0, item);
}

function removeSection(list: SectionNode[], index: number) {
  list.splice(index, 1);
}

  return { addSection, moveSection, removeSection, buildWritingStyleContractJson, buildWritingStyleDraft, applyWritingStyleContract, hydrateWritingStyle, enrichWritingStyle, saveWritingStyle };
}
