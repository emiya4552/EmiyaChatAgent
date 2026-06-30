# -*- coding: utf-8 -*-
"""清理旧预设：删除 JSON 文件 + 重置关联的 conversation.preset_name。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import AsyncSessionLocal
from sqlalchemy import update, text


PRESETS_DIR = os.path.join(os.path.dirname(__file__), "..", "presets")
FILES_TO_DELETE = [
    "TGbreakV2.1.0版.json",
    "三人逆行 v7.1长风渡之万恶の凝嘤嘤.json",
]


async def main():
    # 1. 删除 JSON 文件
    deleted = []
    for f in FILES_TO_DELETE:
        path = os.path.join(PRESETS_DIR, f)
        if os.path.exists(path):
            os.remove(path)
            deleted.append(f)
            print(f"[OK] 已删除: {f}")
        else:
            print(f"[SKIP] 不存在: {f}")

    # 2. 重置所有 conversation 的 preset_name 为 NULL
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("UPDATE conversations SET preset_name = NULL"))
        await db.commit()
        print(f"[OK] 已将 {result.rowcount} 条对话的 preset_name 设为 NULL")

    print(f"\n清理完成。删除了 {len(deleted)} 个预设文件。")


if __name__ == "__main__":
    asyncio.run(main())
