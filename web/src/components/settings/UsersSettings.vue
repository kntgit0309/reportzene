<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { api } from '../../lib/api'
import { auth } from '../../lib/auth'
import { fetchOptions } from '../../lib/report'
import type { Option, Role, User } from '../../lib/types'

type Form = { email: string; name: string; code: string; role: Role; password: string; scope_sellers: string[] }
const users = ref<User[]>([])
const dialog = ref(false)
const editing = ref<User | null>(null)
const form = ref<Form>({ email: '', name: '', code: '', role: 'member', password: '', scope_sellers: [] })
const saving = ref(false)
const sellers = ref<Option[]>([]) // trackingis sellers, for a member's data scope
const sellerName = computed(() => new Map(sellers.value.map((s) => [String(s.id), s.name])))
const sees = (u: User) => (u.role === 'admin' ? 'Everything' : u.scope_sellers?.length
  ? `Own sales: ${u.scope_sellers.map((id) => sellerName.value.get(id) ?? `seller ${id}`).join(', ')}` : 'The whole of ZenE')

async function load() {
  users.value = (await api.get<User[]>('/users')).data
}
onMounted(async () => {
  await load()
  try { sellers.value = await fetchOptions('sellers') } catch { sellers.value = [] }
})

function openNew() {
  editing.value = null
  form.value = { email: '', name: '', code: '', role: 'member', password: '', scope_sellers: [] }
  dialog.value = true
}
function openEdit(u: User) {
  editing.value = u
  form.value = { email: u.email, name: u.name, code: u.code, role: u.role, password: '', scope_sellers: [...(u.scope_sellers ?? [])] }
  dialog.value = true
}
async function save() {
  saving.value = true
  try {
    if (editing.value) {
      const { name, code, role, password, scope_sellers } = form.value
      await api.patch(`/users/${editing.value.id}`, { name, code, role, scope_sellers, ...(password ? { password } : {}) })
    } else {
      const { password, ...rest } = form.value
      await api.post('/users', password ? form.value : rest)
    }
    ElMessage.success('Saved')
    dialog.value = false
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    saving.value = false
  }
}
async function toggleActive(u: User) {
  try {
    await api.patch(`/users/${u.id}`, { is_active: !u.is_active })
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}
</script>

<template>
  <div class="mb-3 flex justify-between">
    <p class="m-0 text-sm text-slate-500">A first Isuccess System sign-in creates a Member account: active right away for emails on the allow-list, otherwise <b>locked</b> until an admin activates it here (sales data). Members read the reports and sheets; a member limited to some sellers (Sees) gets only those sellers' sales in every report and MCP tool, without the Plan and Team sheets pages. Admins also get Settings and manage sheets and users.</p>
    <el-button type="primary" :icon="Plus" @click="openNew">Add user</el-button>
  </div>
  <el-table :data="users" size="small">
    <el-table-column label="Name" min-width="160">
      <template #default="{ row }">{{ row.name }} <el-tag v-if="row.is_pod" size="small" effect="plain" class="ml-1">Isuccess</el-tag></template>
    </el-table-column>
    <el-table-column label="Email" prop="email" min-width="200" />
    <el-table-column label="Code" prop="code" width="100" />
    <el-table-column label="Role" width="140"><template #default="{ row }">{{ row.role === 'admin' ? 'Admin' : 'Member' }}</template></el-table-column>
    <el-table-column label="Sees" min-width="180"><template #default="{ row }"><span class="text-xs">{{ sees(row as User) }}</span></template></el-table-column>
    <el-table-column label="Status" width="110"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? 'Active' : 'Locked' }}</el-tag></template></el-table-column>
    <el-table-column width="170" align="right">
      <template #default="{ row }">
        <el-button size="small" @click="openEdit(row as User)">Edit</el-button>
        <el-button v-if="row.id !== auth.state.user?.id" size="small" :type="row.is_active ? 'danger' : 'success'" plain @click="toggleActive(row as User)">{{ row.is_active ? 'Lock' : 'Unlock' }}</el-button>
      </template>
    </el-table-column>
  </el-table>

  <el-dialog v-model="dialog" :title="editing ? `Edit ${editing.name}` : 'Add user'" width="min(480px, 92vw)">
    <el-form label-position="top">
      <el-form-item label="Email" required><el-input v-model="form.email" :disabled="!!editing" /></el-form-item>
      <div class="grid grid-cols-2 gap-x-3">
        <el-form-item label="Name" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="Short code" required><el-input v-model="form.code" maxlength="16" @input="(v: string) => (form.code = v.toUpperCase().replace(/[^A-Z0-9]/g, ''))" /></el-form-item>
      </div>
      <el-form-item label="Role">
        <el-radio-group v-model="form.role"><el-radio value="member">Member</el-radio><el-radio value="admin">Admin</el-radio></el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.role === 'member'" label="Sees">
        <el-select v-model="form.scope_sellers" multiple filterable clearable placeholder="The whole of ZenE" class="w-full">
          <el-option v-for="s in sellers" :key="s.id" :label="s.name" :value="String(s.id)" />
        </el-select>
        <div class="text-xs text-muted">Pick the member's own seller (trackingis) to show them only their sales; leave empty for the whole of ZenE.</div>
      </el-form-item>
      <el-form-item :label="editing ? 'New password (leave blank to keep the current one)' : 'Password (leave blank = Isuccess System sign-in only)'">
        <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialog = false">Close</el-button>
      <el-button type="primary" :loading="saving" @click="save">Save</el-button>
    </template>
  </el-dialog>
</template>
