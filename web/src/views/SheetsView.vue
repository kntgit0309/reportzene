<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Link, Plus, Refresh, Search } from '@element-plus/icons-vue'
import PageHeader from '../components/PageHeader.vue'
import { api } from '../lib/api'
import { auth } from '../lib/auth'
import { dateTime } from '../lib/format'
import type { Sheet, SheetTab } from '../lib/types'

const PER_PAGE = 50
const sheets = ref<Sheet[]>([])
const activeId = ref<number | null>(null)
const active = computed(() => sheets.value.find((s) => s.id === activeId.value) ?? null)
const rows = ref<Record<string, string>[]>([])
const total = ref(0)
const page = ref(1)
const q = ref('')
const loading = ref(false)
const syncing = ref(false)

async function loadSheets() {
  sheets.value = (await api.get<Sheet[]>('/sheets')).data
  if (!active.value) activeId.value = sheets.value[0]?.id ?? null
}
async function loadRows() {
  if (!activeId.value) { rows.value = []; total.value = 0; return }
  loading.value = true
  try {
    const res = await api.get<Record<string, string>[]>(`/sheets/${activeId.value}/rows?q=${encodeURIComponent(q.value)}&page=${page.value}&per_page=${PER_PAGE}`)
    rows.value = res.data
    total.value = res.paging?.total ?? 0
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
watch(activeId, () => { page.value = 1; q.value = ''; loadRows() })
onMounted(async () => { await loadSheets(); loadRows() })

async function sync(s: Sheet) {
  syncing.value = true
  try {
    const res = await api.post<Sheet>(`/sheets/${s.id}/sync`)
    ElMessage.success(res.meta.message)
    await loadSheets()
    loadRows()
  } catch (e) {
    ElMessage.error((e as Error).message)
    loadSheets()
  } finally {
    syncing.value = false
  }
}

// --- add / edit (admins) ---
const dialog = ref(false)
const editing = ref<Sheet | null>(null)
const form = reactive({ name: '', url: '', tab_id: '', header_row: 1 })
const tabs = ref<SheetTab[]>([])
const checking = ref(false)
const saving = ref(false)

function openForm(s: Sheet | null) {
  editing.value = s
  Object.assign(form, s ? { name: s.name, url: s.url, tab_id: s.tab_id, header_row: s.header_row } : { name: '', url: '', tab_id: '', header_row: 1 })
  tabs.value = s ? [{ sheet_id: s.tab_id, title: s.tab_title, rows: s.row_count }] : []
  dialog.value = true
}
async function checkLink() {
  checking.value = true
  try {
    const res = (await api.post<{ tabs: SheetTab[]; linked_tab_id: string }>('/sheets/tabs', { url: form.url.trim() })).data
    tabs.value = res.tabs
    form.tab_id = res.linked_tab_id || res.tabs[0]?.sheet_id || ''
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    checking.value = false
  }
}
async function save() {
  saving.value = true
  try {
    const body = { ...form, url: form.url.trim() }
    const res = editing.value ? await api.put<Sheet>(`/sheets/${editing.value.id}`, body) : await api.post<Sheet>('/sheets', body)
    ElMessage.success(res.meta.message)
    dialog.value = false
    activeId.value = res.data.id
    await loadSheets()
    loadRows()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}
async function remove(s: Sheet) {
  try {
    await ElMessageBox.confirm(`Remove "${s.name}" from ReportZenE? The Lark sheet itself is not touched.`, 'Remove sheet?', { type: 'warning', confirmButtonText: 'Remove' })
    await api.del(`/sheets/${s.id}`)
    activeId.value = null
    await loadSheets()
    loadRows()
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}
</script>

<template>
  <PageHeader subtitle="Reports the team fills in Lark Sheets, read-only. Press Sync to read the sheet again.">
    <template #actions>
      <el-button v-if="auth.isAdmin.value" type="primary" :icon="Plus" @click="openForm(null)">Add sheet</el-button>
    </template>
  </PageHeader>

  <el-empty v-if="!sheets.length" description="No sheet yet" class="section-card">
    <p class="text-sm text-muted">An admin adds a Lark Sheet link here (the Lark app must be added to the sheet: … → Add document app).</p>
  </el-empty>

  <div v-else class="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
    <div class="section-card !p-2">
      <button v-for="s in sheets" :key="s.id" type="button"
              class="mb-1 block w-full cursor-pointer rounded-lg border-0 px-3 py-2 text-left transition-colors"
              :class="s.id === activeId ? 'bg-[var(--sidebar-active-bg)] text-[#2563eb]' : 'bg-transparent hover:bg-[var(--sidebar-hover-bg)]'"
              @click="activeId = s.id">
        <div class="truncate text-sm font-semibold">{{ s.name }}</div>
        <div class="text-xs text-muted">{{ s.tab_title || 'Tab' }} · {{ s.row_count }} rows</div>
        <el-tag v-if="s.last_error" type="danger" size="small" class="mt-1">Sync error</el-tag>
      </button>
    </div>

    <div v-if="active" class="section-card min-w-0">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0">
          <h2 class="card-title !mb-1">{{ active.name }}</h2>
          <div class="text-xs text-muted">
            Tab <b>{{ active.tab_title }}</b> · header row {{ active.header_row }} · synced {{ dateTime(active.last_synced_at) }}
            · <a :href="active.url" target="_blank" rel="noopener" class="text-[#2563eb]"><el-icon><Link /></el-icon> Open in Lark</a>
          </div>
        </div>
        <div class="flex gap-2">
          <el-input v-model="q" clearable placeholder="Search every column" :prefix-icon="Search" class="!w-[220px]" @change="page = 1; loadRows()" />
          <el-button :icon="Refresh" :loading="syncing" @click="sync(active)">Sync</el-button>
          <template v-if="auth.isAdmin.value">
            <el-button :icon="Edit" @click="openForm(active)" />
            <el-button :icon="Delete" type="danger" plain @click="remove(active)" />
          </template>
        </div>
      </div>
      <el-alert v-if="active.last_error" type="error" :title="active.last_error" :closable="false" show-icon class="!mb-3"
                description="The rows below are from the last successful sync." />
      <el-table v-loading="loading" :data="rows" border size="small" max-height="calc(100vh - 300px)" empty-text="No rows">
        <el-table-column label="#" prop="_row" width="64" fixed />
        <el-table-column v-for="h in active.header" :key="h" :label="h" :prop="h" min-width="140" show-overflow-tooltip />
      </el-table>
      <div class="mt-3 flex justify-end">
        <el-pagination v-model:current-page="page" :page-size="PER_PAGE" :total="total" background layout="total, prev, pager, next" @current-change="loadRows" />
      </div>
    </div>
  </div>

  <el-dialog v-model="dialog" :title="editing ? 'Edit sheet' : 'Add Lark sheet'" width="min(560px, 94vw)">
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item label="Name"><el-input v-model="form.name" maxlength="120" placeholder="e.g. Báo cáo tuần Etsy 1" /></el-form-item>
      <el-form-item label="Lark Sheet link">
        <div class="flex w-full gap-2">
          <el-input v-model="form.url" placeholder="https://….larksuite.com/sheets/…?sheet=…" />
          <el-button :loading="checking" :disabled="form.url.trim().length < 10" @click="checkLink">Check</el-button>
        </div>
        <div class="text-xs text-muted">Open the sheet → … → Add document app → add the ReportZenE Lark app first.</div>
      </el-form-item>
      <div class="grid gap-x-3 sm:grid-cols-[1fr_140px]">
        <el-form-item label="Tab">
          <el-select v-model="form.tab_id" placeholder="Tab in the link (or the first)" clearable class="w-full">
            <el-option v-for="t in tabs" :key="t.sheet_id" :label="`${t.title} (${t.rows} rows)`" :value="t.sheet_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Header row"><el-input-number v-model="form.header_row" :min="1" :max="50" class="!w-full" /></el-form-item>
      </div>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">Cancel</el-button>
      <el-button type="primary" :loading="saving" :disabled="!form.name.trim() || !form.url.trim()" @click="save">Save & sync</el-button>
    </template>
  </el-dialog>
</template>
