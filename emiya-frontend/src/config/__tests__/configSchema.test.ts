import { describe, it, expect } from 'vitest'
import {
  CHAT_CONFIG_META, chatConfigSnapshot,
  enumFromInherit, enumToInherit, boolFromInherit, boolToInherit,
  GROUP,
} from '../configSchema'

// 与后端 tests/test_config_registry.py::EXPECTED_SCHEMA 的前三项（group/advanced/
// inheritable）逐项一致。改这里务必同步后端 registry + 那份快照。
const EXPECTED_SNAPSHOT: Record<string, [string, boolean, boolean]> = {
  temperature: [GROUP.SAMPLING, false, false],
  top_p: [GROUP.SAMPLING, true, false],
  top_k: [GROUP.SAMPLING, true, false],
  top_a: [GROUP.SAMPLING, true, false],
  min_p: [GROUP.SAMPLING, true, false],
  frequency_penalty: [GROUP.SAMPLING, true, false],
  presence_penalty: [GROUP.SAMPLING, true, false],
  repetition_penalty: [GROUP.SAMPLING, true, false],
  openai_max_context: [GROUP.TOKEN_BUDGET, false, false],
  openai_max_tokens: [GROUP.TOKEN_BUDGET, true, false],
  token_budget_safety_margin: [GROUP.TOKEN_BUDGET, true, false],
  history_budget_cap: [GROUP.TOKEN_BUDGET, true, false],
  worldbook_budget_pct: [GROUP.WORLDBOOK, true, false],
  worldbook_budget_cap: [GROUP.WORLDBOOK, true, false],
  worldbook_overflow_alert: [GROUP.WORLDBOOK, true, false],
  output_contract_mode: [GROUP.OUTPUT_CONTRACT_EXEC, false, true],
  output_contract_allow_full_rewrite: [GROUP.OUTPUT_CONTRACT_EXEC, true, true],
  output_contract_strict_fallback: [GROUP.OUTPUT_CONTRACT_EXEC, true, true],
  output_contract_require_confirmed: [GROUP.OUTPUT_CONTRACT_EXEC, true, true],
}

describe('configSchema chat_config metadata', () => {
  it('matches the 19-key backend snapshot', () => {
    expect(chatConfigSnapshot()).toEqual(EXPECTED_SNAPSHOT)
  })

  it('has no duplicate keys', () => {
    const keys = CHAT_CONFIG_META.map(m => m.key)
    expect(keys.length).toBe(new Set(keys).size)
    expect(keys.length).toBe(19)
  })

  it('marks all and only output_contract_exec items inheritable', () => {
    for (const m of CHAT_CONFIG_META) {
      expect(m.inheritable).toBe(m.group === GROUP.OUTPUT_CONTRACT_EXEC)
    }
  })
})

describe('configSchema inherit helpers', () => {
  it('enum round-trips null <-> inherit', () => {
    expect(enumFromInherit(null)).toBe('inherit')
    expect(enumFromInherit(undefined)).toBe('inherit')
    expect(enumFromInherit('strict')).toBe('strict')
    expect(enumToInherit('inherit')).toBeNull()
    expect(enumToInherit('strict')).toBe('strict')
  })

  it('bool tri-state round-trips true/false/null <-> yes/no/inherit', () => {
    expect(boolFromInherit(true)).toBe('yes')
    expect(boolFromInherit(false)).toBe('no')
    expect(boolFromInherit(null)).toBe('inherit')
    expect(boolFromInherit(undefined)).toBe('inherit')
    expect(boolToInherit('yes')).toBe(true)
    expect(boolToInherit('no')).toBe(false)
    expect(boolToInherit('inherit')).toBeNull()
  })
})
