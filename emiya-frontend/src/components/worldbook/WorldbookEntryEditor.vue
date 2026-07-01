<template>
  <div class="entry-editor" v-if="entry">
    <div class="editor-header">
      <n-input
        v-model:value="entry.comment"
        placeholder="条目名称（仅编辑器显示）"
        size="large"
      />
      <n-switch v-model:value="entry.enabled">
        <template #checked>启用</template>
        <template #unchecked>禁用</template>
      </n-switch>
    </div>

    <n-collapse :default-expanded-names="['basic', 'trigger']">
      <n-collapse-item title="基本" name="basic">
        <n-form-item label="内容" label-placement="top">
          <n-input
            v-model:value="entry.content"
            type="textarea"
            placeholder="注入到 Prompt 的实际文本"
            :autosize="{ minRows: 6, maxRows: 20 }"
          />
        </n-form-item>

        <n-form-item label-placement="left">
          <template #label>
            常驻 constant
            <WorldbookHelpHint>
              <div>
                勾选后<b>忽略关键词匹配</b>，每轮无条件激活。<br />
                注意：被激活的条目仍受 token 预算限制（除非同时勾上 <code>ignore_budget</code>）。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-switch v-model:value="entry.constant" />
        </n-form-item>

        <n-form-item label-placement="left">
          <template #label>
            豁免预算 ignore_budget
            <WorldbookHelpHint>
              <div>
                豁免 token 预算检查。即使本轮世界书预算已耗尽，本条目<b>仍坚持注入</b>。<br />
                慎用——多条豁免会突破"世界书最多占 25% 上下文"的安全线。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-switch v-model:value="entry.ignore_budget" />
        </n-form-item>
      </n-collapse-item>

      <n-collapse-item title="触发关键词" name="trigger">
        <n-form-item label-placement="top">
          <template #label>
            主关键词 key
            <WorldbookHelpHint>
              <div>
                触发本条目的关键词，列表任一命中即满足条件。<br />
                每个标签是一个独立关键词，匹配近 N 条聊天历史。<br />
                形如 <code>/pattern/flags</code> 的元素会作为<b>正则表达式</b>处理，
                例如 <code>/远坂.{0,3}/</code> 可命中"远坂家"、"远坂凛"；其余按明文子串匹配。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-dynamic-tags v-model:value="entry.key" />
        </n-form-item>

        <n-form-item label-placement="top">
          <template #label>
            副关键词 keysecondary
            <WorldbookHelpHint>
              <div>
                配合主关键词使用的二级关键词。主关键词命中后，副关键词按下方"选择逻辑"
                决定最终是否激活。<br />
                留空即不参与判定（主关键词命中就激活）。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-dynamic-tags v-model:value="entry.keysecondary" />
        </n-form-item>

        <n-form-item label-placement="left">
          <template #label>
            选择逻辑 selective_logic
            <WorldbookHelpHint>
              <div>主关键词已命中的前提下，副关键词按此组合判定：</div>
              <ul>
                <li><b>AND_ANY</b>：任一副关键词命中即激活</li>
                <li><b>AND_ALL</b>：所有副关键词全部命中才激活</li>
                <li><b>NOT_ANY</b>：所有副关键词都未命中才激活（"提到 X 但没提到任何 Y"）</li>
                <li><b>NOT_ALL</b>：不是全部命中才激活（"提到 X 但不是完整提了所有 Y"）</li>
              </ul>
            </WorldbookHelpHint>
          </template>
          <n-select
            v-model:value="entry.selective_logic"
            :options="LOGIC_OPTIONS"
            style="width: 280px"
          />
        </n-form-item>

        <n-form-item label-placement="left">
          <template #label>
            扫描深度 scan_depth
            <span v-if="entry.scan_depth === null" class="inherit-tag">继承自书级</span>
            <WorldbookHelpHint>
              <div>
                关键词匹配时取最近 N 条聊天消息组成"扫描缓冲区"。<br />
                深度越大，更早的消息也能触发本条目，但代价是 LLM 调用前的处理开销。<br />
                清空 = 跟随本书级默认（当前 <b>{{ bookDefaults.scan_depth }}</b>）。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-input-number
            v-model:value="effectiveScanDepth"
            :min="0"
            :max="100"
            clearable
            placeholder="清空恢复继承"
          />
        </n-form-item>

        <n-form-item label-placement="left">
          <template #label>
            大小写敏感 case_sensitive
            <span v-if="entry.case_sensitive === null" class="inherit-tag">继承自书级</span>
            <WorldbookHelpHint>
              <div>
                关键词匹配是否区分大小写。对中文无影响；英文场景下"cat"和"Cat"是否视为不同。<br />
                清空 = 跟随本书级默认（当前 <b>{{ bookDefaults.case_sensitive ? '是' : '否' }}</b>）。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-select
            v-model:value="effectiveCaseSensitive"
            :options="TRIBOOL_OPTIONS"
            clearable
            style="width: 200px"
          />
        </n-form-item>

        <n-form-item label-placement="left">
          <template #label>
            整词匹配 match_whole_words
            <span v-if="entry.match_whole_words === null" class="inherit-tag">继承自书级</span>
            <WorldbookHelpHint>
              <div>
                开启后，关键词必须作为<b>独立单词</b>出现才命中：
                <code>cat</code> 不会命中 <code>catastrophe</code>。<br />
                中文场景下作用有限（没有单词边界）。<br />
                清空 = 跟随本书级默认（当前 <b>{{ bookDefaults.match_whole_words ? '是' : '否' }}</b>）。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-select
            v-model:value="effectiveMatchWholeWords"
            :options="TRIBOOL_OPTIONS"
            clearable
            style="width: 200px"
          />
        </n-form-item>
      </n-collapse-item>

      <n-collapse-item title="位置与排序" name="position">
        <n-form-item label-placement="left">
          <template #label>
            position
            <WorldbookHelpHint>
              <div>条目内容在最终 Prompt 中的落点。8 个值对齐 SillyTavern：</div>
              <ul>
                <li><b>0-1</b>：角色描述<b>前 / 后</b></li>
                <li><b>2-3</b>：作者笔记 (AN) <b>之上 / 之下</b></li>
                <li><b>4</b>：聊天历史<b>倒数第 N 条之前</b>（需配合下方 depth）</li>
                <li><b>5-6</b>：示例对话<b>之上 / 之下</b></li>
                <li><b>7</b>：具名插槽（需配合 outlet_name + 在 Prompt 模板里放一个 outlet 块）</li>
              </ul>
            </WorldbookHelpHint>
          </template>
          <n-select
            v-model:value="entry.position"
            :options="POSITION_OPTIONS"
            style="width: 280px"
          />
        </n-form-item>
        <n-form-item v-if="entry.position === 4" label-placement="left">
          <template #label>
            depth
            <WorldbookHelpHint>
              <div>
                仅当 position = AT_DEPTH 时生效。<br />
                本条目作为消息插入到聊天历史<b>末尾倒数第 N 条之前</b>。<br />
                <code>depth=0</code> 表示插到所有消息之后；
                <code>depth=4</code>（常见默认）表示插到最近 4 条消息之前。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-input-number v-model:value="entry.depth" :min="0" :max="100" />
        </n-form-item>
        <n-form-item v-if="entry.position === 7" label-placement="left">
          <template #label>
            outlet 名称
            <WorldbookHelpHint>
              <div>
                仅当 position = OUTLET 时生效。<br />
                在 Prompt 模板里加一个 <code>type=outlet</code> 的块、其 <code>outlet_name</code>
                与此处填的相同，本条目内容就会被收集到那个块里。<br />
                多条目可共用同一个 outlet_name，内容按 order 拼接。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-input v-model:value="entry.outlet_name" placeholder="如 lore" />
        </n-form-item>
        <n-form-item label-placement="left">
          <template #label>
            order
            <WorldbookHelpHint>
              <div>
                同一 position 下多个条目的注入顺序。<b>数值大者先注入</b>，即出现在更靠前的位置。<br />
                ST 默认值 100。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-input-number v-model:value="entry.order" :min="0" :max="9999" />
        </n-form-item>
        <n-form-item label-placement="left">
          <template #label>
            role
            <WorldbookHelpHint>
              <div>
                条目作为消息插入时的角色。绝大多数情况选 <code>system</code>；
                仅当 position = AT_DEPTH 且想模拟"过往用户/角色对话"时才用
                <code>user</code> / <code>assistant</code>。
              </div>
            </WorldbookHelpHint>
          </template>
          <n-select
            v-model:value="entry.role"
            :options="ROLE_OPTIONS"
            style="width: 200px"
          />
        </n-form-item>
      </n-collapse-item>

      <n-collapse-item v-if="entry.extras && Object.keys(entry.extras).length > 0" title="兼容字段 (extras, 只读)" name="extras">
        <pre class="extras-pre">{{ JSON.stringify(entry.extras, null, 2) }}</pre>
        <div class="hint">这些字段是 ST 高级语义（sticky/cooldown/probability 等），EMIYA 当前不消费但保留以便导出无损。</div>
      </n-collapse-item>
    </n-collapse>
  </div>
  <div v-else class="empty-tip">左侧选择一个条目以编辑</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  NInput, NSwitch, NCollapse, NCollapseItem, NFormItem,
  NDynamicTags, NSelect, NInputNumber,
} from 'naive-ui'
import WorldbookHelpHint from './WorldbookHelpHint.vue'
import type { WorldbookEntry } from '../../types'

