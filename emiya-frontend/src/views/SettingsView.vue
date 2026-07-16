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

          <n-divider />

          <div class="section">
            <n-form-item label="新对话默认开启情感分析">
              <n-switch
                v-model:value="defaultAnalyzeEmotion"
                :loading="savingPerceptionDefault"
                @update:value="savePerceptionDefault"
              />
            </n-form-item>
            <p class="hint">
              情感分析（感知系统）会在每轮回复后额外调用一次 LLM，产出情绪 emoji 与好感度变化。
              这里只设 <b>新建对话</b> 的默认值：关闭后新对话默认不开启，你仍可在每个对话的设置里单独开启；
              已存在的对话不受影响。详见 ADR-0020。
            </p>
          </div>

          <n-divider />

          <div class="section">
            <n-form-item label="MVU 兼容">
              <n-switch
                v-model:value="mvuCompatEnabled"
                :loading="savingMvuCompat"
                @update:value="saveMvuCompat"
              />
            </n-form-item>
            <p class="hint">
              开启（默认）时，识别为 MVU 的角色卡在聊天中启用变量状态追踪与卡界面（如飞讯）。
              关闭后 <b>聊天时</b> 把 MVU 卡当普通卡：不追踪状态、不显示卡界面、不注入 MVU 世界书条目。
              仅影响聊天，导入/导出/识别不受影响；模板强制输出（非 MVU 卡的世界书模板）也不受影响。详见 CARD-0002。
            </p>
          </div>

          <n-divider />

          <div class="section">
            <n-form-item label="AI 输出格式识别">
              <n-switch
                v-model:value="outputContractLlmDetectionEnabled"
                :loading="savingOutputContractDetection"
                @update:value="saveOutputContractDetectionEnabled"
              />
            </n-form-item>
            <n-collapse v-if="outputContractLlmDetectionEnabled" class="advanced-collapse">
              <n-collapse-item title="高级设置" name="adv">
                <n-form-item label="每次最多检测条数">
                  <n-input-number
                    v-model:value="outputContractLlmDetectionLimit"
                    :min="0"
                    :max="200"
                    :step="5"
                    style="width: 180px"
                    @blur="saveOutputContractDetectionLimit"
                  />
                </n-form-item>
              </n-collapse-item>
            </n-collapse>
            <p class="hint">
              开启后，导入或编辑世界书时会让 AI 尝试识别“状态栏、Markdown 表格、JSON 块、章节/选项/后台日志”等输出格式要求，
              并保存到条目里供聊天时使用。检测条数越大，覆盖越全面，但导入等待时间和模型调用次数也会增加。
              自动识别没命中的条目，仍可在世界书编辑页对单条 entry 手动执行 AI 识别。
            </p>
          </div>

          <n-divider />

          <div class="section">
            <h3 class="section-title">可见输出格式执行（新对话默认）</h3>
            <n-form-item label="默认执行模式">
              <n-select
                v-model:value="outputContractDefaultMode"
                :options="outputContractModeOptions"
                :loading="savingOutputContractExec"
                style="width: 240px"
                @update:value="saveOutputContractDefaultMode"
              />
            </n-form-item>
            <n-collapse v-if="outputContractDefaultMode !== 'off'" class="advanced-collapse">
              <n-collapse-item title="高级设置" name="adv">
                <n-form-item label="允许整篇 rewrite 兜底">
                  <n-switch
                    v-model:value="outputContractAllowFullRewrite"
                    :loading="savingOutputContractExec"
                    @update:value="saveOutputContractAllowFullRewrite"
                  />
                </n-form-item>
                <n-form-item label="strict 不可用时降级">
                  <n-select
                    v-model:value="outputContractStrictFallback"
                    :options="outputContractFallbackOptions"
                    :loading="savingOutputContractExec"
                    style="width: 200px"
                    @update:value="saveOutputContractStrictFallback"
                  />
                </n-form-item>
                <n-form-item label="严格声明模式默认">
                  <n-select
                    v-model:value="outputContractRequireConfirmed"
                    :options="outputContractRequireConfirmedOptions"
                    :loading="savingOutputContractExec"
                    style="width: 200px"
                    @update:value="saveOutputContractRequireConfirmed"
                  />
                </n-form-item>
                <p class="hint">
                  严格声明模式（ADR-2c）：开启后聊天只<strong>执行</strong>已确认 / 声明的契约，
                  未确认的自动识别草稿仅作 Prompt 引导。“跟随全局默认”时用部署级默认（通常关）。
                  单个对话仍可在对话设置里覆盖。
                </p>
              </n-collapse-item>
            </n-collapse>
            <p class="hint">
              该设置决定<strong>聊天时</strong>如何处理世界书要求的可见输出格式，与上面的“导入期识别”是两回事。
              <br />· <strong>auto</strong>（默认）：状态栏尾部块自动补写；整篇结构只注入约束并诊断，不自动改写回复。
              <br />· <strong>guide</strong>：只注入约束 + 诊断；<strong>repair</strong>：额外做确定性修复与缺失槽位补写；
              <strong>strict</strong>：由代码分阶段生成并确定性渲染结构（延迟与 token 消耗更高，原始草稿不流式显示）。
              <br />这些只保证已列出的结构规则，不承诺剧情质量。整篇 rewrite 为独立许可，默认关闭。
            </p>
          </div>

          <n-divider />

          <div class="section">
            <h3 class="section-title">全局 CSS 主题</h3>
            <p class="hint">
              这里写的 CSS 对所有对话生效；角色卡自带样式会在全局样式之后注入，因此可以覆盖这里的规则。
            </p>
            <n-input
              v-model:value="cssTheme"
              type="textarea"
              :autosize="{ minRows: 12, maxRows: 24 }"
              placeholder="/* 示例：状态栏样式 */"
              class="css-input"
            />
            <div class="actions">
              <n-button :disabled="!hasCssTheme" @click="clearCssTheme">清空主题</n-button>
              <n-button type="primary" :loading="savingCssTheme" @click="saveCssTheme">
                保存主题
              </n-button>
            </div>
          </div>
        </n-tab-pane>

        <!-- ───── Tab: 记忆 / 预算（ADR-4）───── -->
        <n-tab-pane name="advanced" tab="记忆 / 预算">
          <div class="section">
            <n-form-item label="记忆系统">
              <n-switch
                :value="memoryEnabled"
                :loading="savingAccount"
                @update:value="onMemoryEnabled"
              />
              <span class="switch-hint">
                总开关：关闭后本账户所有对话都不检索、不提取长期记忆（与对话内“记忆”注入块正交）。
              </span>
            </n-form-item>
            <n-collapse v-if="memoryEnabled" class="advanced-collapse">
              <n-collapse-item title="高级设置" name="adv">
                <n-form-item label="提取频率">
                  <n-select
                    :value="memoryCadence"
                    :options="EXTRACTION_CADENCE_OPTIONS"
                    :loading="savingAccount"
                    style="width: 160px"
                    @update:value="onCadence"
                  />
                </n-form-item>
                <n-form-item label="Query 改写">
                  <n-switch :value="memoryQueryRewriting" :loading="savingAccount" @update:value="onQueryRewriting" />
                </n-form-item>
                <n-form-item label="矛盾检测">
                  <n-switch :value="memoryContradiction" :loading="savingAccount" @update:value="onContradiction" />
                </n-form-item>
                <n-form-item v-for="knob in MEMORY_ADVANCED_KNOBS" :key="knob.key" :label="knob.label">
                  <n-input-number
                    :value="accountConfig[knob.key] ?? null"
                    :min="knob.min"
                    :max="knob.max"
                    :step="knob.step"
                    :placeholder="knob.placeholder"
                    clearable
                    style="width: 180px"
                    @update:value="(v) => onKnobChange(knob.key, v)"
                  />
                </n-form-item>
                <div class="actions">
                  <n-button size="small" :loading="savingAccount" @click="resetMemoryAdvanced">
                    复位为全局默认
                  </n-button>
                </div>
                <p class="hint">
                  专家旋钮：阈值 / 权重设置不当会降低记忆召回质量。留空 = 跟随全局默认（后端会钳制到安全区间）。
                </p>
              </n-collapse-item>
            </n-collapse>
          </div>

          <n-divider />

          <div class="section">
            <h3 class="section-title">上下文 / Token 预算默认（新对话继承）</h3>
            <n-form-item v-for="knob in BUDGET_ACCOUNT_KNOBS" :key="knob.key" :label="knob.label">
              <n-input-number
                :value="accountConfig[knob.key] ?? null"
                :min="knob.min"
                :max="knob.max"
                :step="knob.step"
                :placeholder="knob.placeholder"
                clearable
                style="width: 200px"
                @update:value="(v) => onKnobChange(knob.key, v)"
              />
            </n-form-item>
            <p class="hint">
              “上下文总上限”= 单轮请求的总 token 天花板（input + 输出共享），预算规划器把它切成
              历史 / 世界书 / 输出 / 安全余量；“滑窗大小”则是按<strong>消息条数</strong>保留多少条最近对话，两者单位不同。
              账户级默认垫在对话覆盖之下：某对话若单独调了预算，以对话设置为准。留空 = 跟随全局默认。
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
              修改成功后会退出所有登录设备，并要求重新登录。
            </p>
          </div>

          <n-divider />

          <div class="section">
            <h3 class="section-title">退出当前登录</h3>
            <p class="hint">撤销当前设备的登录状态，并返回登录页。</p>
            <div class="actions">
              <n-button :loading="loggingOutCurrent" @click="logoutCurrent">
                退出当前登录
              </n-button>
            </div>
          </div>
        </n-tab-pane>

        <!-- ───── Tab 4: 登录设备 ───── -->
        <n-tab-pane name="sessions" tab="登录设备">
          <div class="section">
            <div class="section-heading-row">
              <h3 class="section-title">当前可登录设备</h3>
              <n-button size="small" :loading="loadingSessions" @click="loadSessions">
                刷新
              </n-button>
            </div>
            <p class="hint">
              这里列出仍可访问账号的登录会话。你可以移除其他设备，或一次性退出所有其他设备。
            </p>
            <div class="actions">
              <n-button
                type="warning"
                :disabled="!hasOtherActiveSessions"
                :loading="revokingOthers"
                @click="revokeOthers"
              >
                退出所有其他设备
              </n-button>
            </div>

            <div class="session-list">
              <div v-for="s in sessions" :key="s.id" class="session-item">
                <div class="session-main">
                  <div class="session-title">
                    <span>{{ s.device_label }}</span>
                    <n-tag v-if="s.is_current" size="small" type="success">当前设备</n-tag>
                    <n-tag v-else-if="s.status === 'revoked'" size="small" type="default">已撤销</n-tag>
                    <n-tag v-else-if="s.status === 'expired'" size="small" type="warning">已过期</n-tag>
                  </div>
                  <div class="session-meta">
                    <span>IP：{{ s.ip_address || '未知' }}</span>
                    <span>登录：{{ formatDate(s.created_at) }}</span>
                    <span>最近活跃：{{ formatDate(s.last_seen_at) }}</span>
                    <span>过期：{{ formatDate(s.expires_at) }}</span>
                  </div>
                </div>
                <n-button
                  v-if="!s.is_current && s.status === 'active'"
                  size="small"
                  type="error"
                  tertiary
                  :loading="revokingSessionId === s.id"
                  @click="revokeSession(s.id)"
                >
                  移除
                </n-button>
              </div>
              <p v-if="!loadingSessions && sessions.length === 0" class="hint">
                暂无登录设备记录。
              </p>
            </div>
          </div>
        </n-tab-pane>

        <!-- ───── Tab 5: 危险区 ───── -->
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
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NCollapse, NCollapseItem, NDivider, NForm, NFormItem, NIcon, NInput,
  NInputNumber, NSelect, NSwitch, NTabPane, NTag, NTabs, NUpload, useDialog, useMessage,
} from 'naive-ui'
import {
  boolFromInherit, boolToInherit,
  MEMORY_ADVANCED_KNOBS, BUDGET_ACCOUNT_KNOBS, EXTRACTION_CADENCE_OPTIONS,
} from '../config/configSchema'
import type { AccountConfig } from '../types'
import {
  isHtmlIframeRenderEnabled, setHtmlIframeRenderEnabled,
} from '../composables/useHtmlIframeRender'
import type { UploadCustomRequestOptions } from 'naive-ui'
import { ArrowBackOutline } from '@vicons/ionicons5'
import { useAuthStore } from '../stores/auth'
import {
  uploadAvatar,
  changePassword,
  deleteMyAccount,
  fetchUserSessions,
  revokeCurrentSession,
  revokeOtherSessions,
  revokeUserSession,
} from '../api/user'
import { avatarColor } from '../utils/avatar'
import PageShell from '../components/layout/PageShell.vue'
import type { UserSession } from '../types'

