<template>
  <div class="auth-container">
    <div class="auth-card">
      <h1 class="auth-title">EMIYA</h1>
      <p class="auth-subtitle">AI 情感陪伴</p>

      <n-form ref="formRef" :model="form" :rules="rules" size="large">
        <n-form-item path="email" label="邮箱">
          <n-input v-model:value="form.email" placeholder="请输入邮箱" />
        </n-form-item>

        <n-form-item path="password" label="密码">
          <n-input
            v-model:value="form.password"
            type="password"
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </n-form-item>

        <n-button
          type="primary"
          block
          :loading="loading"
          @click="handleLogin"
          class="submit-btn"
        >
          登录
        </n-button>
      </n-form>

      <p class="auth-switch">
        还没有账号？
        <router-link to="/register">去注册</router-link>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, useMessage } from 'naive-ui'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()

const formRef = ref<InstanceType<typeof NForm> | null>(null)
const form = ref({
  email: '',
  password: '',
})
const loading = ref(false)

const rules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
    { max: 72, message: '密码不能超过72个字符', trigger: 'blur' },
  ],
}

async function handleLogin() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await authStore.login(form.value)
    message.success('登录成功')
    router.push('/chat')
  } catch (err: any) {
    const detail = err.response?.data?.detail || '登录失败'
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
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.auth-card {
  width: 400px;
  padding: 40px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
}
.auth-title {
  text-align: center;
  font-size: 32px;
  color: #333;
  margin: 0 0 4px;
}
.auth-subtitle {
  text-align: center;
  color: #999;
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
  color: #667eea;
  text-decoration: none;
}
</style>
