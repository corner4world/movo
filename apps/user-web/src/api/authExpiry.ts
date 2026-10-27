import type { AxiosInstance } from 'axios'
import { getLocale } from '../composables/i18n'

export const AUTH_EXPIRED_EVENT = 'askai:auth-expired'

function bearerTokenFromHeaders(headers: any): string {
  if (!headers) return ''
  const value = typeof headers.get === 'function'
    ? headers.get('Authorization') || headers.get('authorization')
    : headers.Authorization || headers.authorization
  return String(value || '').trim()
}

export function notifyAuthExpired(): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
}

export function notifyAuthExpiredFromResponse(response: Response, authenticated: boolean): void {
  if (authenticated && response.status === 401) {
    notifyAuthExpired()
  }
}

export function installAuthExpiryInterceptor(client: AxiosInstance): void {
  client.interceptors.request.use((request) => {
    request.headers['Accept-Language'] = getLocale() === 'en' ? 'en-US' : 'zh-CN'
    return request
  })
  client.interceptors.response.use(
    (response) => response,
    (error) => {
      const hasBearerToken = /^Bearer\s+\S+/i.test(bearerTokenFromHeaders(error?.config?.headers))
      if (hasBearerToken && error?.response?.status === 401) {
        notifyAuthExpired()
      }
      return Promise.reject(error)
    },
  )
}
