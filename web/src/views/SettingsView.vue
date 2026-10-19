<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Plus } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import UsersSettings from '../components/settings/UsersSettings.vue'
import { api } from '../lib/api'
import { FAMILY_LIST } from '../lib/families'
import { columnLetter, dateTime } from '../lib/format'
import { fetchOptions } from '../lib/report'
import type { AccountReplacement, FamilyKey, Option, Sheet } from '../lib/types'

type Status = {
  trackingis_token: string; trackingis_url: string; default_teams: string[]; lark_app_id: string; lark_app_secret: string; users_with_sso_token?: number
  sheet_sync_at: string // daily sync of every team sheet, "HH:MM" Vietnam time; "" = off
  sheet_sync_last?: { day?: string; started_at?: string; finished_at?: string; synced?: number; failed?: number }
  plan_sheet_id: number | null; plan_start_column: number; plan_products: number; pl2_cf_sheet_id: number | null
  family_plan_sheets: Partial<Record<FamilyKey, number>> // product family (Etsy › Ornament…) → its plan sheet
  account_replacements: AccountReplacement[]
}
type Check = { ok: boolean; message: string }

const tab = ref('connections')
const status = ref<Status | null>(null)
const form = reactive({ trackingis_token: '', default_teams: [] as number[], lark_app_id: '', lark_app_secret: '', sheet_sync_at: '10:00',
  plan_sheet_id: null as number | null | undefined, plan_start_column: 17 as number | undefined, plan_products: 11 as number | undefined,
  pl2_cf_sheet_id: null as number | null | undefined,
  family_plan_sheets: {} as Partial<Record<FamilyKey, number | null>>, account_replacements: [] as AccountReplacement[] })
const teams = ref<Option[]>([])
const shops = ref<Option[]>([])
const sheets = ref<Sheet[]>([])
const saving = ref(false)
const testing = ref(false)
const checks = ref<Record<string, Check> | null>(null)

function fill(s: Status) {
  status.value = s
  Object.assign(form, { trackingis_token: '', lark_app_secret: '', lark_app_id: s.lark_app_id, sheet_sync_at: s.sheet_sync_at,
    default_teams: s.default_teams.map(Number),
    plan_sheet_id: s.plan_sheet_id, plan_start_column: s.plan_start_column, plan_products: s.plan_products,
    pl2_cf_sheet_id: s.pl2_cf_sheet_id,
    family_plan_sheets: { ...s.family_plan_sheets }, account_replacements: s.account_replacements.map((r) => ({ ...r })) })
}
const lastSync = computed(() => {
  const l = status.value?.sheet_sync_last
  if (!l?.day) return 'No daily sync has run yet.'
  if (!l.finished_at) return `Running since ${dateTime(l.started_at)}…`
  return `Last run ${dateTime(l.finished_at)}: ${l.synced} synced${l.failed ? `, ${l.failed} failed (see Lark › Team sheets)` : ''}.`
})
async function loadTeams() {
  try { teams.value = (await fetchOptions('teams')).filter((t) => t.type !== 'bu') } catch { teams.value = [] }
  try { shops.value = await fetchOptions('shops') } catch { shops.value = [] }
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
    const res = await api.put<Status>('/settings', { ...form, default_teams: form.default_teams.map(String), plan_sheet_id: form.plan_sheet_id ?? 0,
      pl2_cf_sheet_id: form.pl2_cf_sheet_id ?? 0, sheet_sync_at: form.sheet_sync_at || '', // cleared = no daily sync
      family_plan_sheets: Object.fromEntries(FAMILY_LIST.map((f) => [f.key, form.family_plan_sheets[f.key] ?? 0])),
      account_replacements: form.account_replacements.filter((r) => r.suspended.trim() && r.replacement.trim()) })
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
          <el-form-item label="Sync every team sheet daily at (Vietnam time)">
            <el-time-select v-model="form.sheet_sync_at" start="00:00" step="00:30" end="23:30" clearable placeholder="Off" class="!w-40" />
            <div class="w-full text-xs text-muted">
              The sheets stay live in Lark; ReportZenE reads them all again at this time each day (and on Sync). {{ lastSync }}
            </div>
          </el-form-item>

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
          <el-form-item label="PL2 CF sheet (Etsy › Report)">
            <el-select v-model="form.pl2_cf_sheet_id" clearable placeholder="No PL2 CF sheet" class="w-full">
              <el-option v-for="s in sheets" :key="s.id" :label="`${s.name} · ${s.tab_title}`" :value="s.id" />
            </el-select>
            <div class="text-xs text-muted">
              Finance's "Tổng kết PL Monthly" tab (PL2 theo CF): "B.U | TỔNG | MM-YYYY" header, then the KẾ HOẠCH, THỰC ĐẠT and
              CHÊNH LỆCH rows of B.U ZenE and each team. Etsy › Report compares it with the PL2 estimated from sales (KT).
            </div>
          </el-form-item>
          <el-form-item v-for="f in FAMILY_LIST" :key="f.key" :label="`${f.name} plan sheet (Etsy › ${f.name})`">
            <el-select v-model="form.family_plan_sheets[f.key]" clearable :placeholder="`No ${f.name.toLowerCase()} plan`" class="w-full">
              <el-option v-for="s in sheets" :key="s.id" :label="`${s.name} · ${s.tab_title}`" :value="s.id" />
            </el-select>
            <div class="text-xs text-muted">{{ f.planSheetHint }}</div>
          </el-form-item>
          <el-form-item label="Account replacements (Etsy › Ornament, Shirt, Blanket…)">
            <div class="w-full space-y-2">
              <div v-for="(r, i) in form.account_replacements" :key="i" class="flex items-center gap-2">
                <el-input v-model="r.suspended" placeholder="Suspended store, as in the plan sheet" class="flex-1" />
                <span class="text-muted">→</span>
                <el-select v-model="r.replacement" filterable allow-create default-first-option placeholder="Store that takes over" class="flex-1">
                  <el-option v-for="s in shops" :key="s.id" :label="s.name" :value="s.name" />
                </el-select>
                <el-button :icon="Delete" circle plain aria-label="Remove" @click="form.account_replacements.splice(i, 1)" />
              </div>
              <el-button size="small" :icon="Plus" @click="form.account_replacements.push({ suspended: '', replacement: '' })">Add replacement</el-button>
            </div>
            <div class="text-xs text-muted">
              When a store is suspended, the store that takes over gets its line of every product plan, and the suspended
              store's sales count in its row.
            </div>
          </el-form-item>

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
