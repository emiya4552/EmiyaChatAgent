# -*- coding: utf-8 -*-
"""预设系统测试：MacroEngine → RegexProcessor → PresetInjector。"""
import re
import pytest
from app.services.macro_engine import MacroEngine
from app.services.regex_processor import RegexProcessor, parse_js_regex
from app.services.preset_injector import PresetInjector


class TestMacroEngineTrimAndComment:
    """Slice 1: {{trim}} 和 {{// comment}}。"""

    def test_comment_removed(self):
        """{{// 这是注释}} 被移除，不产生输出。"""
        result = MacroEngine.render("你好{{// 这是一条注释}}世界", {})
        assert result == "你好世界"

    def test_comment_multiline_content(self):
        """注释内可以包含多行内容。"""
        result = MacroEngine.render("开始{{//\n多行\n注释\n}}结束", {})
        assert result == "开始结束"

    def test_trim_removes_trailing_whitespace(self):
        """{{trim}} 清除之前文本的尾部空白和换行。"""
        result = MacroEngine.render("   hello   {{trim}}", {})
        assert result == "   hello"

    def test_trim_removes_newlines(self):
        """{{trim}} 清除之前累积的换行。"""
        result = MacroEngine.render("line1\n\n\n{{trim}}line2", {})
        assert result == "line1line2"

    def test_trim_before_text_noop(self):
        """{{trim}} 在文本开头时是空操作。"""
        result = MacroEngine.render("{{trim}}hello", {})
        assert result == "hello"

    def test_trim_with_comment(self):
        """{{trim}} 与 {{//}} 组合使用。"""
        result = MacroEngine.render("text{{// comment}}{{trim}}after", {})
        assert result == "textafter"

    def test_comment_at_start(self):
        """注释在字符串开头。"""
        result = MacroEngine.render("{{// header}}body", {})
        assert result == "body"


class TestMacroEngineRandom:
    """Slice 2: {{random::A::B::C}} 随机选择。"""

    def test_random_picks_one_of_options(self):
        """{{random}} 从候选项中随机选择一个。"""
        result = MacroEngine.render("{{random::A::B::C}}", {})
        assert result in ("A", "B", "C")

    def test_random_single_option(self):
        """只有一个选项时直接返回。"""
        result = MacroEngine.render("{{random::only}}", {})
        assert result == "only"

    def test_random_embedded_in_text(self):
        """{{random}} 可以嵌入在普通文本中。"""
        result = MacroEngine.render("你好，{{random::小明::小红}}，欢迎", {})
        assert result in ("你好，小明，欢迎", "你好，小红，欢迎")

    def test_random_multiple_in_one_text(self):
        """同一段文本中可以出现多个 {{random}}。"""
        result = MacroEngine.render("{{random::A::B}}-{{random::1::2}}", {})
        parts = result.split("-")
        assert parts[0] in ("A", "B")
        assert parts[1] in ("1", "2")

    def test_random_two_options(self):
        """两个选项。"'"""
        result = MacroEngine.render("{{random::左::右}}", {})
        assert result in ("左", "右")


class TestMacroEngineVariables:
    """Slice 3: {{setvar::name::value}} + {{getvar::name}}。"""

    def test_setvar_sets_variable(self):
        """{{setvar}} 设置变量，输出空字符串。"""
        scope = {}
        result = MacroEngine.render("{{setvar::key::hello}}", scope)
        assert result == ""
        assert scope["key"] == "hello"

    def test_setvar_empty_clears_variable(self):
        """{{setvar::name::}} 清除变量。"""
        scope = {"key": "old"}
        result = MacroEngine.render("{{setvar::key::}}", scope)
        assert result == ""
        assert "key" not in scope

    def test_getvar_gets_variable(self):
        """{{getvar}} 读取变量值。"""
        scope = {"key": "my_value"}
        result = MacroEngine.render("{{getvar::key}}", scope)
        assert result == "my_value"

    def test_getvar_nonexistent_returns_empty(self):
        """读取不存在的变量返回空字符串。"""
        result = MacroEngine.render("{{getvar::nonexistent}}", {})
        assert result == ""

    def test_setvar_then_getvar(self):
        """先 setvar 再 getvar，跨宏传递。"""
        scope = {}
        result = MacroEngine.render("{{setvar::name::小明}}{{getvar::name}}", scope)
        assert result == "小明"

    def test_setvar_across_multiple_macros(self):
        """setvar 的效果在同一 scope 中跨宏持续。"""
        scope = {}
        r1 = MacroEngine.render("{{setvar::color::蓝色}}", scope)
        assert r1 == ""
        r2 = MacroEngine.render("{{getvar::color}}", scope)
        assert r2 == "蓝色"


