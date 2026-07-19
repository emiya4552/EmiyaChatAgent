<!-- New frontend migration slice. Does not import legacy frontend code. -->
<template>
  <main class="next-app" :data-theme="theme">
    <nav class="main-nav" aria-label="主导航">
      <RouterLink v-for="item in mainNav" :key="item.id" :to="item.to" :class="{ active: mainActive === item.id }">{{ item.label }}</RouterLink>
      <button class="theme-button" type="button" :aria-label="theme === 'night' ? '切换至日间主题' : '切换至夜间主题'" @click="theme = theme === 'night' ? 'day' : 'night'">{{ theme === 'night' ? '☾ 月' : '☀ 日' }}</button>
    </nav>
    <nav v-if="subNav.length" class="sub-nav" aria-label="副导航">
      <RouterLink v-for="item in subNav" :key="item.to" :to="item.to" :class="{ active: isSubActive(item.to) }">{{ item.label }}</RouterLink>
    </nav>

    <section v-if="!token" class="auth-shell">
      <form class="auth-card" @submit.prevent="signIn">
        <p class="eyebrow">EMIYA NEXT · 迁移验证</p>
        <h1>登录新前端</h1>
        <p>认证仍使用现有后端接口；登录状态与旧前端隔离保存。</p>
        <label>邮箱<input v-model="email" autocomplete="email" type="email" required placeholder="name@example.com" /></label>
        <label>密码<input v-model="password" autocomplete="current-password" type="password" required placeholder="请输入密码" /></label>
        <button class="primary" :disabled="loading">{{ loading ? '正在登录…' : '登录' }}</button>
        <small v-if="error" class="error">{{ error }}</small>
      </form>
    </section>

    <section v-else class="workspace">
      <header class="page-heading">
        <div><p class="eyebrow">{{ pageKicker }}</p><h1>{{ pageTitle }}</h1><p>{{ pageDescription }}</p></div>
        <div class="identity"><b>{{ user?.nickname?.slice(0, 1) || '我' }}</b><span>{{ user?.nickname || user?.email }}<button type="button" @click="signOut">退出</button></span></div>
      </header>

      <template v-if="route.path === '/chat'">
        <div class="toolbar"><button class="primary" type="button" @click="openCreateDialog">新建对话</button><button class="secondary" type="button" @click="refreshConversations">刷新</button><small>{{ status }}</small></div>
        <RouterLink v-for="conversation in conversations" :key="conversation.id" :to="`/chat/${conversation.id}`" class="row-card conversation-row"><i>{{ conversation.persona_name?.slice(0, 1) || '角' }}</i><div><b>{{ conversation.title || '未命名对话' }}</b><small>{{ conversation.persona_name || '未指定角色' }} · {{ formatDate(conversation.updated_at) }}</small></div><span>进入对话 →</span></RouterLink>
        <p v-if="!loading && conversations.length === 0" class="empty">暂无会话。请选择一个角色来创建新对话。</p>
      </template>

      <template v-else-if="isChatDetail">
        <div class="chat-toolbar"><RouterLink class="back-link" to="/chat">← 所有对话</RouterLink><span>{{ activeConversation?.persona_name || '对话' }}</span><button class="secondary" type="button" @click="openConversationSettings">对话设置</button><button class="secondary" type="button" @click="refreshMessages">刷新消息</button></div>
        <section class="chat-panel">
          <div class="message-list" aria-live="polite">
            <p v-if="messagesLoading" class="empty">正在读取消息…</p>
            <p v-else-if="messages.length === 0" class="empty">这段对话尚未开始。发送第一条消息吧。</p>
            <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
              <span class="message-role">{{ roleLabel(message.role) }}</span>
              <p>{{ displayContent(message) }}</p>
            </article>
          </div>
          <form class="composer" @submit.prevent="sendMessage">
            <textarea v-model="draft" :disabled="streaming" maxlength="4000" placeholder="输入消息，Enter 换行，发送后会使用现有 SSE 接口生成回复。"></textarea>
            <div><label>回复长度<select v-model="replyLength" :disabled="streaming"><option value="short">短</option><option value="medium">中</option><option value="long">长</option></select></label><small v-if="streamStatus">{{ streamStatus }}</small><button v-if="streaming" class="secondary" type="button" @click="cancelStream">停止</button><button v-else class="primary" type="submit" :disabled="!draft.trim()">发送</button></div>
          </form>
        </section>
      </template>

      <template v-else-if="isPersonaEditor">
        <form class="editor-card" @submit.prevent="savePersona">
          <div class="chat-toolbar"><RouterLink class="back-link" to="/personas">← 所有角色</RouterLink><span>{{ personaEditingId ? '真实 API · PUT /v1/personas/:id' : '真实 API · POST /v1/personas' }}</span></div>
          <h2>{{ personaEditingId ? '编辑角色' : '创建角色' }}</h2>
          <div class="form-grid"><label>名称<input v-model="personaForm.name" required maxlength="100" placeholder="角色名称" /></label><label>标签（逗号分隔）<input v-model="personaForm.tags" placeholder="奇幻, 治愈, 日常" /></label></div>
          <label>性格<textarea v-model="personaForm.personality" required placeholder="角色的核心性格与说话方式"></textarea></label>
          <label>背景故事<textarea v-model="personaForm.background" placeholder="角色背景、经历和重要设定"></textarea></label>
          <label>当前情境<textarea v-model="personaForm.scenario" placeholder="当前故事发生的场景"></textarea></label>
          <label>开场白<textarea v-model="personaForm.first_message" placeholder="与用户开始对话时的第一句话"></textarea></label>
          <label>对话示例<textarea v-model="personaForm.mes_example" placeholder="示例对话"></textarea></label>
          <label>备用开场白（每行一条）<textarea v-model="personaForm.alternate_greetings" placeholder="第一条备用开场白&#10;第二条备用开场白"></textarea></label>
          <label>角色 CSS（可选）<textarea v-model="personaForm.css_theme" placeholder="仅保存到角色卡；应用逻辑会在后续主题迁移中接入"></textarea></label>
          <small v-if="personaError" class="error">{{ personaError }}</small>
          <div class="modal-actions"><RouterLink class="secondary button-link" to="/personas">取消</RouterLink><button class="primary" :disabled="personaSaving">{{ personaSaving ? '正在保存…' : '保存角色' }}</button></div>
        </form>
      </template>

      <template v-else-if="isPersonaDetail">
        <section v-if="personaLoading" class="empty">正在读取角色…</section>
        <section v-else-if="activePersona" class="persona-detail">
          <div class="chat-toolbar"><RouterLink class="back-link" to="/personas">← 所有角色</RouterLink><span>{{ activePersona.source === 'manual' ? '自定义角色' : '系统模板' }}</span><RouterLink v-if="!activePersona.is_template" class="secondary button-link" :to="`/personas/${activePersona.id}/edit`">编辑</RouterLink><button class="secondary" type="button" @click="downloadAuthenticated(`/v1/personas/${activePersona.id}/export?format=png`, `${activePersona.name}.png`)">导出 PNG</button><button class="primary" type="button" @click="startConversationFromPersona">用此角色对话</button></div>
          <header><i>{{ activePersona.name.slice(0, 1) }}</i><div><p class="eyebrow">角色卡</p><h2>{{ activePersona.name }}</h2><small>{{ activePersona.tags?.join(' · ') || '未分类' }}</small></div></header>
          <article v-for="section in personaSections" :key="section.label"><h3>{{ section.label }}</h3><p>{{ section.content || '未填写' }}</p></article>
          <article v-if="activePersona.alternate_greetings?.length"><h3>备用开场白</h3><p v-for="greeting in activePersona.alternate_greetings" :key="greeting">{{ greeting }}</p></article>
        </section>
        <section v-else class="empty">{{ personaError || '未找到该角色。' }}</section>
      </template>

      <template v-else-if="route.path === '/personas'">
        <div class="toolbar"><RouterLink class="primary button-link" to="/personas/create">创建角色</RouterLink><label class="secondary import-button">导入角色卡<input type="file" accept=".png,.json,image/png,application/json" @change="importPersonaFile" /></label><button class="secondary" type="button" @click="refreshPersonas">刷新</button><small>{{ status }}</small></div>
        <RouterLink v-for="persona in personas" :key="persona.id" :to="`/personas/${persona.id}`" class="row-card conversation-row"><i>{{ persona.name?.slice(0, 1) || '角' }}</i><div><b>{{ persona.name }}</b><small>{{ persona.personality || persona.tags?.join(' · ') || '角色卡' }}</small></div><span>{{ persona.is_owner ? '我的角色 →' : '模板 →' }}</span></RouterLink>
        <p v-if="!loading && personas.length === 0" class="empty">还没有可用角色卡。</p>
      </template>

      <template v-else-if="isWorldbookEditor">
        <form class="editor-card worldbook-editor" @submit.prevent="saveWorldbook">
          <div class="chat-toolbar"><RouterLink class="back-link" to="/worldbooks">← 所有世界书</RouterLink><span>{{ worldbookEditingId ? '真实 API · PUT /v1/worldbooks/:id' : '真实 API · POST /v1/worldbooks' }}</span></div>
          <h2>{{ worldbookEditingId ? '编辑世界书' : '创建世界书' }}</h2>
          <div class="form-grid"><label>名称<input v-model="worldbookForm.name" required maxlength="200" placeholder="例如：城市设定集" /></label><label>默认扫描深度<input v-model.number="worldbookForm.scan_depth" type="number" min="0" max="100" /></label></div>
          <label>描述<textarea v-model="worldbookForm.description" placeholder="这本世界书的用途与内容范围"></textarea></label>
          <div class="check-row"><label><input v-model="worldbookForm.case_sensitive" type="checkbox" /> 区分关键词大小写</label><label><input v-model="worldbookForm.match_whole_words" type="checkbox" /> 全词匹配</label></div>
          <div class="entry-heading"><h3>条目（{{ worldbookForm.entries.length }}）</h3><button class="secondary" type="button" @click="addWorldbookEntry">新增条目</button></div>
          <article v-for="(entry, index) in worldbookForm.entries" :key="entry.uid" class="worldbook-entry"><div class="entry-heading"><b>条目 {{ index + 1 }}</b><button class="text-button" type="button" @click="removeWorldbookEntry(entry.uid)">移除</button></div><div class="form-grid"><label>备注<input v-model="entry.comment" placeholder="条目名称" /></label><label>关键词（逗号分隔）<input v-model="entry.keywords" placeholder="城市, 街区" /></label></div><label>内容<textarea v-model="entry.content" required placeholder="注入 Prompt 的世界观文本"></textarea></label><div class="entry-options"><label><input v-model="entry.enabled" type="checkbox" /> 启用</label><label><input v-model="entry.constant" type="checkbox" /> 常驻</label><label><input v-model="entry.selective" type="checkbox" /> 关键词触发</label><label>位置<select v-model.number="entry.position"><option v-for="position in 8" :key="position - 1" :value="position - 1">{{ position - 1 }}</option></select></label><label>深度<input v-model.number="entry.depth" type="number" min="0" /></label><label>顺序<input v-model.number="entry.order" type="number" /></label><label>角色<select v-model="entry.role"><option value="system">system</option><option value="user">user</option><option value="assistant">assistant</option></select></label></div></article>
          <small v-if="worldbookError" class="error">{{ worldbookError }}</small>
          <div class="modal-actions"><RouterLink class="secondary button-link" to="/worldbooks">取消</RouterLink><button class="primary" :disabled="worldbookSaving">{{ worldbookSaving ? '正在保存…' : '保存世界书' }}</button></div>
        </form>
      </template>

      <template v-else-if="route.path === '/worldbooks'">
        <div class="toolbar"><RouterLink class="primary button-link" to="/worldbooks/create">创建世界书</RouterLink><label class="secondary import-button">导入 JSON<input type="file" accept=".json,application/json" @change="importWorldbookFile" /></label><button class="secondary" type="button" @click="refreshWorldbooks">刷新</button><small>{{ status }}</small></div>
        <template v-for="worldbook in worldbooks" :key="worldbook.id"><article v-if="worldbook.is_template" class="row-card"><i>书</i><div><b>{{ worldbook.name }}</b><small>{{ worldbook.description || '暂无描述' }} · {{ worldbook.entry_count }} 条目</small></div><span>系统模板（只读）</span><button class="secondary" type="button" @click="downloadAuthenticated(`/v1/worldbooks/${worldbook.id}/export`, `${worldbook.name}.json`)">导出</button></article><article v-else class="row-card"><i>书</i><div><b>{{ worldbook.name }}</b><small>{{ worldbook.description || '暂无描述' }} · {{ worldbook.entry_count }} 条目</small></div><RouterLink :to="`/worldbooks/${worldbook.id}/edit`" class="secondary button-link">编辑</RouterLink><button class="secondary" type="button" @click="downloadAuthenticated(`/v1/worldbooks/${worldbook.id}/export`, `${worldbook.name}.json`)">导出</button></article></template>
        <p v-if="!loading && worldbooks.length === 0" class="empty">还没有世界书。创建一本来管理可复用的设定。</p>
      </template>

      <template v-else-if="isAssetEditor">
        <form class="editor-card" @submit.prevent="saveAsset">
          <div class="chat-toolbar"><RouterLink class="back-link" :to="assetBasePath">← 所有{{ assetLabel }}</RouterLink><span>真实 API · {{ assetEditingId ? 'PUT' : 'POST' }} {{ assetApiPath }}</span></div>
          <h2>{{ assetEditingId ? `编辑${assetLabel}` : `创建${assetLabel}` }}</h2>
          <div class="form-grid"><label>名称<input v-model="assetForm.name" required maxlength="200" /></label><label>描述<input v-model="assetForm.description" /></label></div>
          <label>高级内容（JSON）<textarea class="json-editor" v-model="assetForm.payload" spellcheck="false"></textarea></label>
          <p class="hint">该字段保留后端支持的完整高级配置；预设填写 sampling/context/prompts，模板填写 blocks，正则预设填写 scripts。</p>
          <small v-if="assetError" class="error">{{ assetError }}</small>
          <div class="modal-actions"><RouterLink class="secondary button-link" :to="assetBasePath">取消</RouterLink><button class="primary" :disabled="assetSaving">{{ assetSaving ? '正在保存…' : '保存' }}</button></div>
        </form>
      </template>

      <template v-else-if="isAssetList">
        <div class="toolbar"><RouterLink class="primary button-link" :to="`${assetBasePath}/create`">创建{{ assetLabel }}</RouterLink><label v-if="assetKind !== 'templates'" class="secondary import-button">导入 JSON<input type="file" accept=".json,application/json" @change="importAssetFile" /></label><button class="secondary" type="button" @click="refreshAssets">刷新</button><small>{{ status }}</small></div>
        <article v-for="asset in assets" :key="asset.id" class="row-card"><i>{{ assetLabel.slice(0, 1) }}</i><div><b>{{ asset.name }}</b><small>{{ asset.description || assetMeta(asset) }}</small></div><RouterLink class="secondary button-link" :to="`${assetBasePath}/${asset.id}/edit`">编辑</RouterLink><button v-if="assetKind !== 'templates'" class="secondary" type="button" @click="downloadAuthenticated(`${assetApiPath}/${asset.id}/export`, `${asset.name}.json`)">导出</button><button class="text-button" type="button" @click="deleteAsset(asset.id)">删除</button></article>
        <p v-if="!loading && assets.length === 0" class="empty">暂无{{ assetLabel }}。</p>
      </template>

      <template v-else-if="route.path === '/memories'">
        <div class="toolbar"><button class="secondary" type="button" @click="refreshMemories">刷新</button><small>{{ status }}</small></div>
        <article v-for="memory in memories" :key="memory.id" class="row-card"><i>忆</i><div><b>{{ memory.content }}</b><small>{{ memory.category }} · {{ memory.memory_type }} · 重要度 {{ memory.importance }}</small></div><button class="secondary" type="button" @click="editMemory(memory)">编辑</button><button class="text-button" type="button" @click="deleteMemory(memory.id)">删除</button></article>
        <p v-if="!loading && memories.length === 0" class="empty">暂无记忆。</p>
      </template>

      <template v-else-if="route.path === '/mood'">
        <div class="toolbar"><button class="secondary" type="button" @click="refreshMood">刷新近 30 天数据</button><small>{{ status }}</small></div>
        <section class="insight-grid"><article class="migration-card"><p class="eyebrow">真实 API · /v1/emotions/distribution</p><h2>情绪分布</h2><p v-for="item in emotionDistribution" :key="item.emotion"><b>{{ item.emotion }}</b>　{{ item.count }} 次 · {{ item.percentage }}%</p><p v-if="!emotionDistribution.length" class="empty">尚无情绪分析记录。</p></article><article class="migration-card"><p class="eyebrow">真实 API · /v1/emotions/trend</p><h2>情绪趋势</h2><p v-for="item in emotionTrend" :key="item.date"><b>{{ item.date }}</b>　{{ item.dominant_emotion }} · 强度 {{ item.avg_intensity }}</p><p v-if="!emotionTrend.length" class="empty">尚无趋势数据。</p></article></section>
      </template>

      <template v-else-if="route.path === '/relationships'">
        <div class="toolbar"><button class="secondary" type="button" @click="refreshRelationships">刷新关系</button><small>{{ status }}</small></div>
        <article v-for="relationship in relationships" :key="relationship.persona.id" class="row-card"><i>{{ relationship.persona.name.slice(0, 1) }}</i><div><b>{{ relationship.persona.name }}</b><small>{{ relationship.data.level_name }} · 好感度 {{ relationship.data.affinity_score }} · {{ relationship.data.total_messages }} 条消息</small></div><span>{{ relationship.data.milestones?.join(' · ') || '暂无里程碑' }}</span></article><p v-if="!loading && relationships.length === 0" class="empty">暂无可展示的角色关系。</p>
      </template>

      <template v-else-if="route.path.startsWith('/settings') && !isSecuritySettings">
        <form class="editor-card" @submit.prevent="saveSettings"><p class="eyebrow">真实 API · PATCH /v1/users/me</p><h2>账户与显示偏好</h2><label>昵称<input v-model="settingsForm.nickname" required maxlength="50" /></label><label>全局 CSS 主题<textarea v-model="settingsForm.css_theme" placeholder="可输入完整 CSS；由后端保存，主题注入将在下一切片完成。"></textarea></label><div class="check-row"><label><input v-model="settingsForm.default_analyze_emotion" type="checkbox" /> 新对话默认开启情感分析</label><label><input v-model="settingsForm.mvu_compat_enabled" type="checkbox" /> 启用 MVU 兼容</label></div><small v-if="settingsStatus" :class="settingsStatus.startsWith('保存') ? '' : 'error'">{{ settingsStatus }}</small><div class="modal-actions"><button class="primary" type="submit">保存账户设置</button></div></form>
      </template>

      <template v-else-if="isSecuritySettings">
        <section class="editor-card"><p class="eyebrow">真实 API · 账户安全</p><h2>密码与登录设备</h2><form class="security-form" @submit.prevent="changePassword"><label>当前密码<input v-model="passwordForm.old_password" type="password" required /></label><label>新密码（至少 6 位）<input v-model="passwordForm.new_password" type="password" minlength="6" required /></label><button class="primary">修改密码并退出所有设备</button></form><small v-if="securityStatus" :class="securityStatus.startsWith('成功') ? '' : 'error'">{{ securityStatus }}</small><div class="entry-heading"><h3>登录设备</h3><button class="secondary" type="button" @click="refreshSessions">刷新</button></div><article v-for="session in sessions" :key="session.id" class="row-card"><i>端</i><div><b>{{ session.device_label }}{{ session.is_current ? '（当前）' : '' }}</b><small>{{ session.ip_address || '未知 IP' }} · 最近活跃：{{ formatDate(session.last_seen_at) }}</small></div><button v-if="!session.is_current" class="text-button" type="button" @click="revokeSession(session.id)">撤销</button></article><div class="modal-actions"><button class="secondary" type="button" @click="revokeOtherSessions">撤销其他设备</button><button class="text-button" type="button" @click="revokeCurrentSession">退出当前设备</button></div></section>
      </template>

      <template v-else>
        <section class="migration-card"><p class="eyebrow">待迁移路由</p><h2>{{ pageTitle }}</h2><p>该页面已经在新的导航与认证壳中，但其 CRUD、编辑器和流式交互尚未迁移。旧前端继续作为功能参照，后端接口保持不变。</p><code>{{ route.path }}</code></section>
      </template>
    </section>

    <div v-if="createDialogOpen" class="modal-backdrop" role="presentation" @click.self="createDialogOpen = false">
      <form class="modal" @submit.prevent="createConversation">
        <p class="eyebrow">真实 API · POST /v1/conversations</p><h2>新建对话</h2>
        <label>角色<select v-model="selectedPersonaId" required><option disabled value="">选择一个角色</option><option v-for="persona in personas" :key="persona.id" :value="persona.id">{{ persona.name }}</option></select></label>
        <label>标题（可选）<input v-model="newConversationTitle" maxlength="100" placeholder="例如：雨夜的初次相遇" /></label>
        <small v-if="createError" class="error">{{ createError }}</small>
        <div class="modal-actions"><button class="secondary" type="button" @click="createDialogOpen = false">取消</button><button class="primary" :disabled="creating">{{ creating ? '正在创建…' : '创建并进入' }}</button></div>
      </form>
    </div>
    <div v-if="editingMemory" class="modal-backdrop" role="presentation" @click.self="editingMemory = null"><form class="modal" @submit.prevent="saveMemory"><p class="eyebrow">真实 API · PUT /v1/memories/:id</p><h2>编辑记忆</h2><label>内容<textarea v-model="editingMemory.content"></textarea></label><label>分类<input v-model="editingMemory.category" /></label><label>类型<select v-model="editingMemory.memory_type"><option value="fact">fact</option><option value="event">event</option><option value="state">state</option></select></label><small v-if="memoryError" class="error">{{ memoryError }}</small><div class="modal-actions"><button class="secondary" type="button" @click="editingMemory = null">取消</button><button class="primary">保存</button></div></form></div>
    <div v-if="conversationSettingsOpen" class="modal-backdrop" role="presentation" @click.self="conversationSettingsOpen = false"><form class="modal wide-modal" @submit.prevent="saveConversationSettings"><p class="eyebrow">真实 API · 对话级资产绑定</p><h2>对话设置</h2><p v-if="conversationSettingsLoading" class="empty">正在加载可用资产…</p><template v-else><div class="form-grid"><label>预设<select v-model="conversationSettings.preset_id"><option value="">无</option><option v-for="item in conversationAssetOptions.presets" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>Prompt 模板<select v-model="conversationSettings.template_id"><option value="">系统默认</option><option v-for="item in conversationAssetOptions.templates" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>正则预设<select v-model="conversationSettings.regex_preset_id"><option value="">无</option><option v-for="item in conversationAssetOptions.regex" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>世界书（可多选）<select v-model="conversationSettings.worldbook_ids" multiple size="5"><option v-for="item in conversationAssetOptions.worldbooks" :key="item.id" :value="item.id">{{ item.name }}</option></select></label></div><label>Author’s Note<textarea v-model="conversationSettings.author_note" placeholder="注入当前对话的作者注释"></textarea></label><div class="form-grid"><label>AN 深度<input v-model.number="conversationSettings.an_depth" type="number" min="0" max="100" /></label><label>AN 角色<select v-model="conversationSettings.an_role"><option value="system">system</option><option value="user">user</option><option value="assistant">assistant</option></select></label><label>AN 间隔<input v-model.number="conversationSettings.an_interval" type="number" min="1" /></label></div><label><input v-model="conversationSettings.analyze_emotion" type="checkbox" /> 对本对话启用情感分析</label><label><input v-model="conversationSettings.mvu_dangerous" type="checkbox" /> 允许 MVU 卡执行危险操作</label></template><small v-if="conversationSettingsStatus" :class="conversationSettingsStatus.startsWith('保存') ? '' : 'error'">{{ conversationSettingsStatus }}</small><div class="modal-actions"><button class="secondary" type="button" @click="conversationSettingsOpen = false">取消</button><button class="primary" :disabled="conversationSettingsLoading">保存设置</button></div></form></div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

