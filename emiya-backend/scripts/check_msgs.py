import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        # 查看最新的消息序列 (带序号，正序)
        r = await db.execute(text("""
            SELECT created_at, role, LEFT(content, 60)
            FROM messages ORDER BY created_at DESC LIMIT 30
        """))
        rows = list(r.all())
        rows.reverse()
        print(f"=== 最新 30 条消息 (共 {len(rows)} 条) ===")
        prev_role = None
        gaps = []
        for i, row in enumerate(rows):
            marker = ""
            if prev_role == "user" and row[1] == "user":
                marker = "  ← 缺少 assistant 回复!"
                gaps.append(str(row[0]))
            print(f"  {row[1]:<10} {str(row[0])[11:19]} | {row[2]}{marker}")
            prev_role = row[1]

        if gaps:
            print(f"\n发现 {len(gaps)} 处缺少 assistant 回复的时间点:")
            for g in gaps:
                print(f"  {g}")

        # 最后一个user消息之后的assistant消息
        r = await db.execute(text("""
            SELECT created_at, role, LEFT(content, 60)
            FROM messages ORDER BY created_at DESC LIMIT 1
        """))
        last = r.one()
        print(f"\n最后一条消息: [{last[1]}] {last[0]} | {last[2]}")

asyncio.run(main())
