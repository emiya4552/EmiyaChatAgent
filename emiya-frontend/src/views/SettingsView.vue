<template>
  <PageShell max-width="720px">
    <div class="settings-page">
      <div class="page-header">
        <n-button text @click="router.back()">
          <template #icon><n-icon><ArrowBackOutline /></n-icon></template>
          返回
        </n-button>
        <h1 class="page-title">账户设置</h1>
      </div>

      <n-tabs type="line" animated>
        <!-- ───── Tab 1: 资料 ───── -->
        <n-tab-pane name="profile" tab="资料">
          <div class="section">
            <n-form-item label="邮箱">
              <n-input :value="user?.email || ''" disabled />
            </n-form-item>

            <n-form-item label="昵称">
              <n-input
                v-model:value="profileForm.nickname"
                placeholder="1-50 个字符"
                maxlength="50"
              />
            </n-form-item>

            <div class="actions">
              <n-button type="primary" :loading="savingProfile" @click="saveProfile">
                保存昵称
              </n-button>
            </div>
          </div>

          <n-divider />

          <div class="section">
            <h3 class="section-title">头像</h3>
            <div class="avatar-row">
              <div class="avatar-preview">
                <img
                  v-if="avatarUrl"
                  :src="avatarUrl"
                  alt="头像"
                  class="avatar-img"
                />
                <div
                  v-else
                  class="avatar-fallback"
                  :style="{ background: avatarColor(user?.nickname || '我') }"
                >
                  {{ (user?.nickname || '我').charAt(0) }}
                </div>
              </div>
              <div class="avatar-controls">
                <n-upload
                  :show-file-list="false"
                  accept="image/jpeg,image/png,image/webp"
                  :custom-request="handleAvatarUpload"
                >
                  <n-button :loading="uploadingAvatar">上传新头像</n-button>
                </n-upload>
                <p class="hint">支持 jpg / png / webp，单文件不超过 2 MB</p>
              </div>
            </div>
          </div>
        </n-tab-pane>

        <!-- ───── Tab 2: 显示偏好 ───── -->
        <n-tab-pane name="display" tab="显示偏好">
          <div class="section">
            <n-form-item label="渲染 LLM 输出的前端代码块">
              <n-switch v-model:value="renderHtmlIframe" @update:value="onRenderHtmlIframeChange" />
            </n-form-item>
            <p class="hint">
              开启后，AI 输出的 ```html 代码块若含完整 HTML 文档（带
              <code>&lt;html&gt;</code> / <code>&lt;body&gt;</code> 等标记），会被替换为
              样式隔离的 iframe 渲染 —— 卡作者写的状态栏 / 角色面板 / CSS 动画都能正常显示。
              关闭后退回原始代码块。详见 ADR-0012。
            </p>
          </div>
        </n-tab-pane>

        <!-- ───── Tab 3: 安全 ───── -->
        <n-tab-pane name="security" tab="安全">
          <div class="section">
            <h3 class="section-title">修改密码</h3>
            <n-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules">
              <n-form-item path="oldPassword" label="当前密码">
                <n-input
                  v-model:value="passwordForm.oldPassword"
                  type="password"
                  show-password-on="click"
                  placeholder="请输入当前密码"
                />
              </n-form-item>
              <n-form-item path="newPassword" label="新密码">
                <n-input
                  v-model:value="passwordForm.newPassword"
                  type="password"
                  show-password-on="click"
                  placeholder="至少 6 位"
                />
              </n-form-item>
              <n-form-item path="confirmPassword" label="确认新密码">
                <n-input
                  v-model:value="passwordForm.confirmPassword"
                  type="password"
                  show-password-on="click"
                  placeholder="再输一次新密码"
                />
              </n-form-item>
              <div class="actions">
                <n-button type="primary" :loading="changingPassword" @click="submitChangePassword">
                  修改密码
                </n-button>
              </div>
            </n-form>
            <p class="hint">
              提示：MVP 阶段修改密码不会强制旧登录会话失效，旧 token 自然过期。
            </p>
          </div>
        </n-tab-pane>

        <!-- ───── Tab 4: 危险区 ───── -->
        <n-tab-pane name="danger" tab="危险区">
          <div class="section danger-section">
            <h3 class="section-title danger-title">⚠ 注销账号</h3>
            <p class="danger-desc">
              注销后将
              <strong>永久删除</strong>
              该账号下的所有数据，包括：
            </p>
            <ul class="danger-list">
              <li>所有对话、消息记录、情绪记录</li>
              <li>所有自建/导入的角色卡、世界书、预设、模板、正则预设</li>
              <li>所有记忆向量与关系数据</li>
              <li>所有上传的头像文件</li>
            </ul>
            <p class="danger-desc">
              此操作<strong>不可恢复</strong>。
            </p>

            <n-form-item label="输入当前密码确认">
              <n-input
                v-model:value="deletePassword"
                type="password"
                show-password-on="click"
                placeholder="当前密码"
              />
            </n-form-item>
            <div class="actions">
              <n-button
                type="error"
                :disabled="!deletePassword"
                :loading="deletingAccount"
                @click="confirmDeleteAccount"
              >
                永久注销账号
              </n-button>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
    </div>
  </PageShell>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NDivider, NForm, NFormItem, NIcon, NInput, NSwitch,
  NTabPane, NTabs, NUpload, useDialog, useMessage,
} from 'naive-ui'
import {
  isHtmlIframeRenderEnabled, setHtmlIframeRenderEnabled,
} from '../composables/useHtmlIframeRender'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import { uploadAvatar, changePassword, deleteMyAccount } from '../api/user'
import { avatarColor } from '../utils/avatar'
import PageShell from '../components/layout/PageShell.vue'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const dialog = useDialog()

const user = computed(() => authStore.user)
const avatarUrl = computed(() => user.value?.avatar_url || null)

// ── 显示偏好 ──
const renderHtmlIframe = ref(isHtmlIframeRenderEnabled())
function onRenderHtmlIframeChange(v: boolean) {
  setHtmlIframeRenderEnabled(v)
  message.success(v ? '已开启前端代码块渲染' : '已关闭前端代码块渲染')
}

// ── 资料 ──
const profileForm = ref({
  nickname: user.value?.nickname || '',
})
const savingProfile = ref(false)
const uploadingAvatar = ref(false)

async function saveProfile() {
  const nickname = (profileForm.value.nickname || '').trim()
  if (!nickname) {
    message.error('昵称不能为空')
    return
  }
  if (nickname.length > 50) {
    message.error('昵称最多 50 个字符')
    return
  }
  savingProfile.value = true
  try {
    await authStore.updateMe({ nickname })
    message.success('昵称已保存')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingProfile.value = false
  }
}

async function handleAvatarUpload({ file, onFinish, onError }: UploadCustomRequestOptions) {
  const raw = file.file
  if (!raw) {
    onError()
    return
  }
  if (raw.size > 2 * 1024 * 1024) {
    message.error('头像不能超过 2 MB')
    onError()
    return
  }
  uploadingAvatar.value = true
  try {
    const updated = await uploadAvatar(raw)
    authStore.user = updated
    localStorage.setItem('user', JSON.stringify(updated))
    message.success('头像已更新')
    onFinish()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '上传失败')
    onError()
  } finally {
    uploadingAvatar.value = false
  }
}

// ── 安全 ──
const passwordFormRef = ref<InstanceType<typeof NForm> | null>(null)
const passwordForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})
const changingPassword = ref(false)

const passwordRules = {
  oldPassword: [{ required: true, message: '请输入当前密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '新密码至少 6 位', trigger: 'blur' },
    { max: 72, message: '新密码不能超过 72 字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再输入一次新密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string) => {
        if (value !== passwordForm.value.newPassword) {
          return new Error('两次密码不一致')
        }
        return true
      },
      trigger: 'blur',
    },
  ],
}

async function submitChangePassword() {
  try {
    await passwordFormRef.value?.validate()
  } catch {
    return
  }
  changingPassword.value = true
  try {
    await changePassword(passwordForm.value.oldPassword, passwordForm.value.newPassword)
    message.success('密码已修改')
    passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
  } catch (err: any) {
    message.error(err.response?.data?.detail || '修改失败')
  } finally {
    changingPassword.value = false
  }
}

// ── 危险区 ──
const deletePassword = ref('')
const deletingAccount = ref(false)

function confirmDeleteAccount() {
  dialog.error({
    title: '确定要永久注销账号吗？',
    content:
      '此操作将立即删除你的全部数据，且不可恢复。请确认你已经导出了想保留的角色卡/世界书等资源。',
    positiveText: '永久注销',
    negativeText: '取消',
    onPositiveClick: doDeleteAccount,
  })
}

async function doDeleteAccount() {
  deletingAccount.value = true
  try {
    await deleteMyAccount(deletePassword.value)
    message.success('账号已注销')
    authStore.logout()
    router.push('/login')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '注销失败')
  } finally {
    deletingAccount.value = false
  }
}
</script>

<style scoped>
.settings-page { padding-bottom: 60px; }
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}
.page-title { margin: 0; font-size: 22px; }
.section { padding: 12px 4px; }
.section-title { margin: 0 0 16px; font-size: 16px; }
.actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 12px; }
.hint { color: var(--color-text-tertiary); font-size: 12px; margin: 8px 0 0; }

.avatar-row { display: flex; gap: 24px; align-items: center; }
.avatar-preview { width: 96px; height: 96px; border-radius: 50%; overflow: hidden; flex-shrink: 0; }
.avatar-img { width: 100%; height: 100%; object-fit: cover; }
.avatar-fallback {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 36px; font-weight: 600;
}
.avatar-controls { display: flex; flex-direction: column; gap: 8px; }

.danger-section { background: #fff5f5; border: 1px solid #ffd6d6; border-radius: 8px; padding: 20px; }
.danger-title { color: #d03050; }
.danger-desc { color: #555; font-size: 14px; margin: 12px 0; line-height: 1.7; }
.danger-list { color: #555; font-size: 14px; padding-left: 20px; line-height: 1.9; }
</style>
