"""작업 이름을 현장 용어로 (D-085 보완, C04-30)

C04-29에서 공온이 붙인 작업 이름 일부를 현장에서 부르는 말로 바꿨다. 이미 그 이름으로 저장된 작업도
같은 이름으로 옮겨야 복사·묶음·자주 쓴 작업이 맞는다. 날씨 판정 공종(기준 원문의 이름)은 바꾸지
않았으므로 판정 내역(judgments.work_type)은 건드리지 않는다.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAMED = {
    "벽체 철근": "벽체 철근 배근",
    "슬라브 철근": "슬라브 철근 배근",
    "벽체 형틀": "벽체 형틀 설치",
    "슬라브 형틀": "슬라브 형틀 설치",
    "형틀 해체": "탈형(형틀 해체)",
    "구조물 해체": "철거",
    "실내 마감": "내장 마감",
    "칸막이 설치": "경량 칸막이 설치",
    "패널 조립": "샌드위치패널 설치",
    "석재 붙임": "석재 시공",
    "고장력볼트 조임": "볼트 본조임",
    "설비 슬리브·배관 매립": "설비 슬리브 설치",
    "전기 배선": "전기 입선",
    "감리 검측": "검측(감리 입회)",
    "품질 시험": "현장 품질시험",
    "양생 관리": "양생",
    "승강기 설치": "엘리베이터 설치",
}


def _rename(pairs: dict[str, str]) -> None:
    statement = sa.text("UPDATE work_items SET work_type = :new WHERE work_type = :old")
    for old, new in pairs.items():
        op.execute(statement.bindparams(old=old, new=new))


def upgrade() -> None:
    _rename(RENAMED)


def downgrade() -> None:
    _rename({new: old for old, new in RENAMED.items()})
