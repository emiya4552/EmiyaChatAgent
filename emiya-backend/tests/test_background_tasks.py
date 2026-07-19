# -*- coding: utf-8 -*-
"""后台 fire-and-forget 任务强引用（DB 连接泄漏修复）回归测试。

`asyncio` 事件循环只对 task 持弱引用：裸 `create_task(coro)` 若不 hold 引用，task 可能在跑完前被
GC 回收，其 `async with AsyncSessionLocal()` 的异步 __aexit__ 跑不完 → DB 连接不归还连接池（表现为
`sqlalchemy.pool ... garbage collector ... non-checked-in connection` 告警，进而拖垮 PG）。
`nodes._spawn_background` 存强引用、完成后回调移除，保证后台任务跑到底、session 正常关闭。
"""
import asyncio

import pytest

from app.services.langgraph import nodes


@pytest.mark.asyncio
async def test_spawn_background_holds_ref_until_done():
    nodes._background_tasks.clear()
    ran: list[str] = []

    async def _work():
        await asyncio.sleep(0.05)
        ran.append("done")

    nodes._spawn_background(_work())
    # 派发后立即：任务在强引用池里（否则可能被 GC 中途回收）
    assert len(nodes._background_tasks) == 1

    await asyncio.sleep(0.2)
    # 完成后：确实跑完 + 从池移除（不泄漏引用）
    assert ran == ["done"]
    assert len(nodes._background_tasks) == 0


@pytest.mark.asyncio
async def test_spawn_background_discards_on_exception():
    # 任务内部抛错也要从池移除，别泄漏引用。
    nodes._background_tasks.clear()

    async def _boom():
        raise RuntimeError("boom")

    nodes._spawn_background(_boom())
    await asyncio.sleep(0.1)
    assert len(nodes._background_tasks) == 0
