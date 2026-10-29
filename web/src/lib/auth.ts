import { computed, reactive } from 'vue'
import { api, setViewAsId, viewAsId } from './api'
import type { User } from './types'

// user = the account the app acts as: the signed-in one, or the seller account they view as (View as, read-only)
const state = reactive<{ user: User | null; loaded: boolean }>({ user: null, loaded: false })

export const auth = {
  state,
  isAdmin: computed(() => state.user?.role === 'admin'),
  /** A member limited to their own sales (Settings › Users): the server filters every report; pages of the whole of ZenE are hidden. */
  ownSalesOnly: computed(() => state.user?.role !== 'admin' && (state.user?.scope_sellers?.length ?? 0) > 0),
  /** Who is viewing as the current account, when the app is viewed as a seller. */
  viewedBy: computed(() => state.user?.viewed_by ?? null),
  /** The signed-in user may view as a seller account. */
  mayViewAs: computed(() => !!state.user?.may_view_as),

  async load(): Promise<User | null> {
    if (state.loaded) return state.user
    try {
      state.user = (await api.get<User>('/auth/me')).data
    } catch {
      if (viewAsId()) { // the account viewed as is gone or locked: back to the signed-in user
        setViewAsId(null)
        try { state.user = (await api.get<User>('/auth/me')).data } catch { state.user = null }
      } else {
        state.user = null
      }
    }
    state.loaded = true
    return state.user
  },

  async login(email: string, password: string): Promise<void> {
    setViewAsId(null)
    state.user = (await api.post<{ user: User }>('/auth/login', { email, password })).data.user
    state.loaded = true
  },

  async logout(): Promise<void> {
    setViewAsId(null)
    try { await api.post('/auth/logout') } catch { /* session already gone */ }
    state.user = null
  },

  /** View ReportZenE as this seller account (null: back to yourself). Reloads: every report is fetched again as them. */
  viewAs(id: number | null): void {
    setViewAsId(id)
    window.location.assign('/etsy/report')
  },
}

window.addEventListener('rzn:logout', () => { setViewAsId(null); state.user = null })
