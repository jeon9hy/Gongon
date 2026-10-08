import os
from pathlib import Path

import pytest

from app.core import templating


def test_static_url_changes_when_file_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    css = tmp_path / "gongon.css"
    css.write_text("a {}", encoding="utf-8")
    monkeypatch.setattr(templating, "STATIC_DIR", tmp_path)
    os.utime(css, (1_000, 1_000))
    before = templating.static_url("gongon.css")

    os.utime(css, (2_000, 2_000))  # 수정하면 주소가 바뀌어 브라우저 캐시를 쓰지 않는다

    assert before == "/static/gongon.css?v=1000"
    assert templating.static_url("gongon.css") == "/static/gongon.css?v=2000"
