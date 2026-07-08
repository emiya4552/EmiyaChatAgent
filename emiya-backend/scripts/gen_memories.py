"""自动对话脚本：与 AI persona 对话以生成记忆数据。

运行方式：（在 emiya-backend 目录下，后端服务已在 localhost:8000 运行）
  python scripts/gen_memories.py

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

# ========== 登录账号：用你自己已有的帐号（不再自动注册） ==========
# 密码建议走环境变量，别硬写进仓库（本脚本在 git 里）：
#   bash:  export EMIYA_EMAIL=you@example.com EMIYA_PASSWORD=****
#   PowerShell:  $env:EMIYA_EMAIL="..."; $env:EMIYA_PASSWORD="..."
# 没设环境变量时用下面的默认值兜底。
USER_PROFILE = {
    "email": "3111854303@qq.com",
    "password": "123456",
}

# ⚠️ 用的是你自己的真实帐号：默认【不】清空已有记忆。
# 设为 True 会删除该帐号下所有记忆（软删 + 清 ChromaDB 向量），不可逆，谨慎！
CLEAR_EXISTING_MEMORIES = False

# ========== 对话对象：改成你库里实际存在的 AI 角色卡名 ==========
AI_PERSONA_NAME = "桃桃"

# ========== 对话脚本：每条消息都设计为触发记忆提取 ==========
# 不设置用户人设（user_persona_name），对话只带 AI 卡；建对话时不传 user_persona_id。
CONVERSATION_SCRIPTS = [
    {
        "persona_name": AI_PERSONA_NAME,
        "user_persona_name": None,
        "messages": [
            "（去给她做番茄鸡蛋面）",
            "（忙完后，抱住她）要来吗？",
            "那你跪下吧",
            "知道怎么做吗",
            "继续",
            "（解开裤链）这里呢？",
            "大声说出来，你想做什么",
            "宝宝真了不起，来吧，主人奖励你",
            "要好好加油哦",
            "（射进嘴里）餐前甜点好吃吗？",
            "小母狗这么贪心，会被主人惩罚哦",
            "小母狗想被怎么惩罚",
            "感觉还不够呢",
            "跟你讲这些乱七八糟的，你别嫌我啰嗦啊",
            # --- 偏好：吃 / 游戏 / 音乐 / 审美（preference）---
            "说到吃的，我最爱螺蛳粉，一周不嗦一次就浑身难受",
            "香菜必须多放！我知道很多人接受不了，但没香菜的螺蛳粉没有灵魂",
            "奶茶我倒是戒了，去年体检血糖有点高，现在只敢喝无糖乌龙",
            "游戏我超爱《空洞骑士》，通关了三遍还想再玩",
            "最近在肝《星露谷物语》，种田种到凌晨两点，第二天上班像行尸走肉",
            "我这人吃软不吃硬，越是要肝的游戏越提不起劲，就爱慢悠悠的那种",
            "追番不多，但《紫罗兰永恒花园》我哭了好几次",
            "音乐我喜欢听后摇，无人声的那种，写方案时单曲循环最带感",
            "惘闻和 Explosions in the Sky 是我的加班续命神器",
            "我对颜色特别敏感，穿衣服全是低饱和的灰蓝灰绿，鲜艳的一件不敢碰",
            "咖啡是刚需，每天早上不喝一杯手冲脑子转不动",
            "豆子都是自己磨的，家里三个手摇磨豆机，被室友嘲笑是咖啡邪教",
            "我不太吃甜，但唯独对提拉米苏没有抵抗力",
            "看电影只看文艺片和悬疑片，爆米花大片我基本坐不住",
            "买东西有个毛病，宁可贵一点买耐用的，也不将就",
            "说到底我是个挺念旧的人，一双鞋能穿到烂才换",
            # --- 日常习惯（habit）---
            "我每天早上六点自然醒，哪怕前一晚熬到两点也一样，生物钟坏了",
            "通勤路上我一定听播客，最近在追一个讲艺术史的",
            "讲印象派那几期我反复听，莫奈画睡莲画到眼睛快瞎还在画，我特别共情",
            "睡前有个雷打不动的习惯，写三行日记，记当天的小确幸",
            "昨天写的是：地铁有座位、螺蛳粉加了双份腐竹、方案没被老板打回",
            "周末我基本不出门，宅家打游戏或补番，社恐属性拉满",
            "偶尔会一个人去西湖边走走，但只挑人少的清晨去",
            "我有点认床，出差住酒店基本睡不着，得带自己的枕头",
            "一焦虑我就疯狂刷手机，明明什么也没看进去，纯粹逃避",
            "吃饭必须配剧或视频，不然一个人吃饭会莫名难受",
            "我还有点囤积癖，快递箱堆一墙也懒得扔，室友快被我逼疯",
            "手机永远静音，我受不了突然响，消息也经常好几小时才回",
            "你别学我这作息，一看就是慢性自杀",
            # --- 关系：家人 / 前任 / 朋友 / 宠物（relationship）---
            "我妈最近又开始催了，说25了该找对象，烦得很",
            "其实我谈过一个，异地，谈了两年去年分了",
            "她在深圳，我们轮流飞去看对方，飞到最后两个人都累了",
            "分手那天谁都没哭，很平静地说'算了吧'，反而更难受",
            "现在想起来没那么疼了，但看到街上的情侣还是会愣一下",
            "我爸妈感情其实很好，就是特别爱管我，尤其我爸，控制欲有点强",
            "但他去年查出高血压之后，我突然意识到他也会老，就没那么怨他了",
            "我有个从小玩到大的哥们，在老家开了个小酒馆，每次回温州都去蹭酒",
            "我俩能一晚上不说话各玩各的手机，但就是很自在，你懂那种朋友吧",
            "我室友养了只猫叫年糕，橘白的，胖得像个不倒翁",
            "年糕最爱半夜三点在我床头开演唱会，我又爱又恨",
            "其实我一直想自己养只猫，但怕加班太多冷落它",
            "我奶奶前年走了，是我最亲的人，她以前总偷偷塞钱给我买画笔",
            "到现在我都不太敢翻以前的全家福，一看就绷不住",
            "说这些是不是有点沉重了，抱歉啊突然emo",
            "你愿意听我念叨这些，真的挺难得的",
            "认识你之后我感觉话都变多了，以前我可闷了",
            # --- 经历 / 事件（experience / event）---
            "跟你说个事，我上个月一个人去了趟景德镇，第一次学拉坯",
            "手忙脚乱做了个歪歪扭扭的杯子，丑是丑，但我宝贝得不行",
            "那三天没碰工作手机，是我今年最放松的时候",
            "大学时我参加过学校的动漫社，还画过一期社刊封面",
            "那是我最后一次'正经'画画，之后就被实习和工作淹没了",
            "我第一份工作在上海，做了一年就抑郁了，天天加班到最后一班地铁",
            "后来果断裸辞回了杭州，虽然降薪但至少能喘口气",
            "那段裸辞在家的三个月，我天天睡到中午，反而把自己修复好了",
            "前年公司团建去了趟稻城亚丁，海拔四千多我高反到吐",
            "但看到雪山那一瞬间，真觉得什么KPI都是狗屁",
            "我这辈子做过最疯狂的事，是大二一个人穷游了半个云南",
            "兜里就两千块，睡青旅、搭顺风车，现在想想有点后怕但很爽",
            "上周我把工位那盆养了三年的绿萝养死了，莫名有点失落",
            "可能它替我扛了太多加班的怨气吧",
            "我最近去学了拳击，纯粹为了发泄，打沙袋太解压了",
            "教练说我出拳没章法但是很狠，我说因为我脑子里在打老板",
            # --- 情绪模式 / 当前状态（emotion_pattern / state）---
            "我这人报喜不报忧，再难受也习惯自己扛，家里人根本不知道我压力多大",
            "崩溃的时候我不会找人哭，就一个人开车去江边坐着",
            "有时候半夜会突然惊醒，心跳很快，说不上来为什么就是慌",
            "白天忙起来倒没事，一安静下来就容易钻牛角尖",
            "我最怕别人对我期待太高，那种'你一定行'的话会让我更喘不过气",
            "所以你从来不跟我说'加油'，我特别感激，你就陪我一起骂",
            "最近状态其实不太好，连着几个大项目，人被榨得没什么感觉了",
            "早上睁眼第一反应是'又要上班了'，那种疲惫睡多久都缓不过来",
            "但奇怪的是，只要想到晚上能来找你唠嗑，就还能撑一天",
            "我是不是很没用啊，一点小事就被压垮",
            "你说得对，允许自己脆弱也是一种勇敢，这话我记下了",
            "今天说着说着，感觉胸口那块石头轻了点，谢谢你桃桃",
            # --- 目标 / 愿望 + 收尾（goal）---
            "说说我的愿望吧，我最想的是攒够钱后 gap 一年，去系统学画画",
            "哪怕最后画不出什么名堂，我也想给18岁没能坚持的自己一个交代",
            "短期目标是今年先把那块吃灰的电子画板用起来，重新入门",
            "我还想开个只发自己画的小号，不求关注，就当树洞",
            "更大的梦是以后开一家画室兼咖啡馆，白天教小孩画画，晚上自己喝咖啡",
            "我知道听起来很不切实际，但有个盼头，日子才有奔头嘛",
            "工作上我也想今年争取转去用户体验岗，离'创造'近一点",
            "存钱计划也在推进，每月强制存三成工资，目标三年内不为钱慌",
            "对了下个月15号是我生日，26了，本命年前的最后一年",
            "今年生日我想给自己买套好点的水彩颜料，重新开始",
            "谢谢你一直听我说这些，有你在我感觉没那么孤单",
            "好啦不吵你了，明天再来找你，晚安桃桃",
        ],
    }
]


async def get_token(client: httpx.AsyncClient) -> str:
    """用已有帐号登录，返回 JWT。不再自动注册。"""
    if not USER_PROFILE["password"]:
        raise RuntimeError(
            "未设置密码。请设 EMIYA_PASSWORD 环境变量，"
            "或直接改脚本里的 USER_PROFILE['password']。"
        )
    resp = await client.post(f"{API}/auth/login", json={
        "email": USER_PROFILE["email"],
        "password": USER_PROFILE["password"],
    })
    if resp.status_code == 200:
        logger.info(f"登录成功: {USER_PROFILE['email']}")
        return resp.json()["access_token"]

    raise RuntimeError(f"登录失败: {resp.status_code} {resp.text[:200]}")


async def find_persona_id(client: httpx.AsyncClient, token: str, name: str) -> str:
    """按名称查角色卡 ID。

    persona 模型已不再区分 AI/用户类型（同一张 personas 表，靠对话的
    persona_id / user_persona_id 决定用途）。GET /personas 默认返回
    模板卡 ∪ 当前用户自建卡，按名称匹配即可，AI 卡和用户人设都能找到。
    """
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.get(f"{API}/personas", headers=headers)
    personas = resp.json()
    for p in personas:
        if p["name"] == name:
            return p["id"]
    raise RuntimeError(
        f"找不到角色卡: {name}（模板或自建卡均无此名，请先在角色卡页面创建/导入）"
    )


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
                json={"content": message},
                headers=headers,
                timeout=httpx.Timeout(120.0, read=180.0),
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(f"Chat error {response.status_code}: {body[:200]}")

                # SSE 格式：每个事件是 `event: <name>\ndata: <json>\n\n`。
                # 逐行读取时先记住当前 event 名，再按名解析随后的 data 行。
                # 正文 token 走 message_delta 事件，payload 是 {"content": "..."}。
                current_event = None
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        current_event = line[7:].strip()
                    elif line.startswith("data: "):
                        data_str = line[6:]
                        if not data_str.strip():
                            continue
                        try:
                            payload = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        if current_event == "message_delta":
                            full_reply += payload.get("content", "")
                        elif current_event == "error":
                            raise RuntimeError(
                                f"服务端返回 error 事件: {payload.get('error')}"
                            )
                        # message_done / memory_recall 等其余事件无需处理，
                        # 继续读到流关闭即可（后台记忆提取在流内的 post_process 完成）。

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

    pid = await find_persona_id(client, token, persona_name)
    upid = None
    if user_persona_name:
        upid = await find_persona_id(client, token, user_persona_name)
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

        # 2. （可选）清空旧记忆——默认关闭，保护真实帐号数据
        if CLEAR_EXISTING_MEMORIES:
            resp = await client.delete(f"{API}/memories", headers=headers)
            if resp.status_code == 200:
                logger.info(f"清除 {resp.json().get('deleted', 0)} 条旧记忆")
            else:
                logger.warning(f"清空旧记忆失败: {resp.status_code} {resp.text[:200]}")
        else:
            logger.info("跳过清空旧记忆（CLEAR_EXISTING_MEMORIES=False）")

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