const router = useRouter()
const authStore = useAuthStore()
const message = useMessage()
const dialog = useDialog()

const user = computed(() => authStore.user)
const avatarUrl = computed(() => user.value?.avatar_url || null)

// ── 显示偏好 ──
const renderHtmlIframe = ref(isHtmlIframeRenderEnabled())
const cssTheme = ref(user.value?.css_theme || '')
const savingCssTheme = ref(false)
const hasCssTheme = computed(() => !!cssTheme.value.trim())

// 情感分析默认偏好（ADR-0020）：仅影响新建对话的默认开关，改动即时保存
const defaultAnalyzeEmotion = ref(user.value?.default_analyze_emotion ?? false)
const savingPerceptionDefault = ref(false)

async function savePerceptionDefault(v: boolean) {
  savingPerceptionDefault.value = true
  try {
    await authStore.updateMe({ default_analyze_emotion: v })
    message.success(v ? '新对话将默认开启情感分析' : '新对话将默认关闭情感分析')
  } catch (err: any) {
    defaultAnalyzeEmotion.value = !v
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingPerceptionDefault.value = false
  }
}

// MVU 兼容总开关（CARD-0002）：仅影响聊天时，改动即时保存
const mvuCompatEnabled = ref(user.value?.mvu_compat_enabled ?? true)
const savingMvuCompat = ref(false)

