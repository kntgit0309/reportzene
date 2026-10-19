<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Aim, DataLine, Document, Expand, Fold, Present, Setting } from '@element-plus/icons-vue'
import AgentTokens from '../components/AgentTokens.vue'
import { auth } from '../lib/auth'

const MOBILE_PX = 768
const route = useRoute()
const router = useRouter()
const collapsed = ref(window.innerWidth < MOBILE_PX)
const user = computed(() => auth.state.user)
const tokensOpen = ref(false)

// Same grouping as the trackingis sidebar: a small group title, then its pages
const GROUPS = [
  { title: 'Etsy', items: [
    { path: '/etsy/report', title: 'Report', icon: DataLine },
    { path: '/etsy/ornament', title: 'Ornament', icon: Present },
    { path: '/etsy/plan', title: 'Plan', icon: Aim },
  ] },
  { title: 'Lark', items: [{ path: '/sheets', title: 'Team sheets', icon: Document }] },
  { title: 'System', adminOnly: true, items: [{ path: '/settings', title: 'Settings', icon: Setting }] },
]
const groups = computed(() => GROUPS.filter((g) => !g.adminOnly || auth.isAdmin.value))
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
      <header class="sticky top-0 z-10 flex h-[var(--header-height)] items-center justify-between border-b border-[#e2e8f0] bg-white/90 px-4 backdrop-blur">
        <el-button text circle aria-label="Collapse menu" @click="collapsed = !collapsed"><el-icon :size="18"><component :is="collapsed ? Expand : Fold" /></el-icon></el-button>
        <el-dropdown trigger="click">
          <div class="flex cursor-pointer items-center gap-2">
            <span class="hidden text-right text-xs leading-tight sm:block">
              <b class="block text-slate-900">{{ user?.name }}</b>
              <span class="text-slate-500">{{ user?.role === 'admin' ? 'Admin' : 'Member' }} · {{ user?.code }}</span>
            </span>
            <el-avatar :size="34" :src="user?.avatar_url ?? undefined" class="!bg-[#2563eb]">{{ user?.name.slice(0, 1).toUpperCase() }}</el-avatar>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>{{ user?.email }}</el-dropdown-item>
              <el-dropdown-item @click="tokensOpen = true">Agent tokens (MCP)</el-dropdown-item>
              <el-dropdown-item divided @click="logout">Sign out</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </header>
      <main class="flex-1 px-4 py-5 sm:px-6"><RouterView /></main>
      <AgentTokens v-model="tokensOpen" />
    </div>
  </div>
</template>
