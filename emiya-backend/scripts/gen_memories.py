"""自动对话脚本：与 AI persona 对话以生成记忆数据。

运行方式：python -m app.scripts.generate_memories

工作原理：
1. 登录获取 token
2. 创建对话（选择 AI persona）
3. 发送多轮预编排的"用户消息"，模拟真实用户透露个人信息
4. 每轮消息间短暂等待，让后台记忆提取有足够触发机会
5. 报告生成的记忆数量

编排的消息覆盖 7 个记忆分类：
  basic_info, preference, experience, habit, emotion_pattern, relationship, goal
以及 3 个 memory_type：fact, event, state
"""
import asyncio
import json
import logging
import os
import sys
from uuid import UUID

import httpx

# 确保项目根在 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE = "http://localhost:8000"
API = f"{BASE}/api/v1"

# ========== 模拟用户账号 ==========
USER_PROFILE = {
    "name": "小明",
    "email": "test_user_2026@example.com",
    "password": "emiya_test_2026",
}

# ========== 对话脚本：每条消息都设计为触发记忆提取 ==========
# 格式：(message, 预期产生的记忆类型)
CONVERSATION_SCRIPTS = [
    {
        "persona_name": "小暖",
        "user_persona_name": "废柴大学生",
        "messages": [
            "嗨小暖~ 最近好累啊，工作上的事情忙不完",
            "我在北京一家互联网公司，做后端的，每天996真要命",
            "最烦的是产品经理老改需求，昨天又让我重写整个模块",
            "还好我养了一只橘猫叫咪咪，回家撸猫是最治愈的事了",
            "咪咪是我去年在小区楼下捡的，当时才巴掌大，现在胖得像个球",
            "说到吃的，我特别喜欢芋泥波波奶茶，每周至少喝两次",
            "虽然知道糖分超标但是真的控制不住哈哈哈",
            "对了，我是四川人，在成都长大的，来北京五年了",
            "北京气候好干燥，刚来的时候天天流鼻血",
            "我其实挺想家的，想念成都的火锅和串串",
            "最近爸妈老催我找女朋友，烦死了",
            "其实我之前谈过一个，分手一年了，她嫌我太忙没时间陪她",
            "说起来还是有点难过，毕竟是大学就开始的",
            "大学在广州读的，那时候经常和她一起去珠江边散步",
            "我现在最大的愿望就是能跳槽去一家WLB好点的公司",
            "收入够用就行，真的不想再过这种把自己榨干的日子了",
            "有时候半夜醒来突然觉得人生好迷茫",
            "不过白天忙起来就忘了，大概就是大家说的社畜生存法则吧",
            "周末我喜欢一个人去爬香山，走到山顶吹吹风感觉好多了",
            "或者窝在家里打游戏，最近在肝原神，已经氪了两千多了",
            "我一个朋友说我这是在用氪金填补空虚哈哈哈",
            "他说的可能也有道理，但我选择不听",
            "好了不说了，该去写那个该死的周报了",
            "对了，下周是我生日，不过估计也没什么特别的，照常加班",
            "谢谢你听我唠叨这么多呀，说了好多乱七八糟的",
            # --- 补充至 50 条 ---
            "对了小暖，我最近开始跑步了，每天早上六点起来跑三公里",
            "坚持了大概两周吧，感觉自己精神确实好了一点",
            "跑步的时候会听播客，最近迷上了忽左忽右那个节目",
            "尤其是讲历史的那几期，听得我停不下来，原来战国史这么有趣",
            "以前历史课都白上了，现在才知道那些故事多精彩",
            "说起来我其实很喜欢听别人讲故事，小时候就爱缠着我外婆讲",
            "我外婆是湖南人，她讲的很多湘西民间故事我现在还记得",
            "比如什么落花洞女啊、赶尸之类的，吓得我晚上睡不着哈哈",
            "不过我外婆去年走了，家里最后一个长辈也不在了",
            "现在想起她做的剁椒鱼头还是会流口水，那个味道再也吃不到了",
            "人长大了就是不断失去的过程吧，但还好有新的事情进来",
            "比如我最近开始学做饭了，上周末做了个回锅肉，居然还能吃",
            "我觉得做饭挺解压的，切菜的时候脑子可以放空",
            "下个目标是想学会做钵钵鸡，这样就不用老馋成都的味道了",
            "我还买了个kindle，想重新养成看书的习惯",
            "最近在看三体，虽然之前看过剧，但书真的比剧震撼太多了",
            "大刘的脑洞简直了，黑暗森林法则让我想了好几天",
            "我发现自己其实挺喜欢科幻的，以前怎么没发现",
            "可能因为工作把脑子都占满了吧，根本没有余裕去想别的",
            "有时候觉得人被工作异化这件事是真的，渐渐变成了一颗螺丝钉",
            "但我最近在想，也许螺丝钉也可以有自己的小宇宙",
            "就是那种'白天打工晚上写诗'的感觉，你觉得呢？",
            "我最近还开始写日记了，不是什么正经日记，就是每天睡前列三个小确幸",
            "昨天列的是：咪咪踩奶了、代码没出bug、食堂的红烧肉很好吃",
            "好了真的不说了，奶茶到了，芋泥波波我来啦~",
            # --- 补充至 100 条：深化已有话题 + 拓展新领域 ---
            "小暖我又来了！今天心情不错，因为终于把那个烂尾项目交付了",
            "产品经理居然没挑刺，我怀疑他被夺舍了哈哈",
            "不过下周要开始新项目了，说是要用Go重构老系统",
            "我只写过Python和Java，Go完全没碰过，有点慌",
            "买了一本《Go语言程序设计》周末开始啃，感觉回到了大学",
            "说到大学，前几天翻到老照片，看到我和前女友在图书馆拍的合照",
            "那时候两个人都好嫩啊，她戴着我送的发卡笑得特别好看",
            "愣了一下，但没有以前那种难受的感觉了，可能是真的过去了吧",
            "朋友说我该开始新的感情了，给我介绍了个妹子",
            "聊了两天发现她喜欢村上春树，我也喜欢，但她说喜欢《挪威的森林》，我更爱《世界尽头与冷酷仙境》",
            "因为这事争论了一晚上，她说我太较真了哈哈",
            "不过她人挺好的，在望京一家设计公司做UI，养了两只布偶猫",
            "约了周末一起去猫咖，感觉又紧张又期待",
            "对了说到猫，咪咪最近变懒了，天天趴在我键盘上",
            "我怀疑它是故意的，每次我加班它就往键盘上一躺",
            "带它去宠物医院体检，医生说有点超重，让我控制饮食",
            "现在每天只给两顿，它看我的眼神充满了怨恨",
            "不过它还是很粘人，我做饭的时候它就蹲在厨房门口看着我",
            "上周末尝试做了麻婆豆腐，按照我妈视频指导弄的",
            "结果花椒放多了，吃了一口嘴唇麻了半小时",
            "我妈笑得不行，说我果然不是做饭的料",
            "不过她说能在北京自己做川菜已经很了不起了",
            "我妈最近开始学用智能手机了，天天在家族群发养生文章",
            "什么《震惊！这五种食物不能一起吃》《睡前做这三个动作活到99》",
            "我每次都要去辟谣，累死了，但看到她学会发语音又觉得挺可爱的",
            "我爸倒是很淡定，每天就是下棋打太极，话少得像换了个人",
            "上周我爸突然给我打电话，问我'北京冷不冷多穿点'，就这一句",
            "挂了电话我愣了好久，他一年说的话加起来可能都没有我妈一天多",
            "跑步坚持一个月了，配速从七分半提到了六分四十",
            "体重降了四斤，但奶茶还是戒不掉，功过相抵吧",
            "最近还加了个跑步群，周末一起去奥森跑五公里",
            "群里有个大爷六十五岁了，全马三小时半，我看完沉默了",
            "上周跑完大家一起吃早餐，发现这群人什么职业都有：律师、理发师、外卖小哥",
            "突然觉得北京也不是那么冷冰冰的，只是我以前把自己关得太死了",
            "播客最近在听《随机波动》，三个女主播聊社会话题，特别有共鸣",
            "有期讲'三十岁的焦虑'，说到父母的期待、职场的瓶颈、自我价值的迷茫",
            "听到一半我在跑步机上差点停下来鼓掌",
            "最近还在B站看了一个讲魏晋南北朝历史的UP主",
            "以前觉得那段历史很乱，看完发现其实特别浪漫——竹林七贤那种'我就是不想上班'的精神",
            "阮籍穷途之哭，我加班到凌晨的时候也想哭",
            "三体看完了，最后一部结局让我发了好久的呆",
            "程心这个角色争议很大，但我觉得大刘其实是在问：善意能不能拯救宇宙？",
            "看完以后买了《球状闪电》和《超新星纪元》，准备继续刷",
            "发现自己居然能静下心看书了，大学的时候除了考试教材什么都不翻",
            "可能真的是因为现在做的事不是自己喜欢的，所以需要精神避难所",
            "说到这个，AI转行的简历我已经投了快二十家了",
            "有三家给了面试，两家挂了，还有一家下周终面，是做AI医疗影像的",
            "我觉得这个方向很有意义，用深度学习辅助医生看X光片，如果能帮到那些在县城医院看病的人就好了",
            "外婆如果在天有灵应该会支持我的选择吧，她以前最心疼我看病难了",
            "好了，今晚该去写Go的helloworld了，程序员的一生就是不停的helloworld",
        ],
    }
]


