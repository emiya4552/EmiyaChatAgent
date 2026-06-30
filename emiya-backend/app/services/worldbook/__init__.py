# -*- coding: utf-8 -*-
"""世界书子包。

模块：
  scanner       — 关键词匹配 + 预算筛选，产出激活集
  injector      — 按 position 把激活集分发到 Prompt 各位置
  service       — CRUD 业务
  import_export — ST native / character_book 互转
"""
from app.services.worldbook.scanner import ActiveEntry, scan_worldbook
from app.services.worldbook.injector import WorldbookInjector

__all__ = ["ActiveEntry", "scan_worldbook", "WorldbookInjector"]