const props = defineProps<{
  entry: WorldbookEntry | null
  bookDefaults: {
    scan_depth: number
    case_sensitive: boolean
    match_whole_words: boolean
  }
}>()

// 三个 nullable 字段：getter 用书级回退展示有效值；setter 如实写入 entry。
// null = "继承书级"（清空按钮回到此状态）；非 null = 显式覆盖。
const effectiveScanDepth = computed<number | null>({
  get: () => (props.entry?.scan_depth ?? props.bookDefaults.scan_depth),
  set: (v) => { if (props.entry) props.entry.scan_depth = v },
})
const effectiveCaseSensitive = computed<string | null>({
  get: () => String(props.entry?.case_sensitive ?? props.bookDefaults.case_sensitive),
  set: (v) => { if (props.entry) props.entry.case_sensitive = v === null ? null : v === 'true' },
})
const effectiveMatchWholeWords = computed<string | null>({
  get: () => String(props.entry?.match_whole_words ?? props.bookDefaults.match_whole_words),
  set: (v) => { if (props.entry) props.entry.match_whole_words = v === null ? null : v === 'true' },
})

const LOGIC_OPTIONS = [
  { label: 'AND_ANY (任一副关键词命中)', value: 0 },
  { label: 'NOT_ALL (不全命中)', value: 1 },
  { label: 'NOT_ANY (任一命中则不激活)', value: 2 },
  { label: 'AND_ALL (全部命中)', value: 3 },
]