class TestMacroEngineDiceAndPick:
    """Slice 4: {{roll::N}}, {{dice::NdM}}, {{pick}}, {{floating}}。"""

    def test_roll_in_range(self):
        """{{roll::6}} 返回 1~6 的整数。"""
        for _ in range(30):
            result = MacroEngine.render("{{roll::6}}", {})
            assert result.isdigit()
            assert 1 <= int(result) <= 6

    def test_roll_1(self):
        """{{roll::1}} 总是返回 1。"""
        for _ in range(10):
            assert MacroEngine.render("{{roll::1}}", {}) == "1"

    def test_dice_basic(self):
        """{{dice::2d6}} 返回 2~12 的整数（两个六面骰）。"""
        for _ in range(30):
            result = MacroEngine.render("{{dice::2d6}}", {})
            assert result.isdigit()
            assert 2 <= int(result) <= 12

    def test_dice_single(self):
        """{{dice::1d20}} 返回 1~20 的整数。"""
        for _ in range(30):
            result = MacroEngine.render("{{dice::1d20}}", {})
            assert 1 <= int(result) <= 20

    def test_pick_cached_in_scope(self):
        """{{pick}} 的结果缓存在 scope 中，同一次渲染中多次调用返回相同值。"""
        scope = {}
        # 在一次 render 调用中多次使用同一个 pick
        result = MacroEngine.render(
            "{{pick::name::红::蓝::绿}}{{getvar::name}}", scope
        )
        # pick 输出颜色，getvar 输出相同颜色
        assert result[:1] == result[1:2] or result[0] == result[1]

    def test_floating_different_each_time(self):
        """{{floating}} 每次使用时可能不同（不缓存）。"""
        scope = {}
        # 一次 render 中使用两个 floating，它们可能不同
        results = set()
        for _ in range(100):
            r = MacroEngine.render(
                "{{floating::A::B::C::D::E}}{{floating::A::B::C::D::E}}", scope
            )
            results.add(r)
        # 应该有不同组合出现
        assert len(results) > 1


# ═══════════════════════════════════════════════════════════
# Slice 5: RegexProcessor
# ═══════════════════════════════════════════════════════════


class TestParseJsRegex:
    """JS 正则 → Python 正则转换。"""

    def test_simple_pattern_no_flags(self):
        """无 flag 的正则。"""
        pattern = parse_js_regex("/hello/")
        assert pattern.search("say hello world")
        assert not pattern.search("goodbye")

    def test_global_flag(self):
        """带 /g flag 的正则。"""
        pattern = parse_js_regex("/ab/g")
        result = pattern.sub("X", "ab ab ab")
        assert result == "X X X"

    def test_case_insensitive_flag(self):
        """带 /i flag 的正则。"""
        pattern = parse_js_regex("/hello/i")
        assert pattern.search("HELLO world")

    def test_dotall_flag(self):
        """带 /s flag（DOTALL）的正则。"""
        pattern = parse_js_regex("/a.*?b/s")
        assert pattern.search("a\nb")

    def test_combined_flags(self):
        """组合 flag /gis。"""
        pattern = parse_js_regex("/hello/gis")
        assert pattern.flags & re.IGNORECASE
        assert pattern.flags & re.DOTALL

    def test_escape_sequences(self):
        """正则中的转义序列。"""
        # JS 原文: /<draft>[\s\S]*?<\/draft>/g
        pattern = parse_js_regex(r"/<draft>[\s\S]*?<\/draft>/g")
        assert pattern.search("text <draft>content</draft> more")

    def test_invalid_regex_returns_none(self):
        """无效正则返回 None 而不是抛异常。"""
        pattern = parse_js_regex("/[invalid/g")
        assert pattern is None

    def test_no_slashes_plain_pattern(self):
        """不带斜杠的字符串作为纯正则模式编译（兼容裸 pattern 格式）。"""
        pattern = parse_js_regex("hello")
        assert pattern is not None


