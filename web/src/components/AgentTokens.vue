<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../lib/api'
import { copyText, dateTime } from '../lib/format'

type Token = { id: number; name: string; hint: string; created_at: string; last_used_at: string | null }

const open = defineModel<boolean>({ required: true })
const tokens = ref<Token[]>([])
const name = ref('Agent')
const created = ref('')
const busy = ref(false)
const mcpUrl = `${window.location.origin}/mcp`
const addCmd = computed(() => `claude mcp add --scope user --transport http reportzene ${mcpUrl} --header "Authorization: Bearer ${created.value || '<token>'}"`)

async function load() {
  tokens.value = (await api.get<Token[]>('/auth/tokens')).data
}
watch(open, (v) => {
  if (v) {
    created.value = ''
    load()
  }
})

async function create() {
  busy.value = true
  try {
    created.value = (await api.post<Token & { token: string }>('/auth/tokens', { name: name.value.trim() || 'Agent' })).data.token
    await load()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    busy.value = false
  }
}
async function revoke(t: Token) {
  try {
    await ElMessageBox.confirm(`The agent using token "${t.name}" will lose access immediately.`, 'Delete token?', { type: 'warning', confirmButtonText: 'Delete', cancelButtonText: 'Cancel' })
    await api.del(`/auth/tokens/${t.id}`)
    await load()
  } catch (e) {
    if (e instanceof Error) ElMessage.error(e.message)
  }
}
async function copy(text: string) {
  if (await copyText(text)) ElMessage.success('Copied')
  else ElMessage.warning('Could not copy, select the text and copy it manually')
}
</script>

<template>
  <el-dialog v-model="open" title="Agent tokens (MCP)" width="min(680px, 94vw)">
    <p class="m-0 mb-3 text-sm text-slate-600">
      AI agents (Claude, GoClaw…) use this token to read the ZenE reports through MCP <b>under your name</b>, read-only. A token is shown only once; deleting it removes the agent's access immediately.
    </p>
    <div class="mb-3 flex gap-2">
      <el-input v-model="name" maxlength="80" placeholder="Token name, e.g. Claude Code" class="flex-1" />
      <el-button type="primary" :loading="busy" @click="create">Create token</el-button>
    </div>

    <el-alert v-if="created" type="success" :closable="false" show-icon title="New token, shown only this once" class="!mb-3">
      <div class="mt-1 flex items-center gap-2"><code class="break-all font-bold">{{ created }}</code><el-button size="small" @click="copy(created)">Copy</el-button></div>
    </el-alert>

    <el-descriptions :column="1" border size="small" class="mb-3">
      <el-descriptions-item label="MCP URL"><code>{{ mcpUrl }}</code></el-descriptions-item>
      <el-descriptions-item label="Claude Code">
        <code class="break-all text-xs">{{ addCmd }}</code> <el-button link type="primary" size="small" @click="copy(addCmd)">Copy</el-button>
      </el-descriptions-item>
      <el-descriptions-item label="Tools"><code class="text-xs">etsy_totals · etsy_report · filter_options · list_sheets · read_sheet · sync_sheet · whoami</code></el-descriptions-item>
    </el-descriptions>

    <el-table :data="tokens" size="small" empty-text="No tokens yet">
      <el-table-column label="Name" prop="name" min-width="140" />
      <el-table-column label="Token" width="120"><template #default="{ row }"><code>{{ row.hint }}…</code></template></el-table-column>
      <el-table-column label="Created" width="130"><template #default="{ row }">{{ dateTime(row.created_at) }}</template></el-table-column>
      <el-table-column label="Last used" width="130"><template #default="{ row }">{{ dateTime(row.last_used_at) }}</template></el-table-column>
      <el-table-column width="70" align="right"><template #default="{ row }"><el-button size="small" type="danger" link @click="revoke(row as Token)">Delete</el-button></template></el-table-column>
    </el-table>
  </el-dialog>
</template>
