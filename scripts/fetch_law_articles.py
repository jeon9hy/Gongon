"""국가법령정보센터 Open API에서 법령 조문을 받아 기준표 대조용 발췌(JSON)로 저장한다.

사용: uv run python -m scripts.fetch_law_articles --mst 273603 --articles 37 383 \\
        --out rules/sources/osh_standards_rule_mst273603.json
- MST(법령일련번호)는 시행본마다 다르다. 현행 MST는 lawSearch.do로 확인한다(docs/references.md).
- OC(신청한 이메일 ID)는 --oc 또는 환경변수 LAW_OC. 발췌에는 OC를 남기지 않는다.
- 조문 텍스트는 공식 응답의 조문·항·호 내용을 줄 단위로 이어 붙인 것이며, 기준표의 quote는
  이 텍스트의 부분 문자열이어야 한다(tests/engine/judgment/test_rule_sources.py).
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from engine.kst import KST

API_URL = "https://www.law.go.kr/DRF/lawService.do"


def article_text(unit: ET.Element) -> str:
    lines = [(unit.findtext("조문내용") or "").strip()]
    for paragraph in unit.findall("항"):
        lines.append((paragraph.findtext("항내용") or "").strip())
        lines.extend((item.findtext("호내용") or "").strip() for item in paragraph.iter("호"))
    return "\n".join(line for line in lines if line)


def extract(xml_bytes: bytes, article_numbers: list[str]) -> dict[str, object]:
    root = ET.fromstring(xml_bytes)
    info = root.find("기본정보")
    if info is None:
        raise SystemExit("응답에 기본정보가 없음(OC·MST 확인)")
    articles: dict[str, str] = {}
    for unit in root.iter("조문단위"):
        if unit.findtext("조문여부") != "조문":
            continue  # 편·장·절 제목 행
        number = unit.findtext("조문번호") or ""
        branch = unit.findtext("조문가지번호") or ""
        key = f"제{number}조" + (f"의{branch}" if branch else "")
        if number + (f"-{branch}" if branch else "") in article_numbers:
            articles[key] = article_text(unit)
    missing = len(article_numbers) - len(articles)
    if missing:
        raise SystemExit(f"요청한 조문 중 {missing}개를 찾지 못함: {article_numbers}")
    return {
        "law_name": info.findtext("법령명_한글"),
        "law_id": info.findtext("법령ID"),
        "promulgated_on": info.findtext("공포일자"),
        "promulgation_number": info.findtext("공포번호"),
        "effective_on": info.findtext("시행일자"),
        "partial_effective_dates": info.findtext("조문시행일자문자열"),
        "articles": articles,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mst", required=True, help="법령일련번호(시행본)")
    parser.add_argument("--articles", nargs="+", required=True, help="조문 번호. 가지조문은 566-2")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--oc", default=os.environ.get("LAW_OC"))
    args = parser.parse_args(argv)
    if not args.oc:
        parser.error("OC가 없음: --oc 또는 LAW_OC")

    query = {"OC": args.oc, "target": "law", "MST": args.mst, "type": "XML"}
    with urllib.request.urlopen(f"{API_URL}?{urllib.parse.urlencode(query)}", timeout=60) as res:
        body: bytes = res.read()
    snapshot = {
        "retrieved_from": f"{API_URL}?target=law&MST={args.mst}&type=XML",
        "retrieved_at": datetime.now(KST).isoformat(timespec="seconds"),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "mst": args.mst,
        **extract(body, args.articles),
    }
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"{args.out}: 조문 {len(args.articles)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
