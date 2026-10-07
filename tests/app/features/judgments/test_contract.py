"""문서 예시와 실제 저장 기록을 같은 JSON Schema로 검사한다. 외부 API 호출 없음."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, Settings
from app.core.rules import rule_sets_by_label
from app.features.judgments.models import Judgment
from app.features.judgments.service import serialize_judgment
from engine.judgment import Element
from tests.app.features.judgments.test_flow import add_site, run
from tests.fakes import FakeKma

EXAMPLES: dict[str, Any] = json.loads(
    (REPO_ROOT / "docs/contract-examples.json").read_text(encoding="utf-8")
)


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads((REPO_ROOT / "docs/schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_documented_examples(validator: Draft202012Validator, name: str) -> None:
    validator.validate(EXAMPLES[name])


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("verdict", "안전"),
        ("rule_source_verified", "false"),
        ("forecast_issued_at", None),
        ("work_start_at", "2026-10-05T09:00:00"),
        ("work_start_at", "2026-10-05T00:00:00Z"),
        ("work_start_at", "2026-02-30T09:00:00+09:00"),
        ("target_date", "2026-02-30"),
        ("hours", []),
        ("schema_version", "2.0"),
    ],
)
def test_invalid_record_rejected(
    validator: Draft202012Validator, field: str, bad_value: Any
) -> None:
    record = deepcopy(EXAMPLES["go"])
    record[field] = bad_value
    with pytest.raises(ValidationError):
        validator.validate(record)


def test_unit_mismatch_and_missing_rule_version_rejected(validator: Draft202012Validator) -> None:
    record = deepcopy(EXAMPLES["go"])
    record["element_units"]["precipitation_mm_per_h"] = "cm/h"
    with pytest.raises(ValidationError):
        validator.validate(record)
    record = deepcopy(EXAMPLES["go"])
    del record["rule_version"]
    with pytest.raises(ValidationError):
        validator.validate(record)


@pytest.mark.parametrize(("field", "value"), [("lower", 0.0), ("verdict", "진행")])
def test_missing_value_cannot_be_filled_as_normal(
    validator: Draft202012Validator, field: str, value: Any
) -> None:
    record = deepcopy(EXAMPLES["missing"])
    record["hours"][0]["conditions"][0][field] = value
    with pytest.raises(ValidationError):
        validator.validate(record)


def test_unbounded_amount_is_distinct_from_missing(validator: Draft202012Validator) -> None:
    record = deepcopy(EXAMPLES["stop"])
    rain = record["hours"][0]["conditions"][1]
    rain.update(raw="50.0mm 이상", lower=50.0, upper=None)
    validator.validate(record)


@pytest.mark.parametrize("field", ["verdict", "forecast_issued_at", "hours"])
def test_collection_failure_cannot_masquerade_as_success(
    validator: Draft202012Validator, field: str
) -> None:
    record = deepcopy(EXAMPLES["collection_failed"])
    record[field] = EXAMPLES["go"][field]
    with pytest.raises(ValidationError):
        validator.validate(record)


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("go", "진행"),
        ("stop", "중지 검토"),
        ("missing", "판정 불가"),
        ("not_comparable", "확인 필요"),
        ("collection_failed", "판정 불가"),
    ],
)
def test_actual_saved_record_matches_contract(
    client: TestClient,
    session: Session,
    fake_kma: FakeKma,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    validator: Draft202012Validator,
    scenario: str,
    expected: str,
) -> None:
    if scenario == "stop":
        fake_kma.set_hour("20261005", 9, PCP="1.0mm")
    elif scenario == "missing":
        del fake_kma.values[("20261005", "0900")]["WSD"]
    elif scenario == "collection_failed":
        object.__setattr__(settings, "kma_service_key", "")
    elif scenario == "not_comparable":
        rules = rule_sets_by_label()["철골 작업"]
        changed = replace(
            rules,
            conditions=tuple(
                replace(c, forecast_comparable=False) if c.element == Element.WIND_SPEED_MPS else c
                for c in rules.conditions
            ),
        )
        monkeypatch.setattr(
            "app.features.judgments.service.rule_sets_by_label", lambda: {"철골 작업": changed}
        )
    run(client, add_site(client))
    saved = session.scalars(select(Judgment)).one()
    record = serialize_judgment(saved)
    validator.validate(json.loads(json.dumps(record, allow_nan=False)))
    assert record["verdict"] == expected
    assert record["rule_source_verified"] is True
    assert record["hours"] == saved.hours and record["windows"] == saved.windows
    assert datetime.fromisoformat(record["judged_at"]) == saved.judged_at
    if scenario == "collection_failed":
        assert record["failure_reason"] and record["forecast_issued_at"] is None
    else:
        # PostgreSQL의 반환 시간대와 관계없이 JSON에는 KST를 명시한다.
        assert saved.forecast_issued_at is not None
        saved.forecast_issued_at = saved.forecast_issued_at.astimezone(UTC)
        assert serialize_judgment(saved)["forecast_issued_at"] == "2026-10-04T14:00:00+09:00"
        record["hours"][0]["conditions"].clear()
        assert saved.hours[0]["conditions"]  # 내보낸 객체의 변경이 ORM JSON을 오염시키지 않음
    saved.work_start_at = saved.work_start_at.replace(tzinfo=None)
    with pytest.raises(ValueError, match="시간대"):
        serialize_judgment(saved)