async function saveMvuCompat(v: boolean) {
  savingMvuCompat.value = true
  try {
    await authStore.updateMe({ mvu_compat_enabled: v })
    message.success(v ? '已开启 MVU 兼容' : '聊天时将把 MVU 卡当普通卡')
  } catch (err: any) {
    mvuCompatEnabled.value = !v
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingMvuCompat.value = false
  }
}

// 世界书输出契约 LLM 自动识别：仅影响导入/编辑期，手动单条识别不受此开关限制
const outputContractLlmDetectionEnabled = ref(user.value?.output_contract_llm_detection_enabled ?? false)
const outputContractLlmDetectionLimit = ref(user.value?.output_contract_llm_detection_limit ?? 30)
const savingOutputContractDetection = ref(false)

async function saveOutputContractDetectionEnabled(v: boolean) {
  savingOutputContractDetection.value = true
  try {
    await authStore.updateMe({ output_contract_llm_detection_enabled: v })
    message.success(v ? '导入世界书时将自动识别输出格式' : '已关闭导入时 AI 输出格式识别')
  } catch (err: any) {
    outputContractLlmDetectionEnabled.value = !v
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingOutputContractDetection.value = false
  }
}

async function saveOutputContractDetectionLimit() {
  const limit = Math.max(0, Math.min(200, Number(outputContractLlmDetectionLimit.value || 0)))
  outputContractLlmDetectionLimit.value = limit
  savingOutputContractDetection.value = true
  try {
    await authStore.updateMe({ output_contract_llm_detection_limit: limit })
    message.success(`每次最多检测 ${limit} 条候选条目`)
  } catch (err: any) {
    outputContractLlmDetectionLimit.value = user.value?.output_contract_llm_detection_limit ?? 30
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingOutputContractDetection.value = false
  }
}