class TestRegexProcessor:
    """RegexProcessor 集成测试。"""

    def test_apply_prompt_only_removes_matching_text(self):
        """promptOnly 脚本移除匹配内容。"""
        scripts = [{
            "scriptName": "test",
            "findRegex": "/<secret>[\\s\\S]*?<\\/secret>/g",
            "replaceString": "",
            "promptOnly": True,
            "markdownOnly": False,
            "disabled": False,
            "placement": [0, 2],  # 同时作用于 system 区和历史区
            "minDepth": None,
            "maxDepth": None,
        }]
        messages = [
            {"role": "system", "content": "hello <secret>hidden</secret> world"},
        ]
        result = RegexProcessor.apply_prompt_only(messages, scripts)
        assert result[0]["content"] == "hello  world"

    def test_skips_disabled_scripts(self):
        """禁用的脚本不被应用。"""
        scripts = [{
            "scriptName": "disabled_test",
            "findRegex": "/hello/g",
            "replaceString": "bye",
            "promptOnly": True,
            "markdownOnly": False,
            "disabled": True,
            "placement": [2],
            "minDepth": None,
            "maxDepth": None,
        }]
        messages = [{"role": "system", "content": "hello world"}]
        result = RegexProcessor.apply_prompt_only(messages, scripts)
        assert result[0]["content"] == "hello world"

    def test_skips_markdown_only_scripts(self):
        """markdownOnly=true 的脚本在 promptOnly pass 中被跳过。"""
        scripts = [{
            "scriptName": "markdown_only",
            "findRegex": "/hello/g",
            "replaceString": "bye",
            "promptOnly": False,
            "markdownOnly": True,
            "disabled": False,
            "placement": [2],
            "minDepth": None,
            "maxDepth": None,
        }]
        messages = [{"role": "system", "content": "hello world"}]
        result = RegexProcessor.apply_prompt_only(messages, scripts)
        assert result[0]["content"] == "hello world"

    def test_respects_placement_filter(self):
        """placement 只作用于指定范围的消息。"""
        scripts = [{
            "scriptName": "system_only",
            "findRegex": "/remove/g",
            "replaceString": "",
            "promptOnly": True,
            "markdownOnly": False,
            "disabled": False,
            "placement": [0],  # 只作用于 system 区
            "minDepth": None,
            "maxDepth": None,
        }]
        messages = [
            {"role": "system", "content": "remove this system"},
            {"role": "user", "content": "keep remove this"},
            {"role": "assistant", "content": "keep remove this too"},
        ]
        result = RegexProcessor.apply_prompt_only(messages, scripts)
        assert result[0]["content"] == " this system"  # system 被处理
        assert result[1]["content"] == "keep remove this"  # 非 system 保持原样
        assert result[2]["content"] == "keep remove this too"

    def test_multiple_scripts(self):
        """多个脚本按顺序应用。"""
        scripts = [
            {
                "scriptName": "hide_draft",
                "findRegex": "/<draft>[\\s\\S]*?<\\/draft>/g",
                "replaceString": "",
                "promptOnly": True, "markdownOnly": False,
                "disabled": False, "placement": [2],
                "minDepth": None, "maxDepth": None,
            },
            {
                "scriptName": "clean_extra_spaces",
                "findRegex": "/  +/g",
                "replaceString": " ",
                "promptOnly": True, "markdownOnly": False,
                "disabled": False, "placement": [2],
                "minDepth": None, "maxDepth": None,
            },
        ]
        messages = [
            {"role": "user", "content": "text   <draft>hidden stuff</draft>   end"},
        ]
        result = RegexProcessor.apply_prompt_only(messages, scripts)
        assert result[0]["content"] == "text end"

    def test_replace_with_capture_groups(self):
        """替换字符串支持 $1, $2 捕获组引用。"""
        scripts = [{
            "scriptName": "rewrap",
            "findRegex": "/<old>(.*?)<\\/old>/g",
            "replaceString": "<new>$1</new>",
            "promptOnly": True, "markdownOnly": False,
            "disabled": False, "placement": [2],
            "minDepth": None, "maxDepth": None,
        }]
        messages = [{"role": "user", "content": "before <old>content</old> after"}]
        result = RegexProcessor.apply_prompt_only(messages, scripts)
        assert result[0]["content"] == "before <new>content</new> after"