const POSITION_OPTIONS = [
  { label: '0 · BEFORE_CHAR (角色描述前)', value: 0 },
  { label: '1 · AFTER_CHAR (角色描述后)', value: 1 },
  { label: '2 · AN_TOP (作者笔记上)', value: 2 },
  { label: '3 · AN_BOTTOM (作者笔记下)', value: 3 },
  { label: '4 · AT_DEPTH (历史倒数 N 条之前)', value: 4 },
  { label: '5 · EM_TOP (示例对话上)', value: 5 },
  { label: '6 · EM_BOTTOM (示例对话下)', value: 6 },
  { label: '7 · OUTLET (具名插槽)', value: 7 },
]

const ROLE_OPTIONS = [
  { label: 'system', value: 'system' },
  { label: 'user', value: 'user' },
  { label: 'assistant', value: 'assistant' },
]

const TRIBOOL_OPTIONS = [
  { label: '是', value: 'true' },
  { label: '否', value: 'false' },
]
</script>

<style scoped>
.entry-editor { padding: 16px; }
.editor-header { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
.hint { color: var(--color-text-tertiary); font-size: 12px; margin-left: 8px; }
.inherit-tag {
  display: inline-block; margin-left: 6px;
  font-size: 11px; padding: 1px 6px; border-radius: 4px;
  background: var(--color-bg-hover); color: var(--color-text-tertiary);
  vertical-align: middle;
}
.extras-pre {
  background: var(--color-bg-base); border-radius: 6px; padding: 12px;
  max-height: 240px; overflow: auto; font-size: 12px;
}
.empty-tip { padding: 80px; text-align: center; color: var(--color-text-tertiary); }
</style>