// 可见输出格式聊天期执行默认（ADR-1f）：新对话继承，单个对话可在配置面板覆盖。
const outputContractDefaultMode = ref(user.value?.output_contract_default_mode ?? 'auto')
const outputContractAllowFullRewrite = ref(user.value?.output_contract_allow_full_rewrite ?? false)
const outputContractStrictFallback = ref(user.value?.output_contract_strict_fallback ?? 'repair')
// 严格声明模式账户默认：可空三态，null=跟随全局默认。UI 用 boolFromInherit 映射到 inherit/yes/no。
const outputContractRequireConfirmed = ref<string>(
  boolFromInherit(user.value?.output_contract_require_confirmed)
)
const savingOutputContractExec = ref(false)
const outputContractModeOptions = [
  { label: 'auto（按类型自动）', value: 'auto' },
  { label: 'off（关闭）', value: 'off' },
  { label: 'guide（只约束+诊断）', value: 'guide' },
  { label: 'repair（修复+补写）', value: 'repair' },
  { label: 'strict（结构化生成）', value: 'strict' },
]
const outputContractFallbackOptions = [
  { label: 'repair', value: 'repair' },
  { label: 'guide', value: 'guide' },
  { label: 'off', value: 'off' },
]
// 账户级严格声明模式：inherit=跟随全局默认（区别于对话级的“继承账户”）。
const outputContractRequireConfirmedOptions = [
  { label: '跟随全局默认', value: 'inherit' },
  { label: '开启', value: 'yes' },
  { label: '关闭', value: 'no' },
]

