// MVU 卡宿主能力分层 + 限权策略（ADR-0008d D2）。纯逻辑，Node/Vitest 可测。
//
// 三层：
//   local     —— 安全，Host 内本地做，不走父窗口（对本回合 stat_data 读写、DOM/toastr）
//   read      —— 只读，Bridge 中介，默认允许（世界书、全局变量读）
//   dangerous —— 写/花钱，Bridge 中介 + 后端端点，**默认拒绝**（卡调 LLM、卡改会话楼层）

const LOCAL = new Set([
  'insertOrAssignVariables', 'deleteVariable', 'getvar', 'setvar',
])
const READ = new Set([
  'getWorldbook', 'getWorldInfo', 'getLorebook', 'getCharLorebooks',
])
const DANGEROUS = new Set([
  'generateRaw', 'generate', 'setChatMessages', 'createChatMessages', 'deleteChatMessages',
])

/** 分类一个能力。`getVariables({type:'global'})` 归 read（读全局会话变量），否则归 local（本回合 stat_data）。 */
export function classifyCapability(cap, args) {
  if (cap === 'getVariables') {
    return args && args.type === 'global' ? 'read' : 'local'
  }
  if (LOCAL.has(cap)) return 'local'
  if (READ.has(cap)) return 'read'
  if (DANGEROUS.has(cap)) return 'dangerous'
  return 'unknown'
}

export const defaultCapabilityPolicy = {
  read: true, // 只读默认允许
  dangerous: false, // 危险默认拒绝（per-conversation 显式开启才放行）
  allowUnknown: false, // 未知能力默认拒绝（有界失败）
}

/** 决定放行与否。返回 {allow, tier, reason?}。dangerous/unknown 默认 deny。 */
export function resolveCapability(cap, policy = defaultCapabilityPolicy, args) {
  const tier = classifyCapability(cap, args)
  const p = { ...defaultCapabilityPolicy, ...(policy || {}) }
  switch (tier) {
    case 'local':
      return { allow: true, tier }
    case 'read':
      return { allow: p.read !== false, tier, reason: p.read !== false ? undefined : 'read disabled' }
    case 'dangerous':
      return { allow: p.dangerous === true, tier, reason: p.dangerous === true ? undefined : 'dangerous cap default-denied (需 per-conversation 开启)' }
    default:
      return { allow: p.allowUnknown === true, tier, reason: p.allowUnknown === true ? undefined : `unknown cap: ${cap}` }
  }
}
