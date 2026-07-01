<template>
  <div class="auth-container">
    <div class="auth-card">
      <h1 class="auth-title">找回密码</h1>
      <p class="auth-subtitle">输入邮箱，系统会发送重置链接</p>

      <n-form ref="formRef" :model="form" :rules="rules" size="large">
        <n-form-item path="email" label="邮箱">
          <n-input v-model:value="form.email" placeholder="请输入注册邮箱" @keyup.enter="handleSubmit" />
        </n-form-item>

        <n-button
          type="primary"
          block
          :loading="loading"
          @click="handleSubmit"
          class="submit-btn"
        >
          发送重置邮件
        </n-button>
      </n-form>

      <p v-if="sentMessage" class="result-text">{{ sentMessage }}</p>

      <p class="auth-switch">
        想起来了？
        <router-link to="/login">返回登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, useMessage } from 'naive-ui'
import type { FormRules } from 'naive-ui'
import { forgotPassword } from '../api/auth'

const message = useMessage()
const formRef = ref<InstanceType<typeof NForm> | null>(null)
const form = ref({ email: '' })
const loading = ref(false)
const sentMessage = ref('')

const rules: FormRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

async function handleSubmit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    const res = await forgotPassword(form.value.email)
    sentMessage.value = res.message
    message.success(res.message)
  } catch (err: any) {
    message.error(err.response?.data?.detail || '发送失败')
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
  font-size: 28px;
  color: #333;
  margin: 0 0 4px;
}
.auth-subtitle {
  text-align: center;
  color: #999;
  margin: 0 0 32px;
  font-size: 14px;
}
.submit-btn { margin-top: 8px; }
.result-text {
  margin: 16px 0 0;
  color: #18a058;
  font-size: 13px;
  text-align: center;
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
