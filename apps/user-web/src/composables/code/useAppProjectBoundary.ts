import type { Ref } from 'vue'
import type { UserProfile } from '../../api/auth'
import type { DshWorkspace } from '../../platform/types'
import { boundProjectWorktree } from './projectAuthorization'
import type { useDshCodeRuntime } from './useDshCodeRuntime'
import type { useUserBoundProjects } from './userBoundProjects'

type Options = {
  projects: ReturnType<typeof useUserBoundProjects>
  codeRuntime: ReturnType<typeof useDshCodeRuntime>
  canUseCode: Readonly<Ref<boolean>>
}

/** Keeps account and permission changes from retaining another user's project state. */
export function useAppProjectBoundary({ projects, codeRuntime, canUseCode }: Options) {
  function selectBoundProject(key: string, workspace: DshWorkspace): void {
    if (workspace.status !== 'ok') return
    codeRuntime.setDraftProject(
      key, workspace, boundProjectWorktree(projects.bindings.value, workspace.workspace_id),
    )
  }

  function clearUserBoundProjectState(resetCodeRuntime = false): void {
    projects.clear()
    if (resetCodeRuntime) codeRuntime.reset()
  }

  function prepareProjectBoundary(nextProfile: UserProfile): boolean {
    const previousIdentity = projects.identity()
    const previousCodeAllowed = canUseCode.value
    const nextCodeAllowed = nextProfile.agentPolicy?.capabilities.code_generation !== false
    const nextIdentity = nextProfile.userId === undefined || nextProfile.userId === null
      ? ''
      : `${String(nextProfile.mainId || 'default')}:${String(nextProfile.userId)}`
    if (previousIdentity !== nextIdentity || previousCodeAllowed !== nextCodeAllowed) {
      clearUserBoundProjectState(previousIdentity !== nextIdentity || !nextCodeAllowed)
    }
    return nextCodeAllowed
  }

  return { selectBoundProject, clearUserBoundProjectState, prepareProjectBoundary }
}
