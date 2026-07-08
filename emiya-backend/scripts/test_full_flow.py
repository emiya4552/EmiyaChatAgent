"""模拟 chat_service.py 的完整流程，检查 final_state 是否正确构造。"""
import asyncio
from uuid import UUID
from app.database import AsyncSessionLocal
from app.services.langgraph.chat_graph import build_analysis_graph
from app.services.langgraph.state import ChatState
from app.services.langgraph.nodes import node_post_process
from app.models.conversation import Conversation
from app.models.message import Message
from sqlalchemy import text, select

async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT c.id, c.user_id, c.persona_id, c.current_mood, c.mood_intensity
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id HAVING COUNT(m.id) >= 10
            LIMIT 1
        """))
        row = r.one_or_none()
        if not row:
            print("无可用对话")
            return
        conv_id, user_id, persona_id, mood, mood_intensity = row
        print(f"conv={conv_id}, user={user_id}")

        r = await db.execute(text("""
            SELECT content FROM messages
            WHERE conversation_id = :cid AND role = 'user'
            ORDER BY created_at DESC LIMIT 1
        """), {"cid": conv_id})
        last_msg = r.scalar()
        content = last_msg or "test"
        print(f"msg={content[:40]}...")

    # === 模拟 chat_service.py 的完整流程 ===
    initial_state: ChatState = {
        "conversation_id": conv_id,
        "user_id": user_id,
        "persona_id": persona_id,
        "user_message": content,
        "emotion": None,
        "emotion_intensity": 5,
        "emotion_confidence": 0.3,
        "emotion_triggers": [],
        "current_mood": mood,
        "mood_intensity": mood_intensity,
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
        "assistant_reply": "",
        "new_memories_count": 0,
        "is_first_round": False,
        "error": None,
    }

    # Step 1: 运行分析 graph
    graph = build_analysis_graph()
    final_state: dict = dict(initial_state)
    node_events = []
    try:
        async for chunk in graph.astream(initial_state, stream_mode="updates"):
            for node_name, node_output in chunk.items():
                node_events.append(node_name)
                final_state.update(node_output)
    except Exception as e:
        print(f"graph 执行失败: {e}")
        return

    print(f"\n节点完成: {node_events}")
    print(f"final_state keys: {sorted(final_state.keys())}")

    # Step 2: 提取 messages
    messages = final_state.get("messages") or []
    print(f"messages 数量: {len(messages)}")
    if messages:
        print(f"messages[0] role: {messages[0].get('role')}")

    # Step 3: 模拟流式回复（用固定文本代替真实 stream）
    fake_reply = "这是通过完整流程测试生成的AI回复。"
    final_state["assistant_reply"] = fake_reply
    print(f"assistant_reply: {fake_reply}")

    # Step 4: 调用 node_post_process
    print("\n调用 node_post_process...")
    try:
        result = await node_post_process(final_state)
        print(f"成功: {result}")

        # 验证
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("""
                SELECT role, LEFT(content, 60) FROM messages
                WHERE conversation_id = :cid
                ORDER BY created_at DESC LIMIT 3
            """), {"cid": conv_id})
            print("\n验证 - 最新 3 条消息:")
            for row in r.all():
                print(f"  [{row[0]:<10}] {row[1]}")

    except Exception as e:
        import traceback
        print(f"失败: {type(e).__name__}: {e}")
        traceback.print_exc()

        # 检查哪些关键字段缺失
        required = ["conversation_id", "user_id", "assistant_reply", "user_message"]
        for k in required:
            print(f"  final_state[{k!r}] = {final_state.get(k, 'MISSING!')!r}")

asyncio.run(main())