async def get_token(client: httpx.AsyncClient) -> str:
    """登录或注册，返回 JWT 认证头。"""
    # 先尝试登录
    resp = await client.post(f"{API}/auth/login", json={
        "email": USER_PROFILE["email"],
        "password": USER_PROFILE["password"],
    })
    if resp.status_code == 200:
        logger.info("登录成功")
        return resp.json()["access_token"]

    # 注册
    resp = await client.post(f"{API}/auth/register", json={
        "email": USER_PROFILE["email"],
        "password": USER_PROFILE["password"],
        "nickname": USER_PROFILE["name"],
    })
    if resp.status_code in (200, 201):
        logger.info("注册成功")
        return resp.json()["access_token"]

    raise RuntimeError(f"登录/注册失败: {resp.status_code} {resp.text}")


async def get_persona_id(client: httpx.AsyncClient, token: str, name: str) -> str:
    """根据名称找 AI persona ID。"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{API}/personas", params={"type": "ai"}, headers=headers)
    personas = resp.json()
    for p in personas:
        if p["name"] == name:
            return p["id"]
    raise RuntimeError(f"找不到 AI persona: {name}")


async def get_user_persona_id(client: httpx.AsyncClient, token: str, name: str) -> str:
    """根据名称找用户 persona ID（type=user）。"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{API}/personas", params={"type": "user"}, headers=headers)
    personas = resp.json()
    for p in personas:
        if p["name"] == name:
            return p["id"]
    raise RuntimeError(f"找不到用户 persona: {name}。请先在 /personas/create 页面创建")


