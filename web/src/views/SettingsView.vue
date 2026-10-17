<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../components/PageHeader.vue'
import UsersSettings from '../components/settings/UsersSettings.vue'
import { api } from '../lib/api'
import { columnLetter } from '../lib/format'
import { fetchOptions } from '../lib/report'
import type { Option, Sheet } from '../lib/types'

type Status = {
  trackingis_token: string; trackingis_url: string; default_teams: string[]; lark_app_id: string; lark_app_secret: string; users_with_sso_token?: number
  plan_sheet_id: number | null; plan_start_column: number; plan_products: number
}
type Check = { ok: boolean; message: string }

const tab = ref('connections')
const status = ref<Status | null>(null)
const form = reactive({ trackingis_token: '', default_teams: [] as number[], lark_app_id: '', lark_app_secret: '',
  plan_sheet_id: null as number | null | undefined, plan_start_column: 17 as number | undefined, plan_products: 11 as number | undefined })
const teams = ref<Option[]>([])
const sheets = ref<Sheet[]>([])
const saving = ref(false)
const testing = ref(false)
const checks = ref<Record<string, Check> | null>(null)

function fill(s: Status) {
  status.value = s
  Object.assign(form, { trackingis_token: '', lark_app_secret: '', lark_app_id: s.lark_app_id, default_teams: s.default_teams.map(Number),
    plan_sheet_id: s.plan_sheet_id, plan_start_column: s.plan_start_column, plan_products: s.plan_products })
}
async function loadTeams() {
  try { teams.value = (await fetchOptions('teams')).filter((t) => t.type !== 'bu') } catch { teams.value = [] }
}
onMounted(async () => {
  fill((await api.get<Status>('/settings')).data)
  loadTeams()
  sheets.value = (await api.get<Sheet[]>('/sheets')).data
})

async function test() {
  testing.value = true
  try { checks.value = (await api.post<Record<string, Check>>('/settings/test')).data } finally { testing.value = false }
}
async function save() {
  saving.value = true
  try {
    const res = await api.put<Status>('/settings', { ...form, default_teams: form.default_teams.map(String), plan_sheet_id: form.plan_sheet_id ?? 0 })
    fill(res.data)
    ElMessage.success(res.meta.message)
    await test()
    loadTeams()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <PageHeader subtitle="Connections, default ZenE teams and who can sign in" />
  <div class="section-card">
    <el-tabs v-model="tab">
      <el-tab-pane label="Connections" name="connections">
        <el-form v-if="status" label-position="top" class="max-w-2xl" @submit.prevent="save">
          <h3 class="card-title">trackingis</h3>
          <el-alert type="info" :closable="false" show-icon class="!mb-4"
                    :title="`Signing in with Isuccess System connects each user to trackingis with their own rights — no token to paste (${status.users_with_sso_token ?? 0} users connected).`" />
          <el-form-item :label="`Shared token (fallback) ${status.trackingis_token ? '(saved: ' + status.trackingis_token + ')' : '(not set)'}`">
            <el-input v-model="form.trackingis_token" type="password" show-password autocomplete="off" placeholder="Leave blank to keep the saved token" />
            <div class="text-xs text-muted">Used when a user has no SSO token (password sign-in) or theirs expired. Bearer token of an account with <code>view_report</code> on {{ status.trackingis_url }}. Stored encrypted.</div>
          </el-form-item>
          <el-form-item label="Default teams (ZenE)">
            <el-select v-model="form.default_teams" multiple filterable clearable placeholder="Every team" class="w-full">
              <el-option v-for="t in teams" :key="t.id" :label="t.name" :value="Number(t.id)" />
            </el-select>
            <div class="text-xs text-muted">The report starts filtered on these teams. Empty = every Etsy team.</div>
          </el-form-item>

          <h3 class="card-title mt-6">Lark (team sheets)</h3>
          <div class="grid gap-x-3 sm:grid-cols-2">
            <el-form-item label="App ID"><el-input v-model="form.lark_app_id" placeholder="cli_…" /></el-form-item>
            <el-form-item :label="`App Secret ${status.lark_app_secret ? '(saved)' : '(not set)'}`">
              <el-input v-model="form.lark_app_secret" type="password" show-password autocomplete="off" placeholder="Leave blank to keep" />
            </el-form-item>
          </div>
          <div class="-mt-2 mb-4 text-xs text-muted">Custom app with the <code>sheets:spreadsheet:readonly</code> scope (+ <code>wiki:wiki:readonly</code> for sheets in a wiki).</div>

          <h3 class="card-title mt-6">Plan (Etsy › Plan)</h3>
          <el-form-item label="Plan sheet">
            <el-select v-model="form.plan_sheet_id" clearable placeholder="No plan sheet" class="w-full">
              <el-option v-for="s in sheets" :key="s.id" :label="`${s.name} · ${s.tab_title}`" :value="s.id" />
            </el-select>
            <div class="text-xs text-muted">A sheet from Lark › Team sheets; the Plan page reads its last sync.</div>
          </el-form-item>
          <div class="grid gap-x-3 sm:grid-cols-2">
            <el-form-item :label="`Start column (${columnLetter(form.plan_start_column)})`">
              <el-input-number v-model="form.plan_start_column" :min="1" :max="52" class="!w-full" />
            </el-form-item>
            <el-form-item label="Products"><el-input-number v-model="form.plan_products" :min="1" :max="100" class="!w-full" /></el-form-item>
          </div>
          <div class="-mt-2 mb-4 text-xs text-muted">
            The start column holds "Product", then PL2/item, Total Sales, Total PL2, Tỷ trọng and the month columns (Sales/mo, Sales/day, PL2).
          </div>

          <div class="flex gap-2">
            <el-button type="primary" native-type="submit" :loading="saving">Save</el-button>
            <el-button :loading="testing" @click="test">Test connections</el-button>
          </div>
          <div v-if="checks" class="mt-4 grid gap-2">
            <el-alert v-for="(c, k) in checks" :key="k" :type="c.ok ? 'success' : 'error'" :closable="false" show-icon :title="`${k}: ${c.message}`" />
          </div>
        </el-form>
      </el-tab-pane>
      <el-tab-pane label="Users" name="users"><UsersSettings /></el-tab-pane>
    </el-tabs>
  </div>
</template>