async function saveOutputContractDefaultMode(v: string) {
  savingOutputContractExec.value = true
  try {
    await authStore.updateMe({ output_contract_default_mode: v })
    message.success(`新对话默认执行模式：${v}`)
  } catch (err: any) {
    outputContractDefaultMode.value = user.value?.output_contract_default_mode ?? 'auto'
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingOutputContractExec.value = false
  }
}

async function saveOutputContractAllowFullRewrite(v: boolean) {
  savingOutputContractExec.value = true
  try {
    await authStore.updateMe({ output_contract_allow_full_rewrite: v })
    message.success(v ? '已允许整篇 rewrite 兜底' : '已关闭整篇 rewrite 兜底')
  } catch (err: any) {
    outputContractAllowFullRewrite.value = !v
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingOutputContractExec.value = false
  }
}

async function saveOutputContractStrictFallback(v: string) {
  savingOutputContractExec.value = true
  try {
    await authStore.updateMe({ output_contract_strict_fallback: v })
    message.success(`strict 不可用时降级为：${v}`)
  } catch (err: any) {
    outputContractStrictFallback.value = user.value?.output_contract_strict_fallback ?? 'repair'
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingOutputContractExec.value = false
  }
}

async function saveOutputContractRequireConfirmed(v: string) {
  savingOutputContractExec.value = true
  try {
    // boolToInherit: inherit→null（清空账户表态，回退全局）、yes→true、no→false
    await authStore.updateMe({ output_contract_require_confirmed: boolToInherit(v) })
    message.success(
      v === 'inherit' ? '严格声明模式：跟随全局默认'
        : v === 'yes' ? '新对话默认开启严格声明模式' : '新对话默认关闭严格声明模式'
    )
  } catch (err: any) {
    outputContractRequireConfirmed.value = boolFromInherit(user.value?.output_contract_require_confirmed)
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingOutputContractExec.value = false
  }
}

// ── 账户级配置桶（ADR-4）：记忆系统 + token 预算账户默认，增量保存 ──
const accountConfig = ref<AccountConfig>({ ...(user.value?.account_config || {}) })
const savingAccount = ref(false)

async function saveAccountConfig(
  patch: Record<string, number | boolean | string | null>,
) {
  savingAccount.value = true
  try {
    await authStore.updateMe({ account_config: patch })
    // updateMe 已把合并/钳制后的 user 写回 store；同步本地视图。
    accountConfig.value = { ...(user.value?.account_config || {}) }
  } catch (err: any) {
    accountConfig.value = { ...(user.value?.account_config || {}) }
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingAccount.value = false
  }
}

// getter：未设账户值时用 UI 默认显示（真正的“继承全局”在后端解析）。
const memoryEnabled = computed(() => accountConfig.value.memory_enabled ?? true)
const memoryCadence = computed(() => accountConfig.value.memory_extraction_cadence ?? 'standard')
const memoryQueryRewriting = computed(() => accountConfig.value.memory_query_rewriting ?? true)
const memoryContradiction = computed(() => accountConfig.value.memory_contradiction_detection ?? true)

function onMemoryEnabled(v: boolean) { saveAccountConfig({ memory_enabled: v }) }
function onCadence(v: string) { saveAccountConfig({ memory_extraction_cadence: v }) }
function onQueryRewriting(v: boolean) { saveAccountConfig({ memory_query_rewriting: v }) }
function onContradiction(v: boolean) { saveAccountConfig({ memory_contradiction_detection: v }) }
// 数字旋钮：null（清空）= 回退全局；否则存账户值（后端钳制）。
function onKnobChange(key: string, v: number | null) { saveAccountConfig({ [key]: v }) }

