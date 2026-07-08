"""测试 node_post_process 直接调用是否正常。"""
import asyncio
from uuid import UUID, uuid4
from app.database import AsyncSessionLocal
from app.services.langgraph.nodes import node_post_process
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        # 找一个有消息的对话
        r = await db.execute(text("""
            SELECT c.id, c.user_id, c.persona_id
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id HAVING COUNT(m.id) >= 10
            LIMIT 1
        """))
        row = r.one_or_none()
        if not row:
            print("没有找到有足够消息的对话")
            return
        conv_id, user_id, persona_id = row
        print(f"测试对话: {conv_id}, 用户: {user_id}")

        # 查最后一条 user 消息
        r = await db.execute(text("""
            SELECT content FROM messages
            WHERE conversation_id = :cid AND role = 'user'
            ORDER BY created_at DESC LIMIT 1
        """), {"cid": conv_id})
        user_msg = r.scalar()
        print(f"最后用户消息: {user_msg[:50] if user_msg else 'N/A'}...")

    # 构造 state 模拟 chat_service 的行为
    test_state = {
        "conversation_id": conv_id,
        "user_id": user_id,
        "persona_id": persona_id,
        "user_message": user_msg or "test message",
        "assistant_reply": "这是一个测试回复，用于验证 node_post_process 直接调用。",
        "emotion": "开心",
        "emotion_intensity": 7,
        "emotion_confidence": 0.8,
        "emotion_triggers": ["test"],
        "current_mood": None,
        "mood_intensity": None,
        "recalled_memories": [],
        "profile": None,
        "profile_section": "",
        "relationship": None,
        "relationship_section": "",
        "relationship_level": 0,
        "level_changed": False,
        "new_milestone": None,
        "system_prompt": "",
        "messages": [],
        "persona_name": None,
        "is_first_round": False,
        "error": None,
        "new_memories_count": 0,
    }

    print(f"\n调用 node_post_process...")
    print(f"  conv_id: {test_state['conversation_id']}")
    print(f"  user_id: {test_state['user_id']}")
    print(f"  reply_len: {len(test_state['assistant_reply'])}")
    print(f"  state_keys: {sorted(test_state.keys())}")

    try:
        result = await node_post_process(test_state)
        print(f"\n成功! 返回: {result}")

        # 验证消息是否写入
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("""
                SELECT role, LEFT(content, 60) FROM messages
                WHERE conversation_id = :cid
                ORDER BY created_at DESC LIMIT 3
            """), {"cid": conv_id})
            print("\n最新 3 条消息:")
            for row in r.all():
                print(f"  [{row[0]:<10}] {row[1]}")

    except Exception as e:
        import traceback
        print(f"\n失败! {type(e).__name__}: {e}")
        traceback.print_exc()

asyncio.run(main())
