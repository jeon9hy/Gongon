"""기존 현장(참여 업체 없이 만든 행)에 조정자를 명시 지정한다(D-057).

소유자를 추정하지 않으므로 0010 이전에 만든 현장은 이 스크립트로 지정하기 전까지 아무도 볼 수 없다.
사용자는 먼저 화면에서 가입해 둔다. 개발 DB(DATABASE_URL)에 바로 저장한다.

    uv run python scripts/grant_site.py --email me@example.com --site-id 3
    uv run python scripts/grant_site.py --email me@example.com --all-unassigned
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import now_kst
from app.core.db import get_engine
from app.features.teams import service as teams_service

UNASSIGNED = text(
    "SELECT s.id FROM sites s WHERE s.deleted_at IS NULL AND NOT EXISTS "
    "(SELECT 1 FROM project_participants p WHERE p.site_id = s.id) ORDER BY s.id"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--site-id", type=int)
    target.add_argument("--all-unassigned", action="store_true", help="참여 업체가 없는 현장 전부")
    args = parser.parse_args()

    with Session(get_engine(), expire_on_commit=False) as session:
        site_ids = list(session.scalars(UNASSIGNED)) if args.all_unassigned else [args.site_id]
        if not site_ids:
            print("참여 업체가 없는 현장이 없습니다.")
            return 0
        failed = False
        for site_id in site_ids:
            try:
                print(teams_service.grant_existing_site(session, site_id, args.email, now_kst()))
            except ValueError as error:
                session.rollback()
                failed = True
                print(f"현장 {site_id}: 지정하지 않음 · {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
