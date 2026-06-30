"""分析当前记忆系统的状态。"""
import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text


async def main():
    async with AsyncSessionLocal() as db:
        # 1. 记忆分布
        r = await db.execute(text("""
            SELECT memory_type, category, COUNT(*), ROUND(AVG(importance)::numeric, 2)
            FROM memories WHERE is_deleted = false
            GROUP BY memory_type, category ORDER BY memory_type, category
        """))
        print("=== 记忆分布 (memory_type x category) ===")
        print(f"{'type':<8} {'category':<20} {'count':<6} {'avg_imp':<8}")
        print("-" * 44)
        for row in r.all():
            print(f"{row[0]:<8} {row[1]:<20} {row[2]:<6} {row[3]:<8}")

        # 总数
        r = await db.execute(text("SELECT COUNT(*) FROM memories WHERE is_deleted = false"))
        total = r.scalar()
        print(f"\n总记忆数: {total}")

        # by memory_type
        r = await db.execute(text(
            "SELECT memory_type, COUNT(*) FROM memories WHERE is_deleted = false GROUP BY memory_type ORDER BY count DESC"
        ))
        print("\n=== 按 memory_type ===")
        for row in r.all():
            pct = row[1] / total * 100 if total else 0
            print(f"  {row[0]}: {row[1]} ({pct:.0f}%)")

        # by category
        r = await db.execute(text(
            "SELECT category, COUNT(*) FROM memories WHERE is_deleted = false GROUP BY category ORDER BY count DESC"
        ))
        print("\n=== 按 category ===")
        for row in r.all():
            pct = row[1] / total * 100 if total else 0
            print(f"  {row[1]:<4} {row[0]}")

        # 对话统计
        r = await db.execute(text("""
            SELECT c.id, c.title, COUNT(m.id)
            FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id ORDER BY COUNT(m.id) DESC
        """))
        print("\n=== 对话统计 ===")
        for row in r.all():
            title = row[1] or "(无标题)"
            print(f"  对话 {str(row[0])[:8]}... 标题: {title[:30]:<30} 消息: {row[2]}")

        # 提取次数
        r = await db.execute(text(
            "SELECT extraction_count, last_extraction_msg FROM conversations"
        ))
        print("\n=== 提取进度 ===")
        for row in r.all():
            print(f"  extraction_count: {row[0]}, last_extraction_msg: {row[1]}")

        # 记忆示例 (每种 memory_type 各取 5 条)
        for mtype in ("fact", "event", "state"):
            r = await db.execute(text(
                "SELECT content, category, importance FROM memories WHERE is_deleted = false AND memory_type = :mt LIMIT 5"
            ), {"mt": mtype})
            rows = r.all()
            if rows:
                print(f"\n=== {mtype} 示例 ===")
                for row in rows:
                    print(f"  [{row[1]:<18} imp={row[2]:.1f}] {row[0]}")

        # 全部记忆
        r = await db.execute(text(
            "SELECT content, category, memory_type, importance FROM memories WHERE is_deleted = false ORDER BY category, memory_type"
        ))
        print("\n=== 全部记忆 ===")
        for row in r.all():
            print(f"  [{row[2]:<6} {row[1]:<18} imp={row[3]:.1f}] {row[0]}")


if __name__ == "__main__":
    asyncio.run(main())