# ═══════════════════════════════════════════════════════════
# Slice 6: PresetInjector
# ═══════════════════════════════════════════════════════════


def _make_prompt(name, content, enabled=True, position=0, depth=4, order=100,
                 role="system", system_prompt=False):
    return {
        "identifier": name,
        "name": name,
        "enabled": enabled,
        "injection_position": position,
        "injection_depth": depth,
        "injection_order": order,
        "role": role,
        "content": content,
        "system_prompt": system_prompt,
        "marker": False,
        "forbid_overrides": False,
    }


class TestPresetInjectorPosition0:
    """position=0: 注入到 system 区（history 之前）。"""

    def test_injects_into_system_area(self):
        """position=0 的 prompt 插入到 system 消息区域末尾。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "注入的 system 提示", position=0, order=100),
            ]
        }
        messages = [
            {"role": "system", "content": "核心规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        # 注入的 system msg 应在 history 之前
        assert result[0] == {"role": "system", "content": "核心规则"}
        assert result[1] == {"role": "system", "content": "注入的 system 提示"}
        assert result[2] == {"role": "user", "content": "你好"}

    def test_injects_user_role_prompt(self):
        """position=0 且 role=user 的 prompt 也插入到 system 区。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "用户侧注入", position=0, order=100, role="user"),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "用户侧注入"

    def test_skips_disabled_prompts(self):
        """禁用的 prompt 不被注入。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "不注入", enabled=False, position=0),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert len(result) == 2

    def test_multiple_position0_ordered_by_order(self):
        """position=0 的多个 prompt 按 injection_order 排序。"""
        preset = {
            "prompts": [
                _make_prompt("p2", "第二条", position=0, order=200),
                _make_prompt("p1", "第一条", position=0, order=100),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert result[1]["content"] == "第一条"
        assert result[2]["content"] == "第二条"

    def test_renders_macros_in_content(self):
        """prompt content 中的宏被 MacroEngine 渲染。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "{{random::A::B}}", position=0),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert result[1]["content"] in ("A", "B")


class TestPresetInjectorPosition2:
    """position=2: 注入到聊天历史的特定深度。"""

    def test_injects_at_specific_depth(self):
        """position=2 depth=2: 注入到距末尾第 2 条消息处。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "深度注入", position=2, depth=2, order=100, role="system"),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "回复1"},
            {"role": "user", "content": "消息2"},
            {"role": "assistant", "content": "回复2"},
        ]
        result = PresetInjector.inject(messages, preset)
        # depth=2 从末尾倒数第 2 条 = 在 "消息2" 之前
        # 结果: 规则, 消息1, 回复1, [注入], 消息2, 回复2
        assert len(result) == 6
        assert result[3] == {"role": "system", "content": "深度注入"}
        assert result[4] == {"role": "user", "content": "消息2"}
        assert result[5] == {"role": "assistant", "content": "回复2"}

    def test_depth_0_means_at_the_end(self):
        """depth=0: 消息列表最末尾（0 条消息在其后）。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "末尾注入", position=2, depth=0, order=100),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "回复1"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert len(result) == 4
        assert result[3]["content"] == "末尾注入"

    def test_depth_1_before_last_message(self):
        """depth=1: 最后一条消息之前。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "倒数注入", position=2, depth=1, order=100),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "回复1"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert len(result) == 4
        assert result[2]["content"] == "倒数注入"
        assert result[3]["content"] == "回复1"

    def test_depth_larger_than_history_goes_to_system_area(self):
        """depth 大于历史长度时回退到 system 区末尾。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "溢出", position=2, depth=999, order=100),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        # 历史只有1条，depth=999 溢出 → 放到 system 区
        assert result[1]["content"] == "溢出"


