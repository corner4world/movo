import { ref } from 'vue'
import { deleteSkill, enrichSkillDraft, generateSkill, listSkills, updateSkill, uploadSkillSource } from '../api/skills'

type SkillManagementOptions = {
  getUserId: () => string | null
  getMainId: () => string
  onCreated: () => void
  onSelectedRemoved: () => void
}

export function useSkillManagement(options: SkillManagementOptions) {
  const { getUserId, getMainId, onCreated, onSelectedRemoved } = options
  const skills = ref<any[]>([])
  const skillsLoading = ref(false)
  const skillFormOpen = ref(false)
  const skillName = ref('')
  const skillSummary = ref('')
  const skillCategory = ref('Analysis & Reports')
  const skillType = ref('style')
  const skillScenario = ref('')
  const skillChannels = ref<string[]>(['generic'])
  const skillForms = ref<string[]>(['article'])
  const skillAudience = ref<string[]>(['general_public'])
  const skillStyle = ref<string[]>(['professional'])
  const skillRequired = ref<string[]>([])
  const skillForbidden = ref<string[]>([])
  const skillKnowledge = ref<any[]>([])
  const skillTemplates = ref<any[]>([])
  const skillTools = ref<any[]>([])
  const skillCreating = ref(false)
  const skillEnriching = ref(false)
  const selectedSkill = ref<any | null>(null)

  // The skill form and its API operations share one state owner so navigation
  // can keep the same draft and selected skill across view changes.

  async function loadSkills() {
    if (!getUserId()) return
    skillsLoading.value = true
    try {
      skills.value = await listSkills(getUserId(), getMainId())
    } catch {
      skills.value = []
    } finally {
      skillsLoading.value = false
    }
  }

  function closeSkillForm() {
    skillFormOpen.value = false
  }

  function openSkillForm() {
    skillFormOpen.value = true
  }

  async function handleSkillFileUpload(event: Event, kind: 'knowledge' | 'templates' | 'tools') {
    if (!getUserId()) return
    const input = event.target as HTMLInputElement
    if (!input.files || input.files.length === 0) return
    const files = Array.from(input.files)
    for (const file of files) {
      const uploaded = await uploadSkillSource(getUserId(), file)
      if (uploaded?.object_path) {
        if (kind === 'knowledge') skillKnowledge.value.push(uploaded)
        if (kind === 'templates') skillTemplates.value.push(uploaded)
        if (kind === 'tools') skillTools.value.push(uploaded)
      }
    }
    input.value = ''
  }

  async function handleSkillResourceUpload(event: Event, kind: 'knowledge' | 'templates' | 'tools') {
    if (!getUserId() || !selectedSkill.value) return
    const input = event.target as HTMLInputElement
    if (!input.files || input.files.length === 0) return
    const files = Array.from(input.files)
    for (const file of files) {
      const uploaded = await uploadSkillSource(getUserId(), file)
      if (uploaded?.object_path) {
        const updated = { ...selectedSkill.value }
        const resources = { ...(updated.resources || {}) }
        const list = [...(resources[kind] || []), uploaded]
        resources[kind] = list
        updated.resources = resources
        selectedSkill.value = updated
      }
    }
    input.value = ''
  }

  async function enrichDraftFromForm() {
    if (!getUserId() || !skillName.value.trim()) return
    skillEnriching.value = true
    try {
      const inputProfile = {
        skill_type: skillType.value,
        name: skillName.value.trim(),
        summary: skillSummary.value.trim(),
        applicable_scenarios: skillScenario.value.trim(),
        publish_channel: skillChannels.value,
        content_form: skillForms.value,
        target_audience: skillAudience.value,
        preferred_style: skillStyle.value,
        required_elements: skillRequired.value,
        forbidden_elements: skillForbidden.value,
        reference_materials: [
          ...skillKnowledge.value.map((item: any) => item.filename || item.object_path),
          ...skillTemplates.value.map((item: any) => item.filename || item.object_path),
        ],
      }
      const enriched = await enrichSkillDraft({
        user_id: getUserId(),
        name: skillName.value.trim(),
        description: skillSummary.value.trim(),
        skill_type: skillType.value,
        input_profile: inputProfile,
      })
      const contract = enriched?.contract_json || {}
      skillSummary.value = contract.summary || skillSummary.value
      skillScenario.value = contract.applicable_scenarios || skillScenario.value
      skillChannels.value = contract.publish_channel || skillChannels.value
      skillForms.value = contract.content_form || skillForms.value
      skillAudience.value = contract.target_audience || skillAudience.value
      skillStyle.value = contract.preferred_style || skillStyle.value
      skillRequired.value = contract.required_elements || skillRequired.value
      skillForbidden.value = contract.forbidden_elements || skillForbidden.value
    } finally {
      skillEnriching.value = false
    }
  }

  async function createSkill() {
    if (!getUserId()) return
    if (!skillName.value.trim()) return
    skillCreating.value = true
    try {
      const contractJson = {
        skill_type: skillType.value,
        name: skillName.value.trim(),
        summary: skillSummary.value.trim(),
        applicable_scenarios: skillScenario.value.trim(),
        publish_channel: skillChannels.value,
        content_form: skillForms.value,
        target_audience: skillAudience.value,
        preferred_style: skillStyle.value,
        required_elements: skillRequired.value,
        forbidden_elements: skillForbidden.value,
        reference_materials: [
          ...skillKnowledge.value.map((item: any) => item.filename || item.object_path),
          ...skillTemplates.value.map((item: any) => item.filename || item.object_path),
        ],
      }
      const created = await generateSkill({
        user_id: getUserId(),
        name: skillName.value.trim(),
        description: skillSummary.value.trim(),
        summary: skillSummary.value.trim(),
        category: skillCategory.value,
        role: skillType.value,
        skill_type: skillType.value,
        tags: [],
        visibility: 'private',
        formats: ['markdown'],
        sources: [],
        resources: {
          knowledge: skillKnowledge.value,
          templates: skillTemplates.value,
          tools: skillTools.value,
        },
        input_profile: contractJson,
        contract_json: contractJson,
        skill_markdown: '',
        advanced: {},
        is_active: false,
      })
      if (created) {
        handleSkillCreate(created)
        onCreated()
        skillName.value = ''
        skillSummary.value = ''
        skillCategory.value = 'Analysis & Reports'
        skillType.value = 'style'
        skillScenario.value = ''
        skillChannels.value = ['generic']
        skillForms.value = ['article']
        skillAudience.value = ['general_public']
        skillStyle.value = ['professional']
        skillRequired.value = []
        skillForbidden.value = []
        skillKnowledge.value = []
        skillTemplates.value = []
        skillTools.value = []
        skillFormOpen.value = false
      }
    } finally {
      skillCreating.value = false
    }
  }

  function handleSkillCreate(skillOrEvent: any) {
    // A DOM event or an empty value opens the form
    if (!skillOrEvent || skillOrEvent instanceof Event || !skillOrEvent.id) {
      openSkillForm()
      return
    }

    // Add the created skill to the list and select it
    skills.value = [skillOrEvent, ...skills.value]
    selectedSkill.value = skillOrEvent
    // The caller controls navigation after creation.
  }

  async function saveSkillConfig(payload: any) {
    if (!getUserId() || !payload?.id) return
    const updated = await updateSkill(payload.id, {
      user_id: getUserId(),
      name: payload.name,
      description: payload.description,
      category: payload.category,
      skill_type: payload.skill_type,
      is_active: payload.is_active,
      input_profile: payload.input_profile,
      contract_json: payload.contract_json,
      skill_markdown: payload.skill_markdown,
      resources: payload.resources,
      advanced: payload.advanced,
    })
    if (updated) {
      skills.value = skills.value.map((s) => (s.id === updated.id ? updated : s))
      selectedSkill.value = updated
    }
  }

  async function toggleSkillActive(skill: any, isActive: boolean) {
    if (!getUserId() || !skill?.id) return
    const updated = await updateSkill(skill.id, {
      user_id: getUserId(),
      name: skill.name,
      description: skill.description,
      category: skill.category,
      skill_type: skill.skill_type || 'style',
      is_active: isActive,
      input_profile: skill.input_profile || skill.contract_json || {},
      contract_json: skill.contract_json || skill.input_profile || {},
      skill_markdown: skill.skill_markdown || '',
      resources: skill.resources || {},
      advanced: skill.advanced || {},
    })
    if (updated) {
      skills.value = skills.value.map((item) => (item.id === updated.id ? updated : item))
      if (selectedSkill.value?.id === updated.id) {
        selectedSkill.value = updated
      }
    }
  }

  async function removeSkill(skill: any) {
    if (!getUserId() || !skill?.id) return
    await deleteSkill(skill.id, getUserId())
    skills.value = skills.value.filter((s) => s.id !== skill.id)
    if (selectedSkill.value?.id === skill.id) {
      selectedSkill.value = null
      onSelectedRemoved()
    }
  }

  return {
    skills, skillsLoading, skillFormOpen, skillName, skillSummary, skillCategory,
    skillType, skillScenario, skillChannels, skillForms, skillAudience, skillStyle,
    skillRequired, skillForbidden, skillKnowledge, skillTemplates, skillTools,
    skillCreating, skillEnriching, selectedSkill, loadSkills, closeSkillForm,
    openSkillForm, handleSkillFileUpload, handleSkillResourceUpload,
    enrichDraftFromForm, createSkill, handleSkillCreate, saveSkillConfig,
    toggleSkillActive, removeSkill,
  }
}
