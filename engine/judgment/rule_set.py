"""기준표(YAML) → RuleSet. 들어오는 경계에서 형식을 검증하고 잘못되면 바로 실패한다."""

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from engine.judgment.types import Condition, Element, RuleSet, Verdict

_OPERATORS = (">=", ">", "<=", "<")


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
    rule_set = RuleSet(
        work_type=_text(data, "work_type"),
        work_type_label=_text(data, "work_type_label"),
        rule_version=_text(data, "rule_version"),
        source=_text(data, "source"),
        source_verified=_bool(data, "source_verified"),
        conditions=tuple(_condition(item) for item in conditions),
        verified_on=data.get("verified_on"),
    )
    if rule_set.source_verified:
        _require_verification(data, rule_set)
    elif rule_set.verified_on is not None:
        raise RuleSetError("source_verified가 false인데 verified_on이 있음")
    return rule_set


def _require_verification(data: dict[str, Any], rule_set: RuleSet) -> None:
    # 원문 대조 완료 표시에는 발췌 파일·조문·대조일과 조건별 인용이 모두 있어야 한다.
    _text(data, "source_snapshot")
    articles = data.get("source_articles")
    if (
        not isinstance(articles, list)
        or not articles
        or not all(isinstance(a, str) and a for a in articles)
    ):
        raise RuleSetError("source_articles가 조문 목록이 아님")
    if type(rule_set.verified_on) is not date:  # datetime(날짜+시각)도 거부
        raise RuleSetError("verified_on이 날짜(YYYY-MM-DD)가 아님")
    unquoted = [c.id for c in rule_set.conditions if not c.quote]
    if unquoted:
        raise RuleSetError(f"원문 인용(quote) 없음: {unquoted}")


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
    quote = _optional_text(item, "quote", condition_id)
    action = _optional_text(item, "action", condition_id)
    lower_bound = item.get("forecast_lower_bound", False)
    if not isinstance(lower_bound, bool):
        raise RuleSetError(f"{condition_id}: forecast_lower_bound가 true/false가 아님")
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
        forecast_lower_bound=lower_bound,
        action=action,
    )


def _optional_text(item: dict[str, Any], key: str, condition_id: str) -> str | None:
    value = item.get(key)
    if value is not None and not isinstance(value, str):
        raise RuleSetError(f"{condition_id}: {key}가 문자열이 아님")
    return value


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
