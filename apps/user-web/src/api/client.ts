import axios, { type AxiosInstance, type CreateAxiosDefaults } from 'axios'
import { getLocale } from '../composables/i18n'


export function createApiClient(config: CreateAxiosDefaults = {}): AxiosInstance {
  const client = axios.create(config)
  client.interceptors.request.use((request) => {
    request.headers['Accept-Language'] = getLocale() === 'en' ? 'en-US' : 'zh-CN'
    const token = typeof window !== 'undefined' ? window.localStorage.getItem('auth_token') : ''
    if (token && !request.headers.Authorization) {
      request.headers.Authorization = `Bearer ${token}`
    }
    return request
  })
  return client
}
