"""기준표(YAML) → RuleSet. 들어오는 경계에서 형식을 검증하고 잘못되면 바로 실패한다."""

from pathlib import Path
from typing import Any

import yaml

from engine.judgment.types import Condition, Element, RuleSet, Verdict

_OPERATORS = (">=", ">")


class RuleSetError(ValueError):
    """기준표 형식이 올바르지 않다."""


def load_rule_set(path: Path) -> RuleSet:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        return parse_rule_set(data)
    except RuleSetError as error:
        raise RuleSetError(f"{path.name}: {error}") from error


def parse_rule_set(data: Any) -> RuleSet:
    if not isinstance(data, dict):
        raise RuleSetError("최상위가 매핑이 아님")
    conditions = data.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise RuleSetError("conditions가 비어 있음")
    return RuleSet(
        work_type=_text(data, "work_type"),
        work_type_label=_text(data, "work_type_label"),
        rule_version=_text(data, "rule_version"),
        source=_text(data, "source"),
        source_verified=_bool(data, "source_verified"),
        conditions=tuple(_condition(item) for item in conditions),
    )


def _condition(item: Any) -> Condition:
    if not isinstance(item, dict):
        raise RuleSetError("조건이 매핑이 아님")
    condition_id = _text(item, "id")
    operator = _text(item, "operator")
    if operator not in _OPERATORS:
        raise RuleSetError(f"{condition_id}: 지원하지 않는 연산 {operator!r}")
    threshold = item.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, int | float):
        raise RuleSetError(f"{condition_id}: threshold가 숫자가 아님")
    quote = item.get("quote")
    if quote is not None and not isinstance(quote, str):
        raise RuleSetError(f"{condition_id}: quote가 문자열이 아님")
    try:
        element = Element(_text(item, "element"))
        verdict = Verdict(_text(item, "verdict"))
    except ValueError as error:
        raise RuleSetError(f"{condition_id}: {error}") from error
    return Condition(
        id=condition_id,
        element=element,
        operator=operator,
        threshold=float(threshold),
        verdict=verdict,
        forecast_comparable=_bool(item, "forecast_comparable"),
        quote=quote,
    )


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise RuleSetError(f"{key}가 비어 있거나 문자열이 아님")
    return value


def _bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise RuleSetError(f"{key}가 true/false가 아님")
    return value
