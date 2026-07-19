# -*- coding: utf-8 -*-
"""ADR-0021（延伸）：MVU zod schema 真跑求默认值（V8/mini-racer + zod）单元测试。

验证行正则搞不定、V8 能搞定的形态：`.prefault`（Zod v4）、`const Schema = z.object` 根写法、
嵌套；以及两种 registerMvuSchema 约定、无 schema/坏 schema/超时的回退（返回 None）。
mini-racer / zod 不可用则整组 skip。
"""
import time

import pytest

from app.services.mvu_runtime import schema_eval

pytestmark = pytest.mark.skipif(
    not schema_eval.is_available(), reason="mini-racer / zod 不可用（生产回退行正则）"
)

# 覆盖行正则的三处死穴：.prefault（非 .default）、`const Schema = z.object` 根、跨行嵌套 + 子 schema 引用。
_SCHEMA = """
import { registerMvuSchema } from 'x/mvu_zod.js';
const Bar = z.object({ 当前: z.coerce.number().prefault(100) }).prefault({});
export const Schema = z.object({
  进程: z.object({ 阶段: z.string().prefault("创角阶段") }).prefault({}),
  系统状态: z.object({
    主角创建完毕: z.boolean().prefault(false),
    计数: z.coerce.number().prefault(1),
  }).prefault({}),
  血条: Bar,
});
$(() => { registerMvuSchema(Schema); });
"""


def _scripts(content: str):
    return [{"name": "zod", "content": content}]


def test_prefault_nested_root_convention():
    d = schema_eval.extract_defaults(_scripts(_SCHEMA))
    assert d is not None
    assert d["进程"]["阶段"] == "创角阶段"          # .prefault 被认（行正则会漏）
    assert d["系统状态"]["主角创建完毕"] is False   # 关键脚手架字段
    assert d["系统状态"]["计数"] == 1
    assert d["血条"]["当前"] == 100                # 引用同脚本的子 schema


def test_stat_data_wrapper_convention():
    # registerMvuSchema({ stat_data: z.object(...) })（伶伶等卡的包一层写法）
    s = "registerMvuSchema({ stat_data: z.object({ hp: z.coerce.number().prefault(5) }).prefault({}) });"
    d = schema_eval.extract_defaults(_scripts(s))
    assert d == {"hp": 5}


def test_no_schema_returns_none():
    assert schema_eval.extract_defaults(_scripts("const x = 1;")) is None
    assert schema_eval.extract_defaults([]) is None
    assert schema_eval.extract_defaults(None) is None


def test_bad_schema_returns_none():
    # 语法错 → eval 失败 → None（调用方回退行正则，不崩）
    assert schema_eval.extract_defaults(_scripts("registerMvuSchema(z.object({ x: )")) is None


def test_infinite_loop_in_schema_is_timed_out():
    # schema 定义期死循环（IIFE）→ timeout 拦下 → None，且不永久 hang。
    s = "registerMvuSchema(z.object({ x: z.any().prefault((function(){ while(true){} })()) }));"
    t0 = time.time()
    d = schema_eval.extract_defaults(_scripts(s), timeout_ms=300)
    assert d is None
    assert time.time() - t0 < 5  # 被 timeout 拦，秒级返回


@pytest.mark.asyncio
async def test_works_in_async_context():
    # 生产在 async（create_conversation）里调；确认 worker 线程模式在 async 下不 hang、结果正确。
    d = schema_eval.extract_defaults(_scripts(_SCHEMA))
    assert d is not None and d["进程"]["阶段"] == "创角阶段"
