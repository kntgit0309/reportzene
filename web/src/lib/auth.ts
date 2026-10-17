import { computed, reactive } from 'vue'
import { api } from './api'
import type { User } from './types'

const state = reactive<{ user: User | null; loaded: boolean }>({ user: null, loaded: false })

export const auth = {
  state,
  isAdmin: computed(() => state.user?.role === 'admin'),

  async load(): Promise<User | null> {
    if (state.loaded) return state.user
    try {
      state.user = (await api.get<User>('/auth/me')).data
    } catch {
      state.user = null
    }
    state.loaded = true
    return state.user
  },

  async login(email: string, password: string): Promise<void> {
    state.user = (await api.post<{ user: User }>('/auth/login', { email, password })).data.user
    state.loaded = true
  },

  async logout(): Promise<void> {
    try { await api.post('/auth/logout') } catch { /* session already gone */ }
    state.user = null
  },
}

window.addEventListener('rzn:logout', () => { state.user = null })