async def create_conversation(
    client: httpx.AsyncClient, token: str, persona_id: str,
    user_persona_id: str | None = None,
) -> str:
    """创建对话，返回 conversation_id。"""
    headers = {"Authorization": f"Bearer {token}"}
    body: dict = {"persona_id": persona_id}
    if user_persona_id is not None:
        body["user_persona_id"] = user_persona_id
    resp = await client.post(f"{API}/conversations", json=body, headers=headers)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"创建对话失败: {resp.status_code} {resp.text}")
    conv = resp.json()
    logger.info(f"  创建对话: {conv['id'][:8]}... (persona={conv.get('persona_name', '?')})")
    return conv["id"]


async def send_message(
    client: httpx.AsyncClient, token: str, conversation_id: str, message: str,
    max_retries: int = 3,
) -> str:
    """发送消息并收集 SSE 回复，返回 AI 回复文本。支持超时重试。"""
    headers = {"Authorization": f"Bearer {token}"}
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            full_reply = ""
            async with client.stream(
                "POST", f"{API}/conversations/{conversation_id}/chat",
                json={
                    "conversation_id": conversation_id,
                    "content": message,
                },
                headers=headers,
                timeout=httpx.Timeout(120.0, read=180.0),
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(f"Chat error {response.status_code}: {body[:200]}")

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() in ("[DONE]", ""):
                            continue
                        try:
                            event = json.loads(data_str)
                            if event.get("type") == "token":
                                full_reply += event.get("content", "")
                        except json.JSONDecodeError:
                            continue

            return full_reply

        except (httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt  # 指数退避: 2s, 4s, 8s
                logger.warning(f"  [超时重试 {attempt}/{max_retries}] 等待 {wait}s...")
                await asyncio.sleep(wait)
            else:
                raise RuntimeError(
                    f"消息发送失败 (重试{max_retries}次): {e}"
                ) from e


async def count_memories(client: httpx.AsyncClient, token: str) -> int:
    """查当前记忆总数。"""
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{API}/memories", params={"limit": 1}, headers=headers)
    return resp.json().get("total", 0)


async def run_script(script: dict, client: httpx.AsyncClient, token: str):
    """执行一个对话脚本。"""
    persona_name = script["persona_name"]
    user_persona_name = script.get("user_persona_name")
    messages = script["messages"]
    logger.info(f"\n{'='*60}")
    user_info = f", 用户人设={user_persona_name}" if user_persona_name else ""
    logger.info(f"开始对话: persona={persona_name}{user_info}, 消息数={len(messages)}")
    logger.info(f"{'='*60}")

    pid = await get_persona_id(client, token, persona_name)
    upid = None
    if user_persona_name:
        upid = await get_user_persona_id(client, token, user_persona_name)
    cid = await create_conversation(client, token, pid, upid)

    before = await count_memories(client, token)
    logger.info(f"  当前记忆数: {before}")

    for i, msg in enumerate(messages, 1):
        reply = await send_message(client, token, cid, msg)
        preview = reply[:60].replace("\n", " ") + ("..." if len(reply) > 60 else "")
        logger.info(f"  [{i}/{len(messages)}] {msg[:40]}... → {preview}")

        # 消息间短暂等待，避免请求过于密集
        await asyncio.sleep(0.3)

    # 等待后台记忆提取完成
    logger.info("  等待后台记忆提取...")
    await asyncio.sleep(5.0)

    after = await count_memories(client, token)
    logger.info(f"  生成新记忆: {after - before} 条 (总记忆: {after})")


async def main():
    logger.info("=" * 60)
    logger.info("自动记忆数据生成器")
    logger.info("=" * 60)

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=120.0)) as client:
        # 1. 获取 token
        auth_token = await get_token(client)
        headers = {"Authorization": f"Bearer {auth_token}"}

        # 2. 清空旧记忆（从零开始）
        resp = await client.get(f"{API}/memories", params={"limit": 200}, headers=headers)
        old_memories = resp.json().get("items", [])
        if old_memories:
            logger.info(f"清除 {len(old_memories)} 条旧记忆...")
            for m in old_memories:
                await client.delete(f"{API}/memories/{m['id']}", headers=headers)
            logger.info("旧记忆已清除")

        # 3. 运行所有对话脚本
        total_before = await count_memories(client, auth_token)
        for i, script in enumerate(CONVERSATION_SCRIPTS, 1):
            logger.info(f"\n{'#'*60}")
            logger.info(f"# 脚本 {i}/{len(CONVERSATION_SCRIPTS)}")
            logger.info(f"{'#'*60}")
            await run_script(script, client, auth_token)

        total_after = await count_memories(client, auth_token)
        logger.info(f"\n{'='*60}")
        logger.info(f"全部完成！总共生成 {total_after - total_before} 条新记忆")
        logger.info(f"当前记忆总数: {total_after}")
        logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