type User = { id: string; email: string; nickname?: string; css_theme?: string | null; default_analyze_emotion?: boolean; mvu_compat_enabled?: boolean }
type Conversation = { id: string; title?: string; persona_name?: string; updated_at?: string; analyze_emotion?: boolean; mvu_capabilities?: { dangerous?: boolean }; preset_id?: string | null; template_id?: string | null; regex_preset_id?: string | null; worldbook_ids?: string[]; author_note?: string | null; an_depth?: number; an_role?: string; an_interval?: number }
type Persona = { id: string; name: string; personality?: string; tags?: string[]; is_template?: boolean; is_owner?: boolean; source?: string }
type PersonaDetail = Persona & { background?: string | null; first_message?: string | null; mes_example?: string | null; scenario?: string | null; alternate_greetings?: string[]; css_theme?: string | null }
type Message = { id: string; role: 'user' | 'assistant' | 'system'; content: string; display_content?: string | null; created_at?: string }
type PersonaForm = { name: string; personality: string; background: string; scenario: string; first_message: string; mes_example: string; tags: string; alternate_greetings: string; css_theme: string }
type WorldbookListItem = { id: string; name: string; description?: string | null; entry_count: number; is_template: boolean }
type WorldbookEntryForm = { uid: number; comment: string; content: string; enabled: boolean; constant: boolean; selective: boolean; keywords: string; position: number; depth: number; order: number; role: string; raw: Record<string, unknown> }
type WorldbookForm = { name: string; description: string; scan_depth: number; case_sensitive: boolean; match_whole_words: boolean; entries: WorldbookEntryForm[] }
type AssetItem = { id: string; name: string; description?: string | null; prompt_count?: number; script_count?: number; blocks?: unknown[] }
type AssetForm = { name: string; description: string; payload: string }
type Memory = { id: string; content: string; category: string; importance: number; memory_type: string; scope: string }
type EmotionDistribution = { emotion: string; count: number; percentage: number }
type EmotionTrend = { date: string; dominant_emotion: string; avg_intensity: number }
type Relationship = { level_name: string; affinity_score: number; total_messages: number; milestones?: string[] }
type UserSession = { id: string; device_label: string; ip_address?: string | null; last_seen_at?: string; is_current: boolean }

