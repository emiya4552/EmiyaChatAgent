# -*- coding: utf-8 -*-
"""Helpers for values that are persisted into JSONB MVU buckets."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


def make_json_safe(value):
    """Return a JSON-serializable copy of `value`.

    PyYAML resolves unquoted ISO dates to `datetime.date`; JSONB serialization
    cannot handle those Python objects directly.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(v) for v in value]
    return value
