import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './lib/auth'
import { FAMILY_LIST } from './lib/families'
import AppLayout from './layouts/AppLayout.vue'

declare module 'vue-router' {
  interface RouteMeta { title?: string; group?: string; adminOnly?: boolean; public?: boolean; wholeZene?: boolean }
}

const HOME = '/etsy/report'
const FamilyView = () => import('./views/FamilyView.vue') // Etsy › Ornament, Shirt, Blanket…

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true, title: 'Sign in' } },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: HOME },
        { path: 'etsy/report', component: () => import('./views/EtsyReportView.vue'), meta: { title: 'Report Etsy', group: 'Etsy' } },
        ...FAMILY_LIST.map((f) => ({
          path: `etsy/${f.key}`, component: FamilyView, props: { family: f.key }, meta: { title: `${f.name} report`, group: 'Etsy' },
        })),
        { path: 'etsy/plan', component: () => import('./views/PlanView.vue'), meta: { title: 'Plan by product', group: 'Etsy', wholeZene: true } },
        { path: 'sheets', component: () => import('./views/SheetsView.vue'), meta: { title: 'Team sheets', group: 'Lark', wholeZene: true } },
        { path: 'settings', component: () => import('./views/SettingsView.vue'), meta: { title: 'Settings', group: 'System', adminOnly: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: HOME },
  ],
})

router.beforeEach(async (to) => {
  const user = await auth.load()
  if (to.meta.public) return user && to.path === '/login' ? HOME : true
  if (!user) return { path: '/login', query: { next: to.fullPath } }
  if (to.meta.adminOnly && user.role !== 'admin') return HOME
  if (to.meta.wholeZene && auth.ownSalesOnly.value) return HOME // the whole of ZenE's plan and sheets: not for their own sales only
  return true
})

// After a deploy, a tab opened earlier asks for page chunks that no longer exist: load the new version instead.
const RELOAD_KEY = 'rzn:chunk-reload'
router.onError((err, to) => {
  const msg = String((err as Error)?.message ?? err)
  if (!/dynamically imported module|Importing a module script failed|Failed to fetch/i.test(msg)) return
  if (sessionStorage.getItem(RELOAD_KEY) === to.fullPath) return
  sessionStorage.setItem(RELOAD_KEY, to.fullPath)
  window.location.assign(to.fullPath)
})
router.afterEach(() => sessionStorage.removeItem(RELOAD_KEY))

router.afterEach((to) => { document.title = `${to.meta.title ?? 'ReportZenE'} · ReportZenE` })
window.addEventListener('rzn:logout', () => { if (router.currentRoute.value.path !== '/login') router.push('/login') })
