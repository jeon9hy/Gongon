"""국가건설기준센터 OpenAPI에서 KCS 본문을 받아 날씨 조건 문장만 발췌(JSON)로 저장한다.

사용: uv run python -m scripts.fetch_kcs --codes 142040 414700 --out rules/sources/kcs_weather.json
- 키(kcsc.re.kr/support/api에서 신청)는 --key, 환경변수 KCSC_API_KEY, .env의 KCSC_API_KEY 순.
  발췌에는 키를 남기지 않는다.
- 원본 전체는 저장소에 넣지 않는다(D-033). 기온·강우·습도·바람 같은 날씨 조건이 들어간 문단만
  조항 번호와 함께 남긴다. 이 발췌는 기준표를 만들 후보이며, 기준표(rules/*.yaml)의 quote는
  발췌 문장의 부분 문자열이어야 한다(tests/engine/judgment/test_rule_sources.py와 같은 방식).
"""

import argparse
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import ENV_FILE, read_env_file
from engine.kst import KST

API_URL = "https://kcsc.re.kr/OpenApi/CodeViewer"
# 날씨로 비교할 수 있는 조건을 찾는 말. 넓게 잡고, 기준표로 옮길 때 사람이 다시 고른다.
# '비가'는 '비가황 고무'를 빼려고 뒤 글자를 본다.
WEATHER = re.compile(r"℃|기상|기온|강우|강설|우천|비가(?!황)|습도|풍속|바람|동결|결빙|눈이")


def plain(contents: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>", "\n", contents)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def clause_label(row: dict[str, Any]) -> str:
    """'3.2 시공' 절의 '(1)' 문단 → '3.2(1)'. 본문만 있는 행은 절 번호만."""
    section = (row.get("title") or "").split(" ")[0]
    label = row.get("label") or ""
    return section if label in ("", "본문", section) else f"{section}{label}"


def extract(document: dict[str, Any]) -> dict[str, Any]:
    excerpts: dict[str, str] = {}
    for row in document.get("list") or []:
        text = plain(row.get("contents") or "")
        if text and WEATHER.search(text):
            key = clause_label(row)
            excerpts[key] = f"{excerpts[key]}\n{text}" if key in excerpts else text
    return {
        "code": f"{document['codeType']} {document['code'][:2]} {document['code'][2:4]} "
        f"{document['code'][4:]}",
        "name": document.get("name"),
        "version": document.get("version"),
        "updated_at": document.get("updateDate"),
        "excerpts": excerpts,
    }


def fetch(code: str, key: str) -> bytes:
    query = urllib.parse.urlencode({"key": key})
    with urllib.request.urlopen(f"{API_URL}/KCS/{code}?{query}", timeout=60) as res:
        body: bytes = res.read()
    return body


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="+", required=True, help="KCS 6자리 번호. 예: 142040")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--key",
        default=os.environ.get("KCSC_API_KEY") or read_env_file(ENV_FILE).get("KCSC_API_KEY"),
    )
    args = parser.parse_args(argv)
    if not args.key:
        parser.error("키가 없음: --key 또는 KCSC_API_KEY")

    documents = []
    for code in args.codes:
        body = fetch(code, args.key)
        data = json.loads(body)
        document = data[0] if isinstance(data, list) and data else data
        if not isinstance(document, dict) or not document.get("list"):
            raise SystemExit(f"KCS {code}: 본문이 비어 있음(키·번호 확인)")
        documents.append(
            {
                "retrieved_from": f"{API_URL}/KCS/{code}",
                "response_sha256": hashlib.sha256(body).hexdigest(),
                **extract(document),
            }
        )
    snapshot = {
        "note": "국가건설기준센터 OpenAPI 본문에서 날씨 조건이 들어간 문단만 발췌했다. "
        "원본 전체는 저장소에 넣지 않는다(D-033). 기준표를 만들 때 이 중에서 고른다.",
        "retrieved_at": datetime.now(KST).isoformat(timespec="seconds"),
        "documents": documents,
    }
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", "utf-8")
    for doc in documents:
        print(f"{doc['code']} {doc['name']}({doc['version']}): 발췌 {len(doc['excerpts'])}개")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
