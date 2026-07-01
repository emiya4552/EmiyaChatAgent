# -*- coding: utf-8 -*-
"""角色卡导入/导出服务：PNG tEXt chunk 解析 + 版本兼容。"""
import base64
import io
import json
import re
import struct
from datetime import datetime

# 从 creator_notes 抽 <style>...</style> 块（兜底路径，详见 docs/adr/0008）
_STYLE_BLOCK_RE = re.compile(
    r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL,
)


def _detect_mvu(data: dict) -> bool:
    """检测此卡是否使用 MVU 系统（详见 ADR-0010）。

    判定：extensions.tavern_helper.scripts 中存在
      (a) name == "MVU"，或
      (b) content 中含 "MagVarUpdate" / "registerMvuSchema" 等关键串

    命中即视为 MVU 卡，导入侧据此标记 persona.uses_mvu。
    """
    ext = data.get("extensions") or {}
    if not isinstance(ext, dict):
        return False
    th = ext.get("tavern_helper")
    if not isinstance(th, dict):
        return False
    scripts = th.get("scripts") or []
    if not isinstance(scripts, list):
        return False
    needles = ("MagVarUpdate", "registerMvuSchema", "mvu_zod")
    for sc in scripts:
        if not isinstance(sc, dict):
            continue
        if (sc.get("name") or "").strip().upper() == "MVU":
            return True
        content = sc.get("content") or ""
        if isinstance(content, str) and any(n in content for n in needles):
            return True
    return False


def _extract_css_theme(data: dict) -> str | None:
    """按优先级抽取卡作者带的 CSS 主题。

    路径：extensions.css → extensions.style → creator_notes 内嵌 <style>。
    都没命中返回 None。
    """
    ext = data.get("extensions") or {}
    if isinstance(ext, dict):
        for key in ("css", "style"):
            val = ext.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

    notes = data.get("creator_notes") or ""
    if notes and isinstance(notes, str):
        blocks = _STYLE_BLOCK_RE.findall(notes)
        if blocks:
            # 多个 <style> 块顺序拼接（卡里偶有多块）
            joined = "\n\n".join(b.strip() for b in blocks if b.strip())
            if joined:
                return joined
    return None


def _normalize_tags(tags) -> list | None:
    """确保 tags 是字符串列表。兼容 v1 的逗号分隔字符串格式。"""
    if tags is None:
        return None
    if isinstance(tags, list):
        return [str(t) for t in tags if t]
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(',') if t.strip()]
    return None


