<template>
  <div class="auth-container">
    <div class="auth-card">
      <h1 class="auth-title">重置密码</h1>
      <p class="auth-subtitle">设置新密码后，需要重新登录</p>

      <n-alert v-if="!token" type="error" class="alert">
        重置链接缺少 token，请重新发起找回密码。
      </n-alert>

      <n-form ref="formRef" :model="form" :rules="rules" size="large">
        <n-form-item path="password" label="新密码">
          <n-input
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            placeholder="至少 6 位"
          />
        </n-form-item>
        <n-form-item path="confirmPassword" label="确认新密码">
          <n-input
            v-model:value="form.confirmPassword"
            type="password"
            show-password-on="click"
            placeholder="再输一次新密码"
            @keyup.enter="handleSubmit"
          />
        </n-form-item>

        <n-button
          type="primary"
          block
          :disabled="!token"
          :loading="loading"
          @click="handleSubmit"
          class="submit-btn"
        >
          重置密码
        </n-button>
      </n-form>

      <p class="auth-switch">
        <router-link to="/login">返回登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NForm, NFormItem, NInput, useMessage } from 'naive-ui'
import type { FormRules } from 'naive-ui'
import { resetPassword } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()
const formRef = ref<InstanceType<typeof NForm> | null>(null)
const form = ref({ password: '', confirmPassword: '' })
const loading = ref(false)
const token = computed(() => String(route.query.token || ''))

const rules: FormRules = {
  password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '新密码至少 6 位', trigger: 'blur' },
    { max: 72, message: '新密码不能超过72个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再输入一次新密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string) => {
        if (value !== form.value.password) return new Error('两次密码不一致')
        return true
      },
      trigger: 'blur',
    },
  ],
}

async function handleSubmit() {
  if (!token.value) return
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const res = await resetPassword(token.value, form.value.password)
    authStore.logout()
    message.success(res.message)
    router.push('/login')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '重置失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 24px;
  background: radial-gradient(circle at 30% 12%, #f6ece0, var(--color-bg-page) 60%);
}
.auth-card {
  width: 400px;
  max-width: 100%;
  padding: 40px;
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.auth-title {
  text-align: center;
  font: 600 30px var(--font-serif);
  color: var(--color-primary);
  margin: 0 0 4px;
}
.auth-subtitle {
  text-align: center;
  color: var(--color-text-secondary);
  margin: 0 0 32px;
  font-size: 14px;
}
.alert { margin-bottom: 16px; }
.submit-btn { margin-top: 8px; }
.auth-switch {
  text-align: center;
  margin-top: 20px;
  color: #999;
  font-size: 14px;
}
.auth-switch a {
  color: var(--color-primary);
  text-decoration: none;
}
</style>
