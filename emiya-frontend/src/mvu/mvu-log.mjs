// MVU 专用轻量日志模块（前端 Host iframe + 父窗口 Controller 共用）。
//
// 目的：MVU 是最难调的部分（浏览器沙箱 iframe + 卡脚本 + 桥接 + 状态派生），把所有 MVU
// 相关日志统一到 `[MVU]` 前缀，便于在浏览器 Console 里按前缀过滤、快速定位是哪一环出问题。
//
// 约定：
//  - `debug/info` 可整体关掉（`globalThis.__MVU_LOG_OFF = true`），`warn/error` 恒输出。
//  - `mvuLog.scope('Host')` 派生带子标签的 logger → `[MVU:Host]`，用于区分 iframe(Host) 与
//    父窗口(Controller/Session)、或不同阶段（Host:script / Host:apply …）。
//  - 关键节点埋点约定（便于对照排障）：boot 起止、Vendored Stack 结果、逐脚本载入（含 kind，
//    语法错时前一条 debug 即指出是哪个脚本）、薄 Mvu 就绪、applyTurn 的 ops 进出与结算、
//    能力桥请求的放行/拒绝、各阶段异常。

const BASE = '[MVU]'

function _off() {
  try { return !!globalThis.__MVU_LOG_OFF } catch { return false }
}

function _make(tag) {
  const p = tag ? `${BASE}[${tag}]` : BASE
  return {
    debug: (...a) => { if (!_off()) console.debug(p, ...a) },
    info: (...a) => { if (!_off()) console.info(p, ...a) },
    warn: (...a) => console.warn(p, ...a),
    error: (...a) => console.error(p, ...a),
    /** 派生子标签 logger：mvuLog.scope('Host').scope('script') → [MVU:Host:script] */
    scope: (t) => _make(tag ? `${tag}:${t}` : t),
  }
}

export const mvuLog = _make('')