async function resetMemoryAdvanced() {
  const patch: Record<string, null> = {
    memory_extraction_cadence: null,
    memory_query_rewriting: null,
    memory_contradiction_detection: null,
  }
  for (const k of MEMORY_ADVANCED_KNOBS) patch[k.key] = null
  await saveAccountConfig(patch)
  message.success('记忆高级设置已复位为全局默认')
}

function onRenderHtmlIframeChange(v: boolean) {
  setHtmlIframeRenderEnabled(v)
  message.success(v ? '已开启前端代码块渲染' : '已关闭前端代码块渲染')
}

async function saveCssTheme() {
  savingCssTheme.value = true
  try {
    await authStore.updateMe({ css_theme: cssTheme.value })
    message.success('全局 CSS 主题已保存')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    savingCssTheme.value = false
  }
}

async function clearCssTheme() {
  savingCssTheme.value = true
  try {
    await authStore.updateMe({ css_theme: '' })
    cssTheme.value = ''
    message.success('全局 CSS 主题已清空')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '清空失败')
  } finally {
    savingCssTheme.value = false
  }
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
    message.success('密码已修改，请重新登录')
    passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
    authStore.logout()
    router.push('/login')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '修改失败')
  } finally {
    changingPassword.value = false
  }
}

// ── 登录设备 ──
const sessions = ref<UserSession[]>([])
const loadingSessions = ref(false)
const revokingSessionId = ref<string | null>(null)
const revokingOthers = ref(false)
const loggingOutCurrent = ref(false)

const hasOtherActiveSessions = computed(() =>
  sessions.value.some(s => !s.is_current && s.status === 'active')
)

function formatDate(s: string): string {
  return new Date(s).toLocaleString()
}

async function loadSessions() {
  loadingSessions.value = true
  try {
    sessions.value = await fetchUserSessions()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '加载登录设备失败')
  } finally {
    loadingSessions.value = false
  }
}

async function revokeSession(sessionId: string) {
  revokingSessionId.value = sessionId
  try {
    await revokeUserSession(sessionId)
    message.success('已移除该设备')
    await loadSessions()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '移除失败')
  } finally {
    revokingSessionId.value = null
  }
}

async function revokeOthers() {
  revokingOthers.value = true
  try {
    const res = await revokeOtherSessions()
    message.success(`已退出 ${res.revoked} 个其他设备`)
    await loadSessions()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '操作失败')
  } finally {
    revokingOthers.value = false
  }
}

async function logoutCurrent() {
  loggingOutCurrent.value = true
  try {
    await revokeCurrentSession()
  } catch {
    // 本地退出优先，服务端撤销失败时也清理当前浏览器登录态。
  } finally {
    authStore.logout()
    loggingOutCurrent.value = false
    router.push('/login')
  }
}

onMounted(loadSessions)

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
.advanced-collapse { margin: 4px 0 8px; }
.section-title { margin: 0 0 16px; font-size: 16px; }
.section-heading-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.actions { display: flex; justify-content: flex-end; gap: 12px; margin-top: 12px; }
.hint { color: var(--color-text-tertiary); font-size: 12px; margin: 8px 0 0; }
.css-input { margin-top: 12px; }
.css-input :deep(textarea) {
  font-family: 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
}

.avatar-row { display: flex; gap: 24px; align-items: center; }
.avatar-preview { width: 96px; height: 96px; border-radius: 50%; overflow: hidden; flex-shrink: 0; }
.avatar-img { width: 100%; height: 100%; object-fit: cover; }
.avatar-fallback {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 36px; font-weight: 600;
}
.avatar-controls { display: flex; flex-direction: column; gap: 8px; }

.session-list { display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }
.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border: 1px solid var(--color-border-light);
  border-radius: 8px;
  background: var(--color-bg-surface);
}
.session-main { min-width: 0; }
.session-title { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.session-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.danger-section { background: #fff5f5; border: 1px solid #ffd6d6; border-radius: 8px; padding: 20px; }
.danger-title { color: #d03050; }
.danger-desc { color: #555; font-size: 14px; margin: 12px 0; line-height: 1.7; }
.danger-list { color: #555; font-size: 14px; padding-left: 20px; line-height: 1.9; }
</style>
