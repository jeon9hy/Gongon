"""법령 원문 실검증 스크립트가 개정·누락을 놓치지 않는지 네트워크 없이 검사한다.

data/law_search_osh_20261008.xml은 2026-10-08 lawSearch.do 실제 응답이며,
링크 속 OC 값만 REDACTED로 바꿨다.
"""

import json
from pathlib import Path

import pytest

from scripts import verify_law_sources as v

SEARCH_XML = (Path(__file__).parent / "data" / "law_search_osh_20261008.xml").read_bytes()


def test_current_mst_from_real_search_response() -> None:
    assert v.current_mst(SEARCH_XML, "007363") == "273603"


def test_current_mst_ignores_other_law_and_history_entries() -> None:
    assert v.current_mst(SEARCH_XML, "000001") is None
    history = SEARCH_XML.replace("<현행연혁코드>현행".encode(), "<현행연혁코드>연혁".encode())
    assert v.current_mst(history, "007363") is None


def test_request_numbers_handles_branch_articles_and_appendices() -> None:
    snapshot = {
        "articles": {"제37조": "", "제566조의2": ""},
        "appendices": {"별표 13의2": "", "별표 4": ""},
    }
    assert v.request_numbers(snapshot) == (["37", "566-2"], ["13-2", "4"])


def test_request_numbers_rejects_unknown_key() -> None:
    with pytest.raises(ValueError):
        v.request_numbers({"articles": {"부칙": ""}})


def test_text_differences_reports_changed_and_missing_units() -> None:
    saved = {
        "articles": {"제37조": "초당 15미터", "제383조": "같음"},
        "appendices": {"별표 13의2": "31도"},
    }
    live = {"articles": {"제37조": "초당 20미터", "제383조": "같음"}, "appendices": {}}
    assert v.text_differences(saved, live) == ["제37조", "별표 13의2"]
    assert v.text_differences(saved, saved) == []


def test_saved_snapshot_keys_are_all_requestable() -> None:
    # 실제 발췌의 키가 모두 다시 요청 가능한 형식이어야 실검증에서 빠지는 조문이 없다.
    for path in sorted(v.SOURCES_DIR.glob("*.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if "mst" in snapshot:
            articles, appendices = v.request_numbers(snapshot)
            assert len(articles) == len(snapshot["articles"])
            assert len(appendices) == len(snapshot.get("appendices", {}))


def test_main_without_oc_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAW_OC", raising=False)
    monkeypatch.setattr(v, "read_env_file", lambda _path: {})
    assert v.main() == 2


def test_new_promulgation_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    snapshot = tmp_path / "law.json"
    snapshot.write_text(
        '{"law_name": "산업안전보건기준에 관한 규칙", "law_id": "007363", "mst": "200000",'
        ' "articles": {"제37조": "본문"}, "appendices": {}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(v, "_get", lambda url, query: SEARCH_XML)
    monkeypatch.setattr(
        v, "extract", lambda body, a, b: {"articles": {"제37조": "본문"}, "appendices": {}}
    )
    assert v.verify(snapshot, "oc") == [
        "새 시행본: 현행 MST 273603, 발췌 MST 200000 — 다시 받고 기준 검토"
    ]
