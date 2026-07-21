<template>
  <div class="auth-container">
    <div class="auth-card">
      <h1 class="auth-title">创建账号</h1>
      <p class="auth-subtitle">开始你的 AI 陪伴之旅</p>

      <n-form ref="formRef" :model="form" :rules="rules" size="large">
        <n-form-item path="email" label="邮箱">
          <n-input v-model:value="form.email" placeholder="请输入邮箱" />
        </n-form-item>

        <n-form-item path="nickname" label="昵称">
          <n-input v-model:value="form.nickname" placeholder="请输入昵称" />
        </n-form-item>

        <n-form-item path="password" label="密码">
          <n-input
            v-model:value="form.password"
            type="password"
            placeholder="至少 6 位密码"
          />
        </n-form-item>

        <n-form-item path="confirmPassword" label="确认密码">
          <n-input
            v-model:value="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            @keyup.enter="handleRegister"
          />
        </n-form-item>

        <n-button
          type="primary"
          block
          :loading="loading"
          @click="handleRegister"
          class="submit-btn"
        >
          注册
        </n-button>
      </n-form>

      <p class="auth-switch">
        已有账号？
        <router-link to="/login">去登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, useMessage } from 'naive-ui'
import type { FormRules } from 'naive-ui'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()

const formRef = ref<InstanceType<typeof NForm> | null>(null)
const form = ref({
  email: '',
  nickname: '',
  password: '',
  confirmPassword: '',
})
const loading = ref(false)

const rules: FormRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 1, max: 50, message: '昵称 1-50 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
    { max: 72, message: '密码不能超过72个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string) => {
        if (value !== form.value.password) {
          return new Error('两次密码不一致')
        }
        return true
      },
      trigger: 'blur',
    },
  ],
}

async function handleRegister() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await authStore.register({
      email: form.value.email,
      password: form.value.password,
      nickname: form.value.nickname,
    })
    message.success('注册成功')
    router.push('/home')
  } catch (err: any) {
    const detail = err.response?.data?.detail || '注册失败'
    message.error(detail)
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
.submit-btn {
  margin-top: 8px;
}
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