const route = useRoute()
const router = useRouter()
const theme = ref<'night' | 'day'>('day')
const token = ref(localStorage.getItem('emiya-next-token') || '')
const user = ref<User | null>(readStoredUser())
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const status = ref('')
const conversations = ref<Conversation[]>([])
const personas = ref<Persona[]>([])
const messages = ref<Message[]>([])
const messagesLoading = ref(false)
const draft = ref('')
const replyLength = ref('medium')
const streaming = ref(false)
const streamStatus = ref('')
let activeAbort: AbortController | null = null
const createDialogOpen = ref(false)
const selectedPersonaId = ref('')
const newConversationTitle = ref('')
const creating = ref(false)
const createError = ref('')
const activePersona = ref<PersonaDetail | null>(null)
const personaLoading = ref(false)
const personaSaving = ref(false)
const personaError = ref('')
const personaForm = ref<PersonaForm>(emptyPersonaForm())
const worldbooks = ref<WorldbookListItem[]>([])
const worldbookForm = ref<WorldbookForm>(emptyWorldbookForm())
const worldbookSaving = ref(false)
const worldbookError = ref('')
const assets = ref<AssetItem[]>([])
const assetForm = ref<AssetForm>({ name: '', description: '', payload: '{}' })
const assetSaving = ref(false)
const assetError = ref('')
const memories = ref<Memory[]>([])
const editingMemory = ref<Memory | null>(null)
const memoryError = ref('')
const settingsForm = ref({ nickname: user.value?.nickname || '', css_theme: user.value?.css_theme || '', default_analyze_emotion: user.value?.default_analyze_emotion || false, mvu_compat_enabled: user.value?.mvu_compat_enabled !== false })
const settingsStatus = ref('')
const emotionDistribution = ref<EmotionDistribution[]>([])
const emotionTrend = ref<EmotionTrend[]>([])
const relationships = ref<Array<{ persona: Persona; data: Relationship }>>([])
const sessions = ref<UserSession[]>([])
const passwordForm = ref({ old_password: '', new_password: '' })
const securityStatus = ref('')
const conversationSettingsOpen = ref(false)
const conversationSettings = ref({ analyze_emotion: true, mvu_dangerous: false, preset_id: '', template_id: '', regex_preset_id: '', worldbook_ids: [] as string[], author_note: '', an_depth: 4, an_role: 'system', an_interval: 1 })
const conversationSettingsStatus = ref('')
const conversationSettingsLoading = ref(false)
const conversationAssetOptions = ref<{ presets: AssetItem[]; templates: AssetItem[]; regex: AssetItem[]; worldbooks: WorldbookListItem[] }>({ presets: [], templates: [], regex: [], worldbooks: [] })

