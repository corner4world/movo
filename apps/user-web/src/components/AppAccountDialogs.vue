<script setup lang="ts">
import type { Component } from 'vue'
import type { UserProfile } from '../api/auth'
import ProfileModal from './ProfileModal.vue'

defineProps<{
  loginModal: Component
  billingModal?: Component
  createOrganizationModal?: Component
  loginOpen: boolean
  billingOpen: boolean
  profileOpen: boolean
  createOrganizationOpen: boolean
  savedUsers: string[]
  token: string
  profile: UserProfile | null
  canAccessBillingAdmin: boolean
}>()

const emit = defineEmits<{
  (event: 'close-login'): void
  (event: 'close-billing'): void
  (event: 'close-profile'): void
  (event: 'close-create-organization'): void
  (event: 'login-success', payload: { token: string; username: string; profile?: UserProfile }): void
  (event: 'profile-updated', profile: UserProfile): void
}>()
</script>

<template>
  <component
    :is="loginModal"
    :open="loginOpen"
    :saved-users="savedUsers"
    @close="emit('close-login')"
    @login-success="emit('login-success', $event)"
  />
  <component
    v-if="billingModal"
    :is="billingModal"
    :open="billingOpen"
    :token="token"
    :can-access-admin="canAccessBillingAdmin"
    @close="emit('close-billing')"
    @upgrade-success="emit('login-success', $event)"
  />
  <ProfileModal
    :open="profileOpen"
    :token="token"
    :profile="profile"
    @close="emit('close-profile')"
    @updated="emit('profile-updated', $event)"
  />
  <component
    v-if="createOrganizationModal"
    :is="createOrganizationModal"
    :open="createOrganizationOpen"
    :token="token"
    @close="emit('close-create-organization')"
    @created="emit('login-success', $event)"
  />
</template>
