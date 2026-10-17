<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../lib/api'
import { auth } from '../lib/auth'

type AuthConfig = { pod_enabled: boolean; password_enabled: boolean }

const route = useRoute()
const router = useRouter()
const config = ref<AuthConfig | null>(null)
const showPassword = ref(false)
const form = reactive({ email: '', password: '' })
const loading = ref(false)

const next = computed(() => (typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/etsy/report'))
const podHref = computed(() => `/api/v1/auth/pod/login?next=${encodeURIComponent(next.value)}`)
const error = computed(() => (typeof route.query.error === 'string' ? route.query.error : ''))

onMounted(async () => {
  try {
    config.value = (await api.get<AuthConfig>('/auth/config')).data
  } catch {
    config.value = { pod_enabled: false, password_enabled: true }
  }
  showPassword.value = !config.value.pod_enabled && config.value.password_enabled
})

async function submit() {
  if (!form.email || !form.password) return ElMessage.warning('Enter your email and password')
  loading.value = true
  try {
    await auth.login(form.email, form.password)
    router.push(next.value)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex min-h-full items-center justify-center px-4">
    <div class="page-card w-full max-w-sm">
      <div class="mb-6 flex items-center gap-3">
        <img src="/favicon.svg" class="h-10 w-10" alt="" />
        <div>
          <h1 class="m-0 text-lg font-bold text-slate-900">ReportZenE</h1>
          <p class="m-0 text-xs text-slate-500">Check trademark / copyright cho listing</p>
        </div>
      </div>

      <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon class="!mb-4" />

      <template v-if="config?.pod_enabled">
        <a :href="podHref" class="block no-underline">
          <el-button type="primary" size="large" class="w-full">Sign in with Isuccess System</el-button>
        </a>
        <p class="m-0 mt-2 text-xs leading-relaxed text-slate-500">
          You will be redirected to Isuccess System to sign in, then click <b>Allow</b> to come back. Your first sign-in creates a Member account.
        </p>
        <el-divider v-if="config.password_enabled" class="!my-5">
          <el-button link size="small" @click="showPassword = !showPassword">{{ showPassword ? 'Hide' : 'Sign in with password (admin)' }}</el-button>
        </el-divider>
      </template>

      <el-form v-if="showPassword" label-position="top" @submit.prevent="submit">
        <el-form-item label="Email"><el-input v-model="form.email" autocomplete="username" /></el-form-item>
        <el-form-item label="Password"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" /></el-form-item>
        <el-button :type="config?.pod_enabled ? 'default' : 'primary'" native-type="submit" class="w-full" :loading="loading">Sign in</el-button>
      </el-form>

      <el-alert v-if="config && !config.pod_enabled && !config.password_enabled" type="warning" :closable="false" title="No sign-in method is enabled. Contact an admin." />
    </div>
  </div>
</template>