class CardParser:
    """角色卡 PNG / JSON 解析器。对齐 ST 源码 character-card-parser.js 逻辑。"""

    @staticmethod
    def parse_png(file_bytes: bytes) -> dict:
        """从 PNG 二进制中提取角色卡 JSON (tEXt chunk keyword=ccv3/chara)。"""
        stream = io.BytesIO(file_bytes)
        if stream.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ValueError("不是有效的 PNG 文件")

        TEXT_CHUNK = b'tEXt'
        candidates: list[tuple[str, str]] = [] # 存放候选数据

        while True:
            header = stream.read(8)
            if len(header) < 8:
                break
            length = struct.unpack('>I', header[:4])[0]
            ctype = header[4:8]
            data = stream.read(length) if length > 0 else b''
            stream.read(4)  # CRC

            if ctype == TEXT_CHUNK:
                null_idx = data.find(b'\x00')
                if null_idx == -1:
                    continue
                keyword = data[:null_idx].decode('latin-1')
                text = data[null_idx + 1:].decode('latin-1')
                kw_lower = keyword.lower()
                if kw_lower in ('ccv3', 'chara'):
                    candidates.append((kw_lower, text))

            if ctype == b'IEND':
                break

        if not candidates:
            raise ValueError("PNG 中未找到角色卡数据 (tEXt chunk keyword=ccv3/chara)")

        candidates.sort(key=lambda x: 0 if x[0] == 'ccv3' else 1)
        json_str = base64.b64decode(candidates[0][1]).decode('utf-8')
        return json.loads(json_str)

    @staticmethod
    def detect_version(card: dict) -> int:
        """检测角色卡版本。对齐 ST TavernCardValidator.validate()。"""
        if card.get("spec") == "chara_card_v3" and "data" in card:
            return 3
        if card.get("spec") == "chara_card_v2" and "data" in card:
            return 2
        if "name" in card and card.get("name"):
            return 1
        raise ValueError("无法识别的角色卡格式")

    @staticmethod
    def extract_data(card: dict, version: int) -> dict:
        """从不同版本中提取统一的 data dict。"""
        if version == 1:
            return {
                "name": card.get("name", ""),
                "description": card.get("description", ""),
                "personality": card.get("personality", ""),
                "scenario": card.get("scenario", ""),
                "first_mes": card.get("first_mes", ""),
                "mes_example": card.get("mes_example", ""),
                "creator_notes": card.get("creator_notes", card.get("creatorcomment", "")),
                "tags": card.get("tags", []),
                "creator": card.get("creator", ""),
                "character_version": card.get("character_version", "1.0"),
                "alternate_greetings": card.get("alternate_greetings", []),
                "system_prompt": card.get("system_prompt", ""),
                "post_history_instructions": "",
                "extensions": {},
            }
        # v2 / v3
        data = card.get("data", card)
        ext = data.get("extensions") or {}
        return {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "personality": data.get("personality", ""),
            "scenario": data.get("scenario", ""),
            "first_mes": data.get("first_mes", ""),
            "mes_example": data.get("mes_example", ""),
            "creator_notes": data.get("creator_notes", ""),
            "system_prompt": data.get("system_prompt", ""),
            "post_history_instructions": data.get("post_history_instructions", ""),
            "tags": data.get("tags", []),
            "creator": data.get("creator", ""),
            "character_version": data.get("character_version", "1.0"),
            "alternate_greetings": data.get("alternate_greetings", []),
            "extensions": ext,
            "character_book": data.get("character_book"),
            # 卡内嵌正则脚本：卡作者塞在 extensions.regex_scripts，
            # 导入侧拆到独立 RegexPreset 并挂到 persona.default_regex_preset_id
            "regex_scripts": ext.get("regex_scripts") or None,
            # depth_prompt 嵌套在 extensions，统一抽到顶层供下游 to_persona_fields 合并
            "depth_prompt": (ext.get("depth_prompt") or {}).get("prompt", ""),
        }

    @staticmethod
    def to_persona_fields(data: dict, raw_card: dict) -> dict:
        """将 ST data dict 映射为 Persona 创建字段。

        v3 映射策略（详见 docs/adr/0006）：
        - alternate_greetings + scenario → 一等字段
        - background = description（不再把 scenario 塞进 background）
        - system_prompt + post_history_instructions + depth_prompt.prompt
          按 \\n\\n---\\n\\n 拼接，无 header，合并到 author_note
        """
        # background 不再合并 scenario（scenario 自己有列）
        background = data.get("description") or None

        # smart concat 三个 ST "角色自带 prompt 注入" 字段到 author_note
        author_note_parts: list[str] = []
        for k in ("system_prompt", "post_history_instructions", "depth_prompt"):
            v = data.get(k)
            if v and isinstance(v, str) and v.strip():
                author_note_parts.append(v.strip())
        author_note = "\n\n---\n\n".join(author_note_parts) if author_note_parts else None

        # 备用开场白：保证 list[str]，剔空
        alt = data.get("alternate_greetings") or []
        if isinstance(alt, list):
            alternate_greetings = [str(g) for g in alt if g and str(g).strip()]
        else:
            alternate_greetings = []

        scenario = data.get("scenario")
        if scenario is not None:
            scenario = str(scenario).strip() or None

        # 注意：这里不设 imported_at。datetime 经过 JSON 序列化/反序列化
        # 会变成字符串，最终在 import_confirm 里强制覆盖为新鲜 datetime。
        return {
            "name": data["name"],
            "personality": data["personality"] or "",
            "background": background,
            "first_message": data.get("first_mes") or None,
            "mes_example": data.get("mes_example") or None,
            "tags": _normalize_tags(data.get("tags")),
            "card_data": raw_card,
            "source": "imported",
            "alternate_greetings": alternate_greetings,
            "scenario": scenario,
            "author_note": author_note,
            "css_theme": _extract_css_theme(data),
            "uses_mvu": _detect_mvu(data),
        }


