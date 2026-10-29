<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Aim, DataLine, Document, Expand, Fold, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AgentTokens from '../components/AgentTokens.vue'
import { api } from '../lib/api'
import { auth } from '../lib/auth'
import { FAMILY_LIST } from '../lib/families'
import type { ViewAsOption } from '../lib/types'

const MOBILE_PX = 768
const route = useRoute()
const router = useRouter()
const collapsed = ref(window.innerWidth < MOBILE_PX)
const user = computed(() => auth.state.user)
const tokensOpen = ref(false)

// View as: see ReportZenE as a seller account does (their sales, their menu), read-only; for admins and members an admin allowed
const viewAsOpen = ref(false)
const viewAsList = ref<ViewAsOption[]>([])
const viewAsPick = ref<number | null>(null)
async function openViewAs() {
  viewAsPick.value = null
  viewAsOpen.value = true
  try { viewAsList.value = (await api.get<ViewAsOption[]>('/auth/view-as')).data } catch (e) { ElMessage.error((e as Error).message) }
}

// Same grouping as the trackingis sidebar: a small group title, then its pages
const GROUPS = [
  { title: 'Etsy', items: [
    { path: '/etsy/report', title: 'Report', icon: DataLine },
    ...FAMILY_LIST.map((f) => ({ path: `/etsy/${f.key}`, title: f.name, icon: f.icon })),
    { path: '/etsy/plan', title: 'Plan', icon: Aim, wholeZene: true },
  ] },
  { title: 'Lark', items: [{ path: '/sheets', title: 'Team sheets', icon: Document, wholeZene: true }] },
  { title: 'System', adminOnly: true, items: [{ path: '/settings', title: 'Settings', icon: Setting }] },
]
// a member limited to their own sales does not get the pages of the whole of ZenE (plan, team sheets)
const groups = computed(() => GROUPS.filter((g) => !g.adminOnly || auth.isAdmin.value)
  .map((g) => ({ ...g, items: g.items.filter((m) => !('wholeZene' in m && m.wholeZene && auth.ownSalesOnly.value)) }))
  .filter((g) => g.items.length))
const active = computed(() => GROUPS.flatMap((g) => g.items).find((m) => route.path.startsWith(m.path))?.path ?? route.path)

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="flex min-h-full">
    <aside class="fixed inset-y-0 left-0 z-20 flex flex-col overflow-y-auto border-r border-[#e2e8f0] bg-[var(--sidebar-bg)] transition-all"
           :style="{ width: collapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)' }">
      <div class="flex h-[var(--header-height)] shrink-0 items-center gap-2.5 px-4">
        <img src="/favicon.svg" class="h-8 w-8" alt="" />
        <div v-if="!collapsed" class="leading-tight">
          <b class="block text-[15px] text-slate-900">ReportZenE</b>
          <span class="text-[11px] text-slate-500">iSuccess System</span>
        </div>
      </div>
      <el-menu class="app-menu pb-4" router :default-active="active" :collapse="collapsed">
        <template v-for="g in groups" :key="g.title">
          <div v-if="!collapsed" class="menu-group">{{ g.title }}</div>
          <el-menu-item v-for="m in g.items" :key="m.path" :index="m.path">
            <el-icon><component :is="m.icon" /></el-icon>
            <span>{{ m.title }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </aside>

    <div class="flex min-h-full min-w-0 flex-1 flex-col transition-all"
         :style="{ marginLeft: collapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)' }">
      <div class="sticky top-0 z-10">
      <div v-if="auth.viewedBy.value" class="flex flex-wrap items-center justify-between gap-2 bg-amber-100 px-4 py-2 text-sm text-amber-900">
        <span>Viewing as <b>{{ user?.name }}</b>: what they see, read-only. You are signed in as {{ auth.viewedBy.value.name }}.</span>
        <span class="flex gap-2">
          <el-button size="small" @click="openViewAs">Switch</el-button>
          <el-button size="small" type="primary" @click="auth.viewAs(null)">Exit</el-button>
        </span>
      </div>
      <header class="flex h-[var(--header-height)] items-center justify-between border-b border-[#e2e8f0] bg-white/90 px-4 backdrop-blur">
        <el-button text circle aria-label="Collapse menu" @click="collapsed = !collapsed"><el-icon :size="18"><component :is="collapsed ? Expand : Fold" /></el-icon></el-button>
        <el-dropdown trigger="click">
          <div class="flex cursor-pointer items-center gap-2">
            <span class="hidden text-right text-xs leading-tight sm:block">
              <b class="block text-slate-900">{{ user?.name }}</b>
              <span class="text-slate-500">{{ user?.role === 'admin' ? 'Admin' : auth.ownSalesOnly.value ? 'Member · own sales' : 'Member' }} · {{ user?.code }}</span>
            </span>
            <el-avatar :size="34" :src="user?.avatar_url ?? undefined" class="!bg-[#2563eb]">{{ user?.name.slice(0, 1).toUpperCase() }}</el-avatar>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>{{ user?.email }}</el-dropdown-item>
              <el-dropdown-item v-if="auth.mayViewAs.value" @click="openViewAs">View as seller…</el-dropdown-item>
              <el-dropdown-item @click="tokensOpen = true">Agent tokens (MCP)</el-dropdown-item>
              <el-dropdown-item divided @click="logout">Sign out</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>
      </div>
      <!-- keyed by path: Etsy › Ornament, Shirt, Blanket… are one page component, each path gets its own page -->
      <main class="flex-1 px-4 py-5 sm:px-6"><RouterView :key="route.path" /></main>
      <AgentTokens v-model="tokensOpen" />
      <el-dialog v-model="viewAsOpen" title="View as seller" width="min(440px, 92vw)">
        <p class="mt-0 text-sm text-slate-500">See ReportZenE exactly as this seller account does: their sales, their menu, read-only. Exit from the bar at the top.</p>
        <el-select v-model="viewAsPick" filterable placeholder="Pick a seller account" class="w-full" no-data-text="No seller account yet: set Sees for a member in Settings › Users">
          <el-option v-for="o in viewAsList" :key="o.id" :label="`${o.name} (${o.code})`" :value="o.id" />
        </el-select>
        <template #footer>
          <el-button @click="viewAsOpen = false">Close</el-button>
          <el-button type="primary" :disabled="viewAsPick == null" @click="viewAsPick != null && auth.viewAs(viewAsPick)">View</el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>