const mainNav = [{ id: 'chat', label: '对话', to: '/chat' }, { id: 'studio', label: '创作资产', to: '/personas' }, { id: 'insights', label: '记忆与感知', to: '/memories' }, { id: 'account', label: '账户', to: '/settings' }]
const mainActive = computed(() => route.path.startsWith('/chat') ? 'chat' : route.path.startsWith('/personas') || route.path.startsWith('/worldbooks') || route.path.startsWith('/presets') || route.path.startsWith('/templates') || route.path.startsWith('/regex-presets') ? 'studio' : route.path.startsWith('/memories') || route.path.startsWith('/mood') || route.path.startsWith('/relationships') ? 'insights' : 'account')
const subNav = computed(() => mainActive.value === 'studio' ? [{ label: '角色', to: '/personas' }, { label: '世界书', to: '/worldbooks' }, { label: '预设', to: '/presets' }, { label: '模板', to: '/templates' }, { label: '正则', to: '/regex-presets' }] : mainActive.value === 'insights' ? [{ label: '记忆', to: '/memories' }, { label: '情绪', to: '/mood' }, { label: '关系', to: '/relationships' }] : mainActive.value === 'account' ? [{ label: '资料', to: '/settings' }, { label: '显示偏好', to: '/settings?tab=display' }, { label: '安全', to: '/settings?tab=security' }] : [])
const isChatDetail = computed(() => /^\/chat\/[^/]+$/.test(route.path))
const conversationId = computed(() => isChatDetail.value ? route.path.split('/')[2] || '' : '')
const activeConversation = computed(() => conversations.value.find((conversation) => conversation.id === conversationId.value))
const isPersonaEditor = computed(() => route.path === '/personas/create' || /^\/personas\/[^/]+\/edit$/.test(route.path))
const isPersonaDetail = computed(() => /^\/personas\/[^/]+$/.test(route.path))
const personaEditingId = computed(() => /^\/personas\/[^/]+\/edit$/.test(route.path) ? route.path.split('/')[2] || '' : '')
const personaDetailId = computed(() => isPersonaDetail.value ? route.path.split('/')[2] || '' : '')
const personaSections = computed(() => activePersona.value ? [{ label: '性格', content: activePersona.value.personality }, { label: '背景故事', content: activePersona.value.background }, { label: '当前情境', content: activePersona.value.scenario }, { label: '开场白', content: activePersona.value.first_message }, { label: '对话示例', content: activePersona.value.mes_example }] : [])
const isWorldbookEditor = computed(() => route.path === '/worldbooks/create' || /^\/worldbooks\/[^/]+\/edit$/.test(route.path))
const worldbookEditingId = computed(() => /^\/worldbooks\/[^/]+\/edit$/.test(route.path) ? route.path.split('/')[2] || '' : '')
const assetKind = computed<'presets' | 'templates' | 'regex-presets' | ''>(() => route.path.startsWith('/presets') ? 'presets' : route.path.startsWith('/templates') ? 'templates' : route.path.startsWith('/regex-presets') ? 'regex-presets' : '')
const assetBasePath = computed(() => assetKind.value ? `/${assetKind.value}` : '')
const assetApiPath = computed(() => `/v1/${assetKind.value}`)
const assetLabel = computed(() => assetKind.value === 'presets' ? '预设' : assetKind.value === 'templates' ? 'Prompt 模板' : '正则预设')
const isAssetList = computed(() => Boolean(assetKind.value) && route.path === assetBasePath.value)
const isAssetEditor = computed(() => Boolean(assetKind.value) && (route.path === `${assetBasePath.value}/create` || new RegExp(`^${assetBasePath.value}/[^/]+/edit$`).test(route.path)))
const assetEditingId = computed(() => new RegExp(`^${assetBasePath.value}/[^/]+/edit$`).test(route.path) ? route.path.split('/')[2] || '' : '')
const isSecuritySettings = computed(() => route.path === '/settings' && route.query.tab === 'security')
const pageTitle = computed(() => mainActive.value === 'chat' ? (isChatDetail.value ? activeConversation.value?.title || '对话工作区' : '对话工作区') : mainActive.value === 'studio' ? '创作资产' : mainActive.value === 'insights' ? '记忆与感知' : '账户设置')
const pageKicker = computed(() => mainActive.value === 'chat' ? '真实数据 · 会话与消息' : 'EMIYA Next · 迁移切片')
const pageDescription = computed(() => mainActive.value === 'chat' ? (isChatDetail.value ? '历史消息与流式回复均接入现有后端。' : '已接入现有后端的会话读取与创建接口。') : '新前端独立运行；旧前端保持不动。')