class TestPresetInjectorPosition1:
    """Slice 8a: injection_position=1 — 注入到 system 区最前面（ABSOLUTE）。"""

    def test_position1_prepends_to_system_area(self):
        """position=1 注入到 system 区头部（所有 system msg 之前）。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "绝对提示词", position=1, order=100),
            ]
        }
        messages = [
            {"role": "system", "content": "角色描述"},
            {"role": "system", "content": "核心规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert result[0]["content"] == "绝对提示词"
        assert result[1]["content"] == "角色描述"
        assert result[2]["content"] == "核心规则"

    def test_position1_multiple_sorted_by_order(self):
        """多个 position=1 的 prompt 按 injection_order 排序后插入。"""
        preset = {
            "prompts": [
                _make_prompt("p2", "第二条绝对", position=1, order=200),
                _make_prompt("p1", "第一条绝对", position=1, order=100),
            ]
        }
        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert result[0]["content"] == "第一条绝对"
        assert result[1]["content"] == "第二条绝对"

    def test_position1_only_system_messages(self):
        """没有 system 区消息时，position=1 注入到最前面。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "绝对提示", position=1, order=100),
            ]
        }
        messages = [
            {"role": "user", "content": "直接开始"},
        ]
        result = PresetInjector.inject(messages, preset)
        assert result[0]["content"] == "绝对提示"


class TestPresetInjectorSkipMarker:
    """Slice 8b: 跳过 marker=true 的 ST 内部槽位。"""

    def test_skips_marker_prompts(self):
        """marker=true 的 prompt 不注入。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "Chat History", enabled=True),
                _make_prompt("real", "真正要注入的内容", position=0),
            ]
        }
        # 手动设置 marker
        preset["prompts"][0]["marker"] = True
        preset["prompts"][0]["content"] = ""  # marker 通常没有内容

        messages = [
            {"role": "system", "content": "规则"},
            {"role": "user", "content": "你好"},
        ]
        result = PresetInjector.inject(messages, preset)
        # 只有 "real" 被注入，"Chat History" marker 被跳过
        assert len(result) == 3
        assert result[1]["content"] == "真正要注入的内容"

    def test_skips_marker_even_with_content(self):
        """即使 marker=true 有内容也跳过（保守处理）。"""
        preset = {
            "prompts": [
                _make_prompt("p1", "不应该出现的内容", position=0),
            ]
        }
        preset["prompts"][0]["marker"] = True

        messages = [{"role": "user", "content": "你好"}]
        result = PresetInjector.inject(messages, preset)
        # marker 条目被跳过，只有原始消息
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════
# Slice 9: Squash after injection
# ═══════════════════════════════════════════════════════════


class TestSquashAfterInjection:
    """注入后连续 system 消息应该被合并。"""

    def test_squash_consecutive_system_messages(self):
        """连续的 system 消息合并为一条。"""
        from app.services.langgraph.nodes import _squash_system_messages

        messages = [
            {"role": "system", "content": "规则A"},
            {"role": "system", "content": "规则B"},
            {"role": "system", "content": "规则C"},
            {"role": "user", "content": "你好"},
        ]
        result = _squash_system_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert "规则A" in result[0]["content"]
        assert "规则B" in result[0]["content"]
        assert "规则C" in result[0]["content"]
        assert result[1]["role"] == "user"

    def test_squash_preserves_non_system_order(self):
        """非连续 system 消息保持各自独立。"""
        from app.services.langgraph.nodes import _squash_system_messages

        messages = [
            {"role": "system", "content": "规则A"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "回复"},
            {"role": "system", "content": "规则B"},
        ]
        result = _squash_system_messages(messages)
        assert len(result) == 4  # 各自独立，不合并
        assert result[0]["content"] == "规则A"
        assert result[3]["content"] == "规则B"

    def test_full_inject_then_squash(self):
        """注入后合并：多个 position=0 prompt 注入后应合并为一条 system。"""
        from app.services.langgraph.nodes import _squash_system_messages

        preset = {
            "prompts": [
                _make_prompt("p1", "预设规则A", position=0, order=100),
                _make_prompt("p2", "预设规则B", position=0, order=200),
            ]
        }
        messages = [
            {"role": "system", "content": "角色描述"},
            {"role": "user", "content": "你好"},
        ]
        after_inject = PresetInjector.inject(messages, preset)
        after_squash = _squash_system_messages(after_inject)

        # 应该只有 1 条 system 消息 + 1 条 user 消息
        assert len(after_squash) == 2
        system_msg = after_squash[0]
        assert system_msg["role"] == "system"
        assert "角色描述" in system_msg["content"]
        assert "预设规则A" in system_msg["content"]
        assert "预设规则B" in system_msg["content"]