def prepare_export_data(persona) -> dict:
    """准备导出用的 card_v3 JSON。以 card_data 为基础，独立列覆盖。"""
    card = dict(persona.card_data) if persona.card_data else {}

    # 确保 data 嵌套存在
    if "data" not in card:
        card = {"spec": "chara_card_v3", "spec_version": "3.0", "data": {}}
    if "data" not in card:
        card["data"] = {}

    card["data"]["name"] = persona.name
    card["data"]["personality"] = persona.personality
    if persona.background:
        card["data"]["description"] = persona.background
    if persona.first_message:
        card["data"]["first_mes"] = persona.first_message
    if persona.mes_example:
        card["data"]["mes_example"] = persona.mes_example
    if persona.tags:
        card["data"]["tags"] = persona.tags
    if persona.scenario:
        card["data"]["scenario"] = persona.scenario
    if persona.alternate_greetings:
        card["data"]["alternate_greetings"] = list(persona.alternate_greetings)
    if persona.css_theme:
        ext = card["data"].get("extensions") or {}
        ext["css"] = persona.css_theme
        card["data"]["extensions"] = ext

    return card


def build_export_png(persona, avatar_bytes: bytes) -> bytes:
    """将 card_v3 JSON 写入 PNG tEXt chunk，返回完整 PNG。"""
    export_data = prepare_export_data(persona)
    json_str = json.dumps(export_data, ensure_ascii=False)
    b64 = base64.b64encode(json_str.encode('utf-8')).decode('ascii')

    # 复用 avatar 作为底图
    from app.services.persona_import_service import _write_png_with_card
    return _write_png_with_card(avatar_bytes, b64)


def _write_png_with_card(image_bytes: bytes, b64_data: str) -> bytes:
    """将 base64 角色卡数据写入 PNG tEXt chunk。"""
    stream = io.BytesIO(image_bytes)
    if stream.read(8) != b'\x89PNG\r\n\x1a\n':
        raise ValueError("不是有效的 PNG 底图")

    chunks_before_idat: list[tuple[bytes, bytes]] = []
    chunks_after: list[tuple[bytes, bytes]] = []
    header_chunks: list[tuple[bytes, bytes]] = []
    seen_idat = False
    tEXt = b'tEXt'

    while True:
        header = stream.read(8)
        if len(header) < 8:
            break
        length = struct.unpack('>I', header[:4])[0]
        ctype = header[4:8]
        data = stream.read(length) if length > 0 else b''
        crc = stream.read(4)

        if ctype == b'IEND':
            chunks_after.append((b'IEND', b''))
            break
        if ctype == tEXt:
            # 过滤旧的 chara/ccv3 chunk
            null_idx = data.find(b'\x00')
            if null_idx != -1:
                kw = data[:null_idx].decode('latin-1').lower()
                if kw in ('chara', 'ccv3'):
                    continue
        if seen_idat:
            chunks_after.append((ctype, data))
        else:
            if ctype == b'IDAT':
                seen_idat = True
                chunks_after.append((ctype, data))
            else:
                header_chunks.append((ctype, data))

    # 拼接输出: header + filtered_chunks (before IDAT, without old chara/ccv3)
    # + new tEXt chunks (chara + ccv3, before IDAT) + ... + IEND
    output = io.BytesIO()
    output.write(b'\x89PNG\r\n\x1a\n')

    def write_chunk(ctype: bytes, data: bytes):
        output.write(struct.pack('>I', len(data)))
        output.write(ctype)
        output.write(data)
        crc = _png_crc32(ctype + data)
        output.write(struct.pack('>I', crc))

    for ctype, data in header_chunks:
        write_chunk(ctype, data)

    # 写入 ccv3 chunk (before IDAT)
    tEXt_data_ccv3 = b'ccv3\x00' + b64_data.encode('ascii')
    write_chunk(tEXt, tEXt_data_ccv3)

    # 写入 chara chunk (for v2 compatibility)
    tEXt_data_chara = b'chara\x00' + b64_data.encode('ascii')
    write_chunk(tEXt, tEXt_data_chara)

    for ctype, data in chunks_after:
        write_chunk(ctype, data)

    return output.getvalue()


def _png_crc32(data: bytes) -> int:
    """CRC32 计算（PNG 标准）。"""
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            if c & 1:
                c = 0xEDB88320 ^ (c >> 1)
            else:
                c = c >> 1
        table.append(c)
    c = 0xFFFFFFFF
    for byte in data:
        c = table[(c ^ byte) & 0xFF] ^ (c >> 8)
    return c ^ 0xFFFFFFFF