function readStoredUser(): User | null { try { return JSON.parse(localStorage.getItem('emiya-next-user') || 'null') } catch { return null } }
function isSubActive(target: string) { return target.split('?')[0] === route.path && (!target.includes('?') || target.split('?')[1] === new URLSearchParams(route.query as Record<string, string>).toString()) }
function displayContent(message: Message) { return message.display_content || message.content }
function roleLabel(role: Message['role']) { return role === 'user' ? '你' : role === 'assistant' ? '角色' : '系统' }
function formatDate(value?: string) { return value ? new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '刚刚' }
function newTemporaryId(prefix: string) { return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}` }
function emptyPersonaForm(): PersonaForm { return { name: '', personality: '', background: '', scenario: '', first_message: '', mes_example: '', tags: '', alternate_greetings: '', css_theme: '' } }
function formFromPersona(persona: PersonaDetail): PersonaForm { return { name: persona.name, personality: persona.personality || '', background: persona.background || '', scenario: persona.scenario || '', first_message: persona.first_message || '', mes_example: persona.mes_example || '', tags: persona.tags?.join(', ') || '', alternate_greetings: persona.alternate_greetings?.join('\n') || '', css_theme: persona.css_theme || '' } }
function emptyWorldbookForm(): WorldbookForm { return { name: '', description: '', scan_depth: 2, case_sensitive: false, match_whole_words: false, entries: [] } }
function emptyWorldbookEntry(uid: number): WorldbookEntryForm { return { uid, comment: '', content: '', enabled: true, constant: false, selective: false, keywords: '', position: 0, depth: 4, order: 100, role: 'system', raw: {} } }
function worldbookEntryFromApi(entry: Record<string, unknown>): WorldbookEntryForm { return { uid: Number(entry.uid), comment: String(entry.comment || ''), content: String(entry.content || ''), enabled: entry.enabled !== false, constant: entry.constant === true, selective: entry.selective === true, keywords: Array.isArray(entry.key) ? entry.key.map(String).join(', ') : '', position: Number(entry.position ?? 0), depth: Number(entry.depth ?? 4), order: Number(entry.order ?? 100), role: String(entry.role || 'system'), raw: entry } }
function worldbookEntryToApi(entry: WorldbookEntryForm) { return { ...entry.raw, uid: entry.uid, comment: entry.comment, content: entry.content, enabled: entry.enabled, constant: entry.constant, selective: entry.selective, key: splitTags(entry.keywords), position: entry.position, depth: entry.depth, order: entry.order, role: entry.role } }
function splitLines(value: string) { return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean) }
function splitTags(value: string) { return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean) }
function nullableText(value: string) { return value.trim() || null }
function applyCustomCss(css: string) { const id = 'emiya-next-user-css'; const existing = document.getElementById(id); if (!css.trim()) { existing?.remove(); return } const style = existing || Object.assign(document.createElement('style'), { id }); style.textContent = css; if (!existing) document.head.append(style) }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (token.value) headers.set('Authorization', `Bearer ${token.value}`)
  const response = await fetch(`/api${path}`, { ...init, headers })
  if (response.status === 401) signOut()
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `请求失败（${response.status}）`)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
async function uploadFile<T>(path: string, file: File): Promise<T> { const body = new FormData(); body.append('file', file); const response = await fetch(`/api${path}`, { method: 'POST', headers: { Authorization: `Bearer ${token.value}` }, body }); if (response.status === 401) signOut(); if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `导入失败（${response.status}）`); return response.json() as Promise<T> }
async function postForm<T>(path: string, body: FormData): Promise<T> { const response = await fetch(`/api${path}`, { method: 'POST', headers: { Authorization: `Bearer ${token.value}` }, body }); if (response.status === 401) signOut(); if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `请求失败（${response.status}）`); return response.json() as Promise<T> }
async function downloadAuthenticated(path: string, fallbackName: string) { status.value = '正在准备导出…'; try { const response = await fetch(`/api${path}`, { headers: { Authorization: `Bearer ${token.value}` } }); if (!response.ok) throw new Error(`导出失败（${response.status}）`); const disposition = response.headers.get('Content-Disposition') || ''; const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]; const plainName = disposition.match(/filename="?([^";]+)"?/i)?.[1]; let filename = encodedName ? decodeURIComponent(encodedName) : plainName || fallbackName; let blob: Blob; if ((response.headers.get('Content-Type') || '').includes('application/json')) { const json = await response.json() as { filename?: string; data?: unknown }; if (json && typeof json === 'object' && 'data' in json && json.filename) { filename = json.filename; blob = new Blob([JSON.stringify(json.data, null, 2)], { type: 'application/json' }) } else blob = new Blob([JSON.stringify(json, null, 2)], { type: 'application/json' }) } else blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); status.value = '导出完成' } catch (cause) { status.value = cause instanceof Error ? cause.message : '导出失败' } }
async function signIn() { loading.value = true; error.value = ''; try { const result = await request<{ access_token: string; user: User }>('/v1/auth/login', { method: 'POST', body: JSON.stringify({ email: email.value, password: password.value }) }); token.value = result.access_token; user.value = result.user; settingsForm.value = { nickname: result.user.nickname || '', css_theme: result.user.css_theme || '', default_analyze_emotion: result.user.default_analyze_emotion || false, mvu_compat_enabled: result.user.mvu_compat_enabled !== false }; applyCustomCss(settingsForm.value.css_theme); localStorage.setItem('emiya-next-token', result.access_token); localStorage.setItem('emiya-next-user', JSON.stringify(result.user)); await refreshConversations(); await router.replace('/chat') } catch (cause) { error.value = cause instanceof Error ? cause.message : '登录失败' } finally { loading.value = false } }
function signOut() { activeAbort?.abort(); token.value = ''; user.value = null; conversations.value = []; personas.value = []; messages.value = []; localStorage.removeItem('emiya-next-token'); localStorage.removeItem('emiya-next-user'); void router.replace('/chat') }
async function refreshConversations() { loading.value = true; status.value = '正在读取会话…'; try { conversations.value = await request<Conversation[]>('/v1/conversations'); status.value = `已加载 ${conversations.value.length} 个会话` } catch (cause) { status.value = cause instanceof Error ? cause.message : '读取失败' } finally { loading.value = false } }
async function refreshPersonas() { loading.value = true; status.value = '正在读取角色…'; try { personas.value = await request<Persona[]>('/v1/personas'); status.value = `已加载 ${personas.value.length} 个角色` } catch (cause) { status.value = cause instanceof Error ? cause.message : '读取失败' } finally { loading.value = false } }
async function refreshWorldbooks() { loading.value = true; status.value = '正在读取世界书…'; try { worldbooks.value = await request<WorldbookListItem[]>('/v1/worldbooks'); status.value = `已加载 ${worldbooks.value.length} 本世界书` } catch (cause) { status.value = cause instanceof Error ? cause.message : '读取失败' } finally { loading.value = false } }
async function loadWorldbook() {
  worldbookError.value = ''
  if (route.path === '/worldbooks/create') { worldbookForm.value = emptyWorldbookForm(); return }
  if (!worldbookEditingId.value) return
  try {
    const detail = await request<{ name: string; description?: string | null; scan_depth: number; case_sensitive: boolean; match_whole_words: boolean; entries: Array<Record<string, unknown>> }>(`/v1/worldbooks/${worldbookEditingId.value}`)
    worldbookForm.value = { name: detail.name, description: detail.description || '', scan_depth: detail.scan_depth, case_sensitive: detail.case_sensitive, match_whole_words: detail.match_whole_words, entries: detail.entries.map(worldbookEntryFromApi) }
  } catch (cause) { worldbookError.value = cause instanceof Error ? cause.message : '读取世界书失败' }
}
function addWorldbookEntry() { const uid = Math.max(0, ...worldbookForm.value.entries.map((entry) => entry.uid)) + 1; worldbookForm.value.entries.push(emptyWorldbookEntry(uid)) }
function removeWorldbookEntry(uid: number) { worldbookForm.value.entries = worldbookForm.value.entries.filter((entry) => entry.uid !== uid) }
async function saveWorldbook() {
  const form = worldbookForm.value; if (!form.name.trim()) return
  worldbookSaving.value = true; worldbookError.value = ''
  const payload = { name: form.name.trim(), description: nullableText(form.description), scan_depth: form.scan_depth, case_sensitive: form.case_sensitive, match_whole_words: form.match_whole_words, entries: form.entries.map(worldbookEntryToApi) }
  try {
    const saved = worldbookEditingId.value ? await request<{ id: string }>(`/v1/worldbooks/${worldbookEditingId.value}`, { method: 'PUT', body: JSON.stringify(payload) }) : await request<{ id: string }>('/v1/worldbooks', { method: 'POST', body: JSON.stringify(payload) })
    await refreshWorldbooks(); await router.replace(`/worldbooks/${saved.id}/edit`)
  } catch (cause) { worldbookError.value = cause instanceof Error ? cause.message : '保存世界书失败' } finally { worldbookSaving.value = false }
}
function defaultAssetPayload() { return assetKind.value === 'presets' ? { sampling_params: {}, context_settings: {}, prompts: [], extensions: {} } : assetKind.value === 'templates' ? { blocks: [], is_default: false } : { scripts: [] } }
function assetMeta(asset: AssetItem) { return asset.prompt_count != null ? `${asset.prompt_count} 个提示词` : asset.script_count != null ? `${asset.script_count} 条脚本` : asset.blocks?.length != null ? `${asset.blocks.length} 个区块` : '高级配置' }
async function refreshAssets() { loading.value = true; status.value = `正在读取${assetLabel.value}…`; try { assets.value = await request<AssetItem[]>(assetApiPath.value); status.value = `已加载 ${assets.value.length} 个${assetLabel.value}` } catch (cause) { status.value = cause instanceof Error ? cause.message : '读取失败' } finally { loading.value = false } }
async function loadAsset() {
  assetError.value = ''
  if (!assetEditingId.value) { assetForm.value = { name: '', description: '', payload: JSON.stringify(defaultAssetPayload(), null, 2) }; return }
  try { const detail = await request<Record<string, unknown>>(`${assetApiPath.value}/${assetEditingId.value}`); const { id: _id, name, description, created_at: _createdAt, updated_at: _updatedAt, ...payload } = detail; assetForm.value = { name: String(name || ''), description: String(description || ''), payload: JSON.stringify(payload, null, 2) } } catch (cause) { assetError.value = cause instanceof Error ? cause.message : '读取失败' }
}
async function saveAsset() {
  if (!assetForm.value.name.trim()) return
  assetSaving.value = true; assetError.value = ''
  try {
    const advanced = JSON.parse(assetForm.value.payload || '{}') as unknown
    if (!advanced || Array.isArray(advanced) || typeof advanced !== 'object') throw new Error('高级内容必须是 JSON 对象')
    const body = { ...(advanced as Record<string, unknown>), name: assetForm.value.name.trim(), description: nullableText(assetForm.value.description) }
    const saved = assetEditingId.value ? await request<{ id: string }>(`${assetApiPath.value}/${assetEditingId.value}`, { method: 'PUT', body: JSON.stringify(body) }) : await request<{ id: string }>(assetApiPath.value, { method: 'POST', body: JSON.stringify(body) })
    await refreshAssets(); await router.replace(`${assetBasePath.value}/${saved.id}/edit`)
  } catch (cause) { assetError.value = cause instanceof Error ? cause.message : '保存失败' } finally { assetSaving.value = false }
}
async function deleteAsset(id: string) { if (!window.confirm(`确定删除此${assetLabel.value}？`)) return; try { await request<void>(`${assetApiPath.value}/${id}`, { method: 'DELETE' }); await refreshAssets() } catch (cause) { status.value = cause instanceof Error ? cause.message : '删除失败' } }
async function importAssetFile(event: Event) { const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return; status.value = `正在导入${assetLabel.value}…`; try { await uploadFile(`${assetApiPath.value}/import`, file); await refreshAssets() } catch (cause) { status.value = cause instanceof Error ? cause.message : '导入失败' } finally { input.value = '' } }
async function importWorldbookFile(event: Event) { const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return; status.value = '正在导入世界书…'; try { await uploadFile('/v1/worldbooks/import', file); await refreshWorldbooks() } catch (cause) { status.value = cause instanceof Error ? cause.message : '导入失败' } finally { input.value = '' } }
async function importPersonaFile(event: Event) { const input = event.target as HTMLInputElement; const file = input.files?.[0]; if (!file) return; status.value = '正在解析角色卡…'; try { const parseBody = new FormData(); parseBody.append('file', file); const parsed = await postForm<{ preview: Record<string, unknown> }>('/v1/personas/import/parse', parseBody); const name = String(parsed.preview?.name || file.name); if (!window.confirm(`解析到角色「${name}」，确认导入？`)) return; const confirmBody = new FormData(); confirmBody.append('parse_result', JSON.stringify(parsed.preview)); confirmBody.append('overrides', JSON.stringify(parsed.preview)); if (file.type === 'image/png' || file.name.toLowerCase().endsWith('.png')) confirmBody.append('avatar_file', file); await postForm('/v1/personas/import/confirm', confirmBody); await refreshPersonas(); status.value = `已导入角色「${name}」` } catch (cause) { status.value = cause instanceof Error ? cause.message : '导入失败' } finally { input.value = '' } }
async function refreshMemories() { loading.value = true; status.value = '正在读取记忆…'; try { const result = await request<{ items: Memory[]; total: number }>('/v1/memories?limit=50'); memories.value = result.items; status.value = `已加载 ${result.total} 条记忆` } catch (cause) { status.value = cause instanceof Error ? cause.message : '读取失败' } finally { loading.value = false } }
function editMemory(memory: Memory) { memoryError.value = ''; editingMemory.value = { ...memory } }
async function saveMemory() { if (!editingMemory.value) return; memoryError.value = ''; try { const saved = await request<Memory>(`/v1/memories/${editingMemory.value.id}`, { method: 'PUT', body: JSON.stringify({ content: editingMemory.value.content, category: editingMemory.value.category, memory_type: editingMemory.value.memory_type }) }); const index = memories.value.findIndex((memory) => memory.id === saved.id); if (index >= 0) memories.value[index] = saved; editingMemory.value = null } catch (cause) { memoryError.value = cause instanceof Error ? cause.message : '保存失败' } }
async function deleteMemory(id: string) { if (!window.confirm('确定删除这条记忆？')) return; try { await request<void>(`/v1/memories/${id}`, { method: 'DELETE' }); memories.value = memories.value.filter((memory) => memory.id !== id) } catch (cause) { status.value = cause instanceof Error ? cause.message : '删除失败' } }
async function saveSettings() { settingsStatus.value = ''; try { const saved = await request<User>('/v1/users/me', { method: 'PATCH', body: JSON.stringify(settingsForm.value) }); user.value = saved; applyCustomCss(settingsForm.value.css_theme); localStorage.setItem('emiya-next-user', JSON.stringify(saved)); settingsStatus.value = '保存成功' } catch (cause) { settingsStatus.value = cause instanceof Error ? cause.message : '保存失败' } }
async function refreshMood() { loading.value = true; status.value = '正在读取情绪数据…'; try { const [distribution, trend] = await Promise.all([request<EmotionDistribution[]>('/v1/emotions/distribution?days=30'), request<EmotionTrend[]>('/v1/emotions/trend?days=30')]); emotionDistribution.value = distribution; emotionTrend.value = trend; status.value = '已加载近 30 天情绪数据' } catch (cause) { status.value = cause instanceof Error ? cause.message : '读取失败' } finally { loading.value = false } }
async function refreshRelationships() { loading.value = true; status.value = '正在读取角色关系…'; try { const personaList = await request<Persona[]>('/v1/personas'); const rows = await Promise.all(personaList.map(async (persona) => ({ persona, data: await request<Relationship>(`/v1/relationships/${persona.id}`) }))); relationships.value = rows; status.value = `已加载 ${rows.length} 个角色关系` } catch (cause) { status.value = cause instanceof Error ? cause.message : '读取失败' } finally { loading.value = false } }
async function refreshSessions() { securityStatus.value = ''; try { sessions.value = await request<UserSession[]>('/v1/users/me/sessions') } catch (cause) { securityStatus.value = cause instanceof Error ? cause.message : '读取会话失败' } }
async function changePassword() { securityStatus.value = ''; try { await request<void>('/v1/users/me/change-password', { method: 'POST', body: JSON.stringify(passwordForm.value) }); passwordForm.value = { old_password: '', new_password: '' }; securityStatus.value = '成功：密码已修改，请重新登录'; signOut() } catch (cause) { securityStatus.value = cause instanceof Error ? cause.message : '修改密码失败' } }
async function revokeSession(id: string) { if (!window.confirm('确定撤销该设备的登录会话？')) return; try { await request<void>(`/v1/users/me/sessions/${id}`, { method: 'DELETE' }); await refreshSessions() } catch (cause) { securityStatus.value = cause instanceof Error ? cause.message : '撤销失败' } }
async function revokeOtherSessions() { if (!window.confirm('确定撤销当前设备外的所有会话？')) return; try { const result = await request<{ revoked: number }>('/v1/users/me/sessions/revoke-others', { method: 'POST' }); securityStatus.value = `成功：已撤销 ${result.revoked} 个会话`; await refreshSessions() } catch (cause) { securityStatus.value = cause instanceof Error ? cause.message : '撤销失败' } }
async function revokeCurrentSession() { if (!window.confirm('确定退出当前设备？')) return; try { await request<void>('/v1/users/me/sessions/revoke-current', { method: 'POST' }); signOut() } catch (cause) { securityStatus.value = cause instanceof Error ? cause.message : '退出失败' } }
async function openConversationSettings() { const conversation = activeConversation.value; conversationSettingsStatus.value = ''; conversationSettings.value = { analyze_emotion: conversation?.analyze_emotion ?? true, mvu_dangerous: conversation?.mvu_capabilities?.dangerous ?? false, preset_id: conversation?.preset_id || '', template_id: conversation?.template_id || '', regex_preset_id: conversation?.regex_preset_id || '', worldbook_ids: [...(conversation?.worldbook_ids || [])], author_note: conversation?.author_note || '', an_depth: conversation?.an_depth ?? 4, an_role: conversation?.an_role || 'system', an_interval: conversation?.an_interval ?? 1 }; conversationSettingsOpen.value = true; conversationSettingsLoading.value = true; try { const [presets, templates, regex, availableWorldbooks] = await Promise.all([request<AssetItem[]>('/v1/presets'), request<AssetItem[]>('/v1/templates'), request<AssetItem[]>('/v1/regex-presets'), request<WorldbookListItem[]>('/v1/worldbooks')]); conversationAssetOptions.value = { presets, templates, regex, worldbooks: availableWorldbooks } } catch (cause) { conversationSettingsStatus.value = cause instanceof Error ? cause.message : '加载资产失败' } finally { conversationSettingsLoading.value = false } }
async function saveConversationSettings() { if (!conversationId.value) return; conversationSettingsStatus.value = ''; const id = conversationId.value; const settings = conversationSettings.value; try { await request<Conversation>(`/v1/conversations/${id}/apply-preset`, { method: 'PUT', body: JSON.stringify({ preset_id: settings.preset_id || null }) }); await request<Conversation>(`/v1/conversations/${id}/template`, { method: 'PUT', body: JSON.stringify({ template_id: settings.template_id || null }) }); await request<Conversation>(`/v1/conversations/${id}/regex-preset`, { method: 'PUT', body: JSON.stringify({ regex_preset_id: settings.regex_preset_id || null }) }); await request<Conversation>(`/v1/conversations/${id}/worldbooks`, { method: 'PUT', body: JSON.stringify({ worldbook_ids: settings.worldbook_ids }) }); await request<Conversation>(`/v1/conversations/${id}/author-note`, { method: 'PUT', body: JSON.stringify({ author_note: nullableText(settings.author_note), an_depth: settings.an_depth, an_role: settings.an_role, an_interval: settings.an_interval }) }); await request<Conversation>(`/v1/conversations/${id}/toggles`, { method: 'PATCH', body: JSON.stringify({ analyze_emotion: settings.analyze_emotion }) }); await request<Conversation>(`/v1/conversations/${id}/mvu-capabilities`, { method: 'PATCH', body: JSON.stringify({ dangerous: settings.mvu_dangerous }) }); await refreshConversations(); conversationSettingsStatus.value = '保存成功'; conversationSettingsOpen.value = false } catch (cause) { conversationSettingsStatus.value = cause instanceof Error ? cause.message : '保存失败' } }
async function loadPersona() {
  personaError.value = ''
  if (route.path === '/personas/create') { activePersona.value = null; personaForm.value = emptyPersonaForm(); return }
  const id = personaEditingId.value || personaDetailId.value
  if (!id) return
  personaLoading.value = true
  try {
    const detail = await request<PersonaDetail>(`/v1/personas/${id}`)
    activePersona.value = detail
    if (personaEditingId.value) {
      if (detail.is_template) { await router.replace(`/personas/${id}`); return }
      personaForm.value = formFromPersona(detail)
    }
  } catch (cause) { activePersona.value = null; personaError.value = cause instanceof Error ? cause.message : '读取角色失败' } finally { personaLoading.value = false }
}
async function savePersona() {
  const form = personaForm.value; if (!form.name.trim() || !form.personality.trim()) return
  personaSaving.value = true; personaError.value = ''
  const payload = { name: form.name.trim(), personality: form.personality.trim(), background: nullableText(form.background), scenario: nullableText(form.scenario), first_message: nullableText(form.first_message), mes_example: nullableText(form.mes_example), tags: splitTags(form.tags), alternate_greetings: splitLines(form.alternate_greetings), css_theme: nullableText(form.css_theme) }
  try {
    const saved = personaEditingId.value ? await request<PersonaDetail>(`/v1/personas/${personaEditingId.value}`, { method: 'PUT', body: JSON.stringify(payload) }) : await request<PersonaDetail>('/v1/personas', { method: 'POST', body: JSON.stringify(payload) })
    activePersona.value = saved; await refreshPersonas(); await router.replace(`/personas/${saved.id}`)
  } catch (cause) { personaError.value = cause instanceof Error ? cause.message : '保存角色失败' } finally { personaSaving.value = false }
}
async function startConversationFromPersona() {
  if (!activePersona.value) return
  try { const conversation = await request<Conversation>('/v1/conversations', { method: 'POST', body: JSON.stringify({ persona_id: activePersona.value.id }) }); await refreshConversations(); await router.push(`/chat/${conversation.id}`) } catch (cause) { personaError.value = cause instanceof Error ? cause.message : '创建对话失败' }
}
async function refreshMessages() { if (!conversationId.value) return; messagesLoading.value = true; streamStatus.value = ''; try { const result = await request<Message[]>(`/v1/conversations/${conversationId.value}/messages?limit=200`); messages.value = result.reverse() } catch (cause) { streamStatus.value = cause instanceof Error ? cause.message : '读取消息失败' } finally { messagesLoading.value = false } }
async function openCreateDialog() { createError.value = ''; newConversationTitle.value = ''; selectedPersonaId.value = ''; if (!personas.value.length) await refreshPersonas(); createDialogOpen.value = true }
async function createConversation() { creating.value = true; createError.value = ''; try { const result = await request<Conversation>('/v1/conversations', { method: 'POST', body: JSON.stringify({ persona_id: selectedPersonaId.value, title: newConversationTitle.value || null }) }); createDialogOpen.value = false; await refreshConversations(); await router.push(`/chat/${result.id}`) } catch (cause) { createError.value = cause instanceof Error ? cause.message : '创建对话失败' } finally { creating.value = false } }
async function sendMessage() {
  const content = draft.value.trim(); if (!content || !conversationId.value || streaming.value) return
  draft.value = ''; streaming.value = true; streamStatus.value = '正在生成回复…'
  const userMessage: Message = { id: newTemporaryId('local-user'), role: 'user', content }
  const assistantMessage: Message = { id: newTemporaryId('stream'), role: 'assistant', content: '' }
  messages.value.push(userMessage, assistantMessage)
  activeAbort = new AbortController()
  try {
    const response = await fetch(`/api/v1/conversations/${conversationId.value}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token.value}` }, body: JSON.stringify({ content, reply_length: replyLength.value }), signal: activeAbort.signal })
    if (!response.ok || !response.body) throw new Error(`请求失败（${response.status}）`)
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
    while (true) {
      const { done, value } = await reader.read(); if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      const events = buffer.split('\n\n'); buffer = events.pop() || ''
      for (const eventText of events) {
        const event = eventText.match(/^event: (.+)$/m)?.[1]; const rawData = eventText.match(/^data: (.+)$/m)?.[1]
        if (!event || !rawData) continue
        const data = JSON.parse(rawData) as { content?: string; error?: string; final_content?: string; final_display_content?: string }
        if (event === 'message_delta') assistantMessage.content += data.content || ''
        if (event === 'message_done') { assistantMessage.content = data.final_content || assistantMessage.content; assistantMessage.display_content = data.final_display_content || null; streamStatus.value = '回复已保存'; await refreshConversations() }
        if (event === 'error') throw new Error(data.error || '生成失败')
      }
    }
  } catch (cause) { streamStatus.value = cause instanceof DOMException && cause.name === 'AbortError' ? '已停止生成' : cause instanceof Error ? cause.message : '生成失败' } finally { streaming.value = false; activeAbort = null }
}
function cancelStream() { activeAbort?.abort() }
async function loadRoute() { if (!token.value) return; if (isChatDetail.value) { if (!conversations.value.length) await refreshConversations(); await refreshMessages() } else if (route.path === '/chat') await refreshConversations(); else if (isPersonaEditor.value || isPersonaDetail.value) await loadPersona(); else if (route.path === '/personas') await refreshPersonas(); else if (isWorldbookEditor.value) await loadWorldbook(); else if (route.path === '/worldbooks') await refreshWorldbooks(); else if (isAssetEditor.value) await loadAsset(); else if (isAssetList.value) await refreshAssets(); else if (route.path === '/memories') await refreshMemories(); else if (route.path === '/mood') await refreshMood(); else if (route.path === '/relationships') await refreshRelationships(); else if (isSecuritySettings.value) await refreshSessions() }
onMounted(() => { applyCustomCss(settingsForm.value.css_theme); void loadRoute() })
watch(() => route.fullPath, () => void loadRoute())
</script>

<style>
:root{font-family:Inter,"Microsoft YaHei",sans-serif;color:#253143;background:#f2eee7}*{box-sizing:border-box}body{margin:0}.next-app{min-height:100vh;background:#f2eee7;transition:background .2s,color .2s}.main-nav,.sub-nav{position:fixed;left:50%;z-index:10;display:flex;gap:4px;padding:5px;border:1px solid #d8cfc1;border-radius:999px;background:#fffaf2ef;box-shadow:0 10px 30px #4a362015;backdrop-filter:blur(12px);transform:translateX(-50%)}.main-nav{top:14px}.sub-nav{top:78px}.main-nav a,.sub-nav a,.theme-button{padding:8px 12px;color:#536171;border:0;border-radius:999px;background:transparent;font-size:13px;text-decoration:none;white-space:nowrap;cursor:pointer}.main-nav a.active,.sub-nav a.active{color:#fffaf1;background:#cf9065}.theme-button{color:#965f39}.workspace{width:min(1120px,90vw);margin:auto;padding:148px 0 70px}.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:30px}.eyebrow{margin:0 0 8px;color:#997250;font-size:11px;letter-spacing:.12em}.page-heading h1,.auth-card h1,.modal h2{margin:0;font:600 42px Georgia,"Microsoft YaHei",serif}.page-heading p:not(.eyebrow){margin:8px 0 0;color:#718093}.identity{display:flex;align-items:center;gap:10px}.identity>b,.row-card i{display:grid;width:40px;height:40px;place-items:center;color:#fffaf2;border-radius:50%;background:#a86252;font-style:normal}.identity span{display:grid;gap:3px;color:#536171;font-size:12px}.identity button{padding:0;color:#997250;border:0;background:transparent;text-align:left;cursor:pointer}.toolbar,.chat-toolbar{display:flex;align-items:center;gap:12px;margin-bottom:12px}.toolbar small,.chat-toolbar span{color:#718093}.primary,.secondary{padding:10px 14px;border-radius:7px;cursor:pointer}.primary{color:#fffaf1;border:1px solid #9c5d4e;background:#a86252}.secondary{color:#805f39;border:1px solid #d1c3b0;background:#fffaf2}.button-link{display:inline-block;text-decoration:none;font-size:13px}.primary:disabled{opacity:.6}.row-card,.migration-card,.chat-panel,.editor-card,.persona-detail{margin:10px 0;padding:16px;border:1px solid #d8cfc1;border-radius:12px;background:#fffaf2;box-shadow:0 5px 14px #4a362009}.row-card{display:flex;align-items:center;gap:13px;text-decoration:none}.conversation-row{transition:transform .16s,border-color .16s}.conversation-row:hover{border-color:#c99a76;transform:translateY(-1px)}.row-card div{display:grid;gap:4px;flex:1}.row-card small,.empty,.migration-card p{color:#718093;font-size:12px}.row-card span{color:#997250;font-size:12px}.empty{padding:24px;border:1px dashed #cfc4b4;border-radius:10px}.migration-card{display:block;max-width:720px}.migration-card h2{margin:0;font:600 28px Georgia,"Microsoft YaHei",serif}.migration-card code{display:block;margin-top:16px;padding:9px;color:#805f39;border-radius:6px;background:#f2eee7}.auth-shell{display:grid;min-height:100vh;place-items:center;padding:28px}.auth-card,.modal{display:grid;width:min(420px,100%);gap:14px;padding:32px;border:1px solid #d8cfc1;border-radius:15px;background:#fffaf2;box-shadow:0 20px 50px #4a362015}.auth-card p{margin:0;color:#718093;line-height:1.7}.auth-card label,.modal label,.composer label,.editor-card>label{display:grid;gap:6px;color:#536171;font-size:12px}.auth-card input,.modal input,.modal select,.composer textarea,.composer select,.editor-card input,.editor-card textarea{padding:10px;color:#253143;border:1px solid #cec4b7;border-radius:7px;background:#fffefa;font:inherit}.editor-card{display:grid;gap:15px;max-width:900px}.editor-card h2,.persona-detail h2{margin:0;font:600 30px Georgia,"Microsoft YaHei",serif}.editor-card textarea{min-height:105px;resize:vertical}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px}.form-grid label{display:grid;gap:6px;color:#536171;font-size:12px}.error{color:#a74343}.back-link{color:#965f39;font-size:13px;text-decoration:none}.chat-toolbar{justify-content:flex-start}.chat-toolbar .secondary{margin-left:auto}.chat-panel{padding:0;overflow:hidden}.message-list{display:grid;gap:12px;min-height:360px;max-height:58vh;padding:20px;overflow:auto;background:linear-gradient(135deg,#fffdf8,#f7f1e9)}.message{max-width:min(80%,720px);padding:12px 14px;border-radius:12px;background:#ece5da}.message.user{justify-self:end;color:#fffaf2;background:#a86252}.message.assistant{justify-self:start}.message.system{justify-self:center;background:#f1e4d7}.message-role{display:block;margin-bottom:5px;font-size:11px;opacity:.7}.message p{margin:0;white-space:pre-wrap;line-height:1.65}.composer{display:grid;gap:10px;padding:15px;border-top:1px solid #e1d8cc}.composer textarea{width:100%;min-height:92px;resize:vertical}.composer>div{display:flex;align-items:end;gap:12px}.composer small{flex:1;color:#718093;font-size:12px}.persona-detail{display:grid;gap:18px;max-width:900px}.persona-detail header{display:flex;align-items:center;gap:14px;padding-bottom:16px;border-bottom:1px solid #e3d9cb}.persona-detail header i{display:grid;width:68px;height:68px;place-items:center;color:#fffaf2;border-radius:50%;background:#a86252;font:32px Georgia,serif;font-style:normal}.persona-detail header small{color:#718093}.persona-detail article h3{margin:0 0 7px;color:#805f39;font-size:13px}.persona-detail article p{margin:0;color:#536171;white-space:pre-wrap;line-height:1.7}.modal-backdrop{position:fixed;z-index:20;inset:0;display:grid;place-items:center;padding:20px;background:#2f251c75;backdrop-filter:blur(4px)}.modal h2{font-size:31px}.modal-actions{display:flex;justify-content:flex-end;gap:9px;margin-top:4px}.next-app[data-theme="night"]{color:#ebe5dc;background:#1f2329}.next-app[data-theme="night"] .main-nav,.next-app[data-theme="night"] .sub-nav,.next-app[data-theme="night"] .auth-card,.next-app[data-theme="night"] .modal,.next-app[data-theme="night"] .row-card,.next-app[data-theme="night"] .migration-card,.next-app[data-theme="night"] .chat-panel,.next-app[data-theme="night"] .editor-card,.next-app[data-theme="night"] .persona-detail{border-color:#504c49;background:#292e35;box-shadow:none}.next-app[data-theme="night"] .main-nav a,.next-app[data-theme="night"] .sub-nav a,.next-app[data-theme="night"] .theme-button,.next-app[data-theme="night"] .identity span,.next-app[data-theme="night"] .auth-card label,.next-app[data-theme="night"] .modal label,.next-app[data-theme="night"] .composer label,.next-app[data-theme="night"] .editor-card>label,.next-app[data-theme="night"] .form-grid label{color:#c7d0da}.next-app[data-theme="night"] .page-heading p:not(.eyebrow),.next-app[data-theme="night"] .row-card small,.next-app[data-theme="night"] .empty,.next-app[data-theme="night"] .composer small,.next-app[data-theme="night"] .chat-toolbar span,.next-app[data-theme="night"] .persona-detail header small,.next-app[data-theme="night"] .persona-detail article p{color:#a7b1bd}.next-app[data-theme="night"] .message-list{background:#22272e}.next-app[data-theme="night"] .message.assistant{background:#343b45}.next-app[data-theme="night"] .message.system{background:#403932}.next-app[data-theme="night"] .auth-card input,.next-app[data-theme="night"] .modal input,.next-app[data-theme="night"] .modal select,.next-app[data-theme="night"] .composer textarea,.next-app[data-theme="night"] .composer select,.next-app[data-theme="night"] .editor-card input,.next-app[data-theme="night"] .editor-card textarea{color:#ece6dc;border-color:#555c65;background:#20252b}.next-app[data-theme="night"] .secondary{color:#e4c3a5;border-color:#5a5650;background:#343942}.next-app[data-theme="night"] .persona-detail header{border-color:#4b5159}.next-app[data-theme="night"] .persona-detail article h3{color:#e4c3a5}@media(max-width:720px){.main-nav,.sub-nav{max-width:94vw;overflow:auto}.workspace{width:min(92vw,1120px);padding-top:140px}.page-heading{align-items:flex-start;flex-direction:column}.page-heading h1{font-size:34px}.message{max-width:92%}.composer>div{align-items:center;flex-wrap:wrap}.composer small{min-width:120px}.chat-toolbar{flex-wrap:wrap}.chat-toolbar .secondary{margin-left:0}.form-grid{grid-template-columns:1fr}}
.worldbook-editor{max-width:1000px}.wide-modal{width:min(820px,96vw);max-height:90vh;overflow:auto}.import-button{display:inline-flex;align-items:center;font-size:13px}.import-button input{display:none}.entry-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.entry-heading h3{margin:0;font:600 20px Georgia,"Microsoft YaHei",serif}.worldbook-entry{display:grid;gap:12px;padding:15px;border:1px solid #e0d4c4;border-radius:9px;background:#fffdf8}.worldbook-entry textarea{min-height:120px;resize:vertical}.entry-options,.check-row{display:flex;gap:12px;flex-wrap:wrap}.entry-options label,.check-row label{display:flex;align-items:center;gap:5px;color:#536171;font-size:12px}.entry-options input,.entry-options select{width:auto;padding:7px;color:#253143;border:1px solid #cec4b7;border-radius:6px;background:#fffefa;font:inherit}.text-button{padding:0;color:#a74343;border:0;background:transparent;cursor:pointer;font-size:12px}.next-app[data-theme="night"] .worldbook-entry{border-color:#4b5159;background:#22272e}.next-app[data-theme="night"] .entry-options label,.next-app[data-theme="night"] .check-row label{color:#c7d0da}.next-app[data-theme="night"] .entry-options input,.next-app[data-theme="night"] .entry-options select{color:#ece6dc;border-color:#555c65;background:#20252b}
</style>
