"""현장 참여 업체·멤버십·역할(C03-2, D-057). 현장 접근 범위와 역할 확인은 모두 여기를 거친다.

- 비참여 현장은 404(존재를 드러내지 않음), 역할 부족은 403.
- 같은 회사여도 멤버십이 없으면 볼 수 없다. 회사 공통 관리자는 없다.
- 조정자는 원청 소속만 될 수 있다. 마지막 조정자는 회수할 수 없다.
- 참여 업체는 사람 없이 등록·종료·재개하고, 업체별 담당자 명부를 둔다(C04-9, D-066).
- 현장 코드를 아는 가입자는 스스로 담당자로 참여한다(D-095). 업체는 가입한 회사 그대로다.
"""

import secrets
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Annotated, cast

from fastapi import Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.work_kinds import WORK_TRADE_NAMES
from app.features.auth import service as auth_service
from app.features.auth.schemas import CurrentUser, UserInfo
from app.features.sites.schemas import SiteRecord
from app.features.teams import repository
from app.features.teams.models import (
    ParticipantContact,
    ProjectMembership,
    ProjectParticipant,
    SiteJoinCode,
)
from app.features.teams.schemas import (
    ALL_ROLES,
    ASSIGNABLE_ROLES,
    CATEGORY_LABELS,
    CONTACT_DETAIL_ROLES,
    KIND_LABELS,
    MANAGE_ROLES,
    PROPOSE_ROLES,
    ROLE_LABELS,
    Category,
    ContactCard,
    ContactForm,
    ContactView,
    MemberForm,
    MembersView,
    MemberView,
    Option,
    ParticipantForm,
    ParticipantOption,
    ParticipantView,
    Role,
    RoleOption,
    RosterPerson,
    SiteMember,
    TeamAllView,
    TeamRow,
)
from engine.kst import KST

NOT_FOUND = "현장을 찾을 수 없습니다"
FORBIDDEN = "이 현장에서 이 작업을 할 권한이 없습니다"
SAME_NAME_MEMBER = "같은 이름의 업체가 이미 있어요. 그 업체에 붙일지 따로 추가할지 고르세요."
TRADE_CUSTOM_MAX = 20  # 직접 입력한 업종 한 개(C04-45)
TRADE_NOTE_MAX = 20  # 표 한 칸에 들어가는 길이(C04-39 후속, 개발자 요청). DB 열은 60자 그대로
SAME_NAME_PARTICIPANT = "같은 이름의 업체가 이미 있어요. 다른 업체면 '따로 등록'을 체크하세요."


def site_ids_for(session: Session, user_id: int) -> frozenset[int]:
    """활성 멤버십이 있는 현장. 다른 기능은 이 범위로 목록·조회를 제한한다."""
    return repository.active_site_ids(session, user_id, ALL_ROLES)


def board_site_ids(session: Session, user_id: int) -> frozenset[int]:
    """게시 역할로 참여한 현장(현장 TV 계정)."""
    return repository.active_site_ids(session, user_id, ("board",))


def managed_site_ids(session: Session, user_id: int) -> frozenset[int]:
    return repository.active_site_ids(session, user_id, MANAGE_ROLES)


def role_on(session: Session, user_id: int, site_id: int) -> Role | None:
    membership = repository.active_membership(session, user_id, site_id)
    return None if membership is None else cast(Role, membership.role)


def require_role(
    session: Session, user: CurrentUser, site_id: int, allowed: tuple[Role, ...]
) -> Role:
    role = role_on(session, user.user_id, site_id)
    if role is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if role not in allowed:
        raise HTTPException(status_code=403, detail=FORBIDDEN)
    return role


def accessible_site_ids(
    user: auth_service.CurrentUserDep, session: Annotated[Session, Depends(get_session)]
) -> frozenset[int]:
    """라우터 의존성: 로그인 사용자가 볼 수 있는 현장 ID."""
    return site_ids_for(session, user.user_id)


AccessibleSitesDep = Annotated[frozenset[int], Depends(accessible_site_ids)]


def manageable_site_ids(
    user: auth_service.CurrentUserDep, session: Annotated[Session, Depends(get_session)]
) -> frozenset[int]:
    """라우터 의존성: 내가 조정자인 현장. 화면에서 실행·추가·삭제 버튼을 보일지 정한다.

    버튼을 숨기는 것은 안내일 뿐이며 권한은 각 서비스의 require_role이 확인한다.
    """
    return managed_site_ids(session, user.user_id)


ManagedSitesDep = Annotated[frozenset[int], Depends(manageable_site_ids)]


def proposable_site_ids(
    user: auth_service.CurrentUserDep, session: Annotated[Session, Depends(get_session)]
) -> frozenset[int]:
    """라우터 의존성: 변경을 제안할 수 있는 현장(조정자·담당자). 버튼 표시용이다."""
    return repository.active_site_ids(session, user.user_id, PROPOSE_ROLES)


ProposableSitesDep = Annotated[frozenset[int], Depends(proposable_site_ids)]


def participant_labels(session: Session, site_id: int) -> dict[int, str]:
    """현장 참여 업체 ID → "회사 이름 · 구분"(원청 먼저, 제외한 업체 포함). 표시에 쓴다.

    고를 수 있는 업체(참여 중)는 participant_choices."""
    participants = repository.participants(session, site_id)
    names = auth_service.organization_names(session, (p.organization_id for p in participants))
    return {
        p.id: f"{names.get(p.organization_id, '이름 없음')} · {_group_label(p)}"
        for p in participants
    }


def site_members(session: Session, site_id: int) -> tuple[SiteMember, ...]:
    """현장의 활성 참여자(쿼리 2회). 회수한 사람은 빠진다."""
    return _site_members(session, repository.active_memberships(session, site_id))


def memberships_of(session: Session, user_id: int) -> tuple[SiteMember, ...]:
    """한 사용자의 모든 활성 참여(현장마다 하나). 내 조치 목록의 범위를 정한다."""
    return _site_members(session, repository.active_memberships_of_user(session, user_id))


def _site_members(session: Session, memberships: list[ProjectMembership]) -> tuple[SiteMember, ...]:
    users = auth_service.describe_users(session, (m.user_id for m in memberships))
    return tuple(
        SiteMember(
            site_id=m.site_id,
            user_id=m.user_id,
            display_name=users[m.user_id].display_name,
            participant_id=m.participant_id,
            organization_name=users[m.user_id].organization_name,
            role=cast(Role, m.role),
        )
        for m in memberships
        if m.user_id in users and users[m.user_id].is_active
    )


def roster_people(
    session: Session, site_id: int, contact_ids: Iterable[int] = ()
) -> tuple[RosterPerson, ...]:
    """명부의 사람(쿼리 1~2회). contact_ids를 주면 명부에서 뺀 사람도 그 ID는 돌려준다."""
    people = repository.contacts(session, site_id)
    missing = set(contact_ids) - {c.id for c in people}
    if missing:
        people += repository.contacts_by_ids(session, site_id, missing)
    return tuple(
        RosterPerson(c.id, c.site_id, c.participant_id, c.name, c.job_title, c.user_id)
        for c in people
    )


def contacts_linked_to(session: Session, user_id: int) -> tuple[RosterPerson, ...]:
    """이 사용자와 계정이 연결된 명부의 사람(현장마다 하나). 내 조치 목록의 범위에 쓴다."""
    return tuple(
        RosterPerson(c.id, c.site_id, c.participant_id, c.name, c.job_title, c.user_id)
        for c in repository.contacts_linked_to(session, user_id)
    )


def participant_choices(session: Session, site_id: int) -> tuple[ParticipantOption, ...]:
    """작업 실행 업체·조치 담당으로 고를 수 있는 참여 중 업체(구분 순 → 이름 순, D-066)."""
    participants = [p for p in repository.participants(session, site_id) if p.ended_at is None]
    names = auth_service.organization_names(session, (p.organization_id for p in participants))
    options = [
        ParticipantOption(
            p.id,
            names.get(p.organization_id, "이름 없음"),
            _group_label(p),
            tuple(p.work_trades or ()),
        )
        for p in participants
    ]
    order = {label: i for i, label in enumerate(("원청", *CATEGORY_LABELS.values()))}
    return tuple(sorted(options, key=lambda o: (order[o.group_label], o.name, o.participant_id)))


def company_names(session: Session, site_ids: list[int]) -> dict[int, str]:
    """여러 현장의 참여 업체 ID → 회사 이름(쿼리 2회). 홈의 오늘 작업 목록에 쓴다."""
    if not site_ids:
        return {}
    participants = repository.participants_for_sites(session, site_ids)
    names = auth_service.organization_names(session, (p.organization_id for p in participants))
    return {p.id: names.get(p.organization_id, "이름 없음") for p in participants}


def company_trades(session: Session, site_ids: list[int]) -> dict[int, str]:
    """참여 업체 ID → 맡은 업종(D-088), 없으면 업종 메모·구분. 업체별 묶음 줄에 쓴다(D-085)."""
    if not site_ids:
        return {}
    return {
        p.id: " · ".join(p.work_trades or ()) or p.trade_note or _group_label(p)
        for p in repository.participants_for_sites(session, site_ids)
    }


def add_founder(session: Session, site_id: int, user: CurrentUser, now: datetime) -> None:
    """현장을 만든 사람의 회사를 원청, 본인을 조정자로 둔다. 커밋은 호출한 현장 서비스가 한다."""
    participant = ProjectParticipant(
        site_id=site_id, organization_id=user.organization_id, kind="prime"
    )
    session.add(participant)
    session.flush()
    session.add(_membership(participant, user.user_id, "coordinator", user.user_id, now))
    session.add(SiteJoinCode(site_id=site_id, code=_new_code(session), created_at=now,
                             created_by_user_id=user.user_id))  # fmt: skip


CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 헷갈리는 0·O·1·I·L 제외
CODE_LENGTH = 8


def _new_code(session: Session) -> str:
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if repository.site_id_for_code(session, code) is None:
            return code


def normalize_code(raw: str) -> str:
    """입력한 코드에서 하이픈·공백을 빼고 대문자로. 형식이 맞지 않으면 빈 글자.

    만드는 코드는 헷갈리는 글자를 빼지만, 입력은 영문·숫자 8자면 받는다(시험 코드 TEST0000 등)."""
    code = "".join(ch for ch in raw.upper() if ch.isascii() and ch.isalnum())
    if len(code) != CODE_LENGTH:
        return ""
    return code


def show_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def renew_join_code(session: Session, actor: CurrentUser, site_id: int, now: datetime) -> None:
    """새 코드로 바꾼다. 옛 코드로는 더 참여할 수 없다(이미 참여한 사람은 그대로)."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    row = repository.join_code(session, site_id)
    if row is None:
        row = SiteJoinCode(site_id=site_id)
        session.add(row)
    row.code = _new_code(session)
    row.created_at = now
    row.created_by_user_id = actor.user_id
    session.commit()


def site_for_code(session: Session, raw: str) -> int | None:
    code = normalize_code(raw)
    return repository.site_id_for_code(session, code) if code else None


def join_by_code(
    session: Session, site_id: int, user: CurrentUser, now: datetime
) -> tuple[bool, tuple[str, ...]]:
    """코드로 현장에 담당자로 참여한다. (이미 참여 중이었는지, 오류 목록).

    업체는 가입한 회사다. 그 회사가 이 현장에 없으면 협력업체로 새로 넣는다. 이름이 같은 업체가
    있어도 자동으로 붙이지 않는다(D-066, 조정자가 업체 화면에서 정리). 현장 확인(삭제 여부)은
    부르는 쪽이 먼저 한다."""
    if repository.active_membership(session, user.user_id, site_id) is not None:
        return True, ()
    participant = repository.participant_of(session, site_id, user.organization_id)
    if participant is not None and participant.ended_at is not None:
        return False, ("이 현장에서 제외된 업체예요. 현장 조정자에게 복귀를 부탁해 주세요.",)
    if participant is None:
        participant = ProjectParticipant(
            site_id=site_id,
            organization_id=user.organization_id,
            kind="subcontractor",
            created_by_user_id=user.user_id,
        )
        session.add(participant)
        session.flush()
    session.add(_membership(participant, user.user_id, "assignee", user.user_id, now))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()  # 같은 사람이 동시에 두 번 눌렀다
        return True, ()
    return False, ()


def add_member(
    session: Session,
    site_id: int,
    actor: CurrentUser,
    email: str,
    role_raw: str,
    now: datetime,
    contact_id: str = "",
    same_name: str = "",
) -> tuple[str, ...]:
    """가입한 사용자를 참여자로 추가한다. 그 회사가 처음이면 협력업체로 참여시킨다.

    같은 현장에 같은 이름 업체가 있으면 조정자가 붙일지(same_name="attach:<id>") 따로 둘지
    ("separate") 고를 때까지 저장하지 않는다(D-066, 자동 병합 없음). contact_id를 주면 그
    업체 명부의 사람과 계정을 연결한다.
    """
    require_role(session, actor, site_id, MANAGE_ROLES)
    if role_raw not in ASSIGNABLE_ROLES:
        return ("역할을 고르세요.",)
    role: Role = role_raw
    target = auth_service.find_user(session, email)
    if target is None or not target.is_active:
        return (
            "가입한 사용자의 휴대폰 번호나 이메일을 입력하세요. "
            "초대 문자·메일은 아직 보내지 않습니다.",
        )
    if repository.active_membership(session, target.user_id, site_id) is not None:
        return ("이미 이 현장에 참여 중입니다. 역할을 바꾸려면 회수한 뒤 다시 추가하세요.",)
    participant = repository.participant_of(session, site_id, target.organization_id)
    if role == "board":
        # 게시 계정은 현장 공용 화면이라 업체를 따로 만들지 않고 원청 아래에 둔다(D-067)
        participant = repository.prime_participant(session, site_id)
    if participant is None:
        matches = _same_name(session, site_id, target.organization_name)
        if matches and not same_name:
            return (SAME_NAME_MEMBER,)
        if same_name.startswith("attach:"):
            chosen = next((p for p in matches if f"attach:{p.id}" == same_name), None)
            if chosen is None:
                return ("붙일 업체를 다시 고르세요.",)
            error = _attach(session, chosen, target.user_id, target.organization_id)
            if error:
                session.rollback()
                return (error,)
            participant = chosen
    if participant is not None and participant.ended_at is not None:
        session.rollback()
        return ("제외한 업체입니다. 먼저 복귀시켜 주세요.",)
    if role == "coordinator" and (participant is None or participant.kind != "prime"):
        session.rollback()
        return ("조정자는 원청 소속 사용자만 될 수 있습니다.",)
    if participant is None:
        participant = ProjectParticipant(
            site_id=site_id,
            organization_id=target.organization_id,
            kind="subcontractor",
            created_by_user_id=actor.user_id,
        )
        session.add(participant)
        session.flush()
    session.add(_membership(participant, target.user_id, role, actor.user_id, now))
    if contact_id:
        contact = repository.contact(session, site_id, _int(contact_id) or -1)
        if contact is None or contact.participant_id != participant.id or contact.user_id:
            session.rollback()
            return ("연결할 명부의 사람은 같은 업체의 계정 미연결 담당자만 고를 수 있습니다.",)
        contact.user_id = target.user_id
    try:
        session.commit()
    except IntegrityError:
        # 같은 사용자를 동시에 두 번 추가했거나 이미 명부의 다른 사람과 연결된 경우
        session.rollback()
        return ("이미 이 현장에 참여 중이거나 명부의 다른 사람과 연결돼 있습니다.",)
    return ()


def _attach(
    session: Session, participant: ProjectParticipant, user_id: int, user_org_id: int
) -> str | None:
    """같은 이름 업체에 사용자를 붙인다(조정자가 고른 경우만).

    - 명부로만 만든 업체(사용자 0명)면 그 참여 업체를 사용자의 회사로 바꾼다.
    - 이미 사용자가 있는 업체면 사용자를 그 회사로 옮긴다. 다른 현장·동료·명부 연결이 없는
      새 가입자만 옮긴다(다른 현장의 소속이 바뀌지 않게).
    """
    if not auth_service.organizations_with_users(session, [participant.organization_id]):
        participant.organization_id = user_org_id
        session.flush()
        return None
    movable = (
        auth_service.organization_user_count(session, user_org_id) == 1
        and not repository.active_site_ids(session, user_id, ALL_ROLES)
        and not repository.organization_has_participants(session, user_org_id)
        and not repository.user_has_contact_links(session, user_id)
    )
    if not movable:
        return (
            "이 사용자는 다른 현장·동료와 이미 연결돼 있어 이 업체로 옮길 수 없습니다. "
            "다른 업체로 추가하세요."
        )
    auth_service.move_user_to_organization(session, user_id, participant.organization_id)
    session.flush()
    return None


def _same_name(session: Session, site_id: int, name: str) -> list[ProjectParticipant]:
    participants = repository.participants(session, site_id)
    names = auth_service.organization_names(session, (p.organization_id for p in participants))
    key = _name_key(name)
    return [p for p in participants if _name_key(names.get(p.organization_id, "")) == key]


def _name_key(name: str) -> str:
    """같은 이름 비교: 앞뒤·연속 공백과 영문 대소문자만 무시한다(사업자 확인 없음)."""
    return " ".join(name.split()).casefold()


def register_participant(
    session: Session, site_id: int, actor: CurrentUser, form: ParticipantForm
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """사람 없이 참여 업체를 등록한다(원청 조정자, D-066). (오류, 같은 이름 업체 표시 이름)."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    name = " ".join(form.organization_name.split())
    errors = _participant_errors(form, need_name=True)
    if errors:
        return errors, ()
    matches = _same_name(session, site_id, name)
    if matches and not form.confirm_same_name:
        names = auth_service.organization_names(session, (p.organization_id for p in matches))
        shown = tuple(f"{names[p.organization_id]} · {_group_label(p)}" for p in matches)
        return (SAME_NAME_PARTICIPANT,), shown
    organization_id = auth_service.create_organization(session, name)
    participant = ProjectParticipant(
        site_id=site_id,
        organization_id=organization_id,
        kind="subcontractor",
        created_by_user_id=actor.user_id,
    )
    _apply_participant_values(participant, form)
    session.add(participant)
    session.commit()
    return (), ()


def edit_participant(
    session: Session, site_id: int, actor: CurrentUser, participant_id: int, form: ParticipantForm
) -> tuple[str, ...]:
    """구분·맡은 공종·사업자번호·참여 시작일 수정. 원청은 구분이 없다."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    participant = _participant_or_404(session, site_id, participant_id)
    is_prime = participant.kind == "prime"
    errors = _participant_errors(form, need_name=False, prime=is_prime)
    if errors:
        return errors
    _apply_participant_values(participant, form)
    if is_prime:
        participant.category = None
    session.commit()
    return ()


def end_participant(
    session: Session, site_id: int, actor: CurrentUser, participant_id: int, now: datetime
) -> tuple[str, ...]:
    """제외(참여 종료): 실행 업체·조치 담당 선택에서만 빠진다. 지난 작업·기록·멤버십은 그대로다."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    participant = _participant_or_404(session, site_id, participant_id)
    if participant.kind == "prime":
        return ("원청은 제외할 수 없습니다.",)
    if participant.ended_at is not None:
        return ("이미 제외한 업체입니다.",)
    participant.ended_at = now
    participant.ended_by_user_id = actor.user_id
    session.commit()
    return ()


def resume_participant(
    session: Session, site_id: int, actor: CurrentUser, participant_id: int
) -> tuple[str, ...]:
    require_role(session, actor, site_id, MANAGE_ROLES)
    participant = _participant_or_404(session, site_id, participant_id)
    if participant.ended_at is None:
        return ("참여 중인 업체입니다.",)
    participant.ended_at = None
    participant.ended_by_user_id = None
    session.commit()
    return ()


def add_contact(
    session: Session,
    site_id: int,
    actor: CurrentUser,
    participant_id: int,
    form: ContactForm,
    now: datetime,
) -> tuple[str, ...]:
    """업체 담당자 명부에 사람을 더한다(계정 없이)."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    _participant_or_404(session, site_id, participant_id)
    name = " ".join(form.name.split())
    errors = _contact_errors(form)
    if errors:
        return errors
    session.add(
        ParticipantContact(
            site_id=site_id,
            participant_id=participant_id,
            name=name,
            job_title=form.job_title.strip(),
            phone=form.phone.strip(),
            memo=form.memo.strip(),
            created_at=now,
            created_by_user_id=actor.user_id,
        )
    )
    session.commit()
    return ()


def edit_contact(
    session: Session, site_id: int, actor: CurrentUser, contact_id: int, form: ContactForm
) -> tuple[str, ...]:
    """명부 담당자의 이름·직책·연락처·메모를 고친다(C04-45 후속). 계정 연결은 그대로."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    contact = _contact_or_404(session, site_id, contact_id)
    errors = _contact_errors(form)
    if errors:
        return errors
    contact.name = " ".join(form.name.split())
    contact.job_title = form.job_title.strip()
    contact.phone = form.phone.strip()
    contact.memo = form.memo.strip()
    session.commit()
    return ()


def _contact_errors(form: ContactForm) -> tuple[str, ...]:
    name = " ".join(form.name.split())
    errors = [] if name else ["담당자 이름을 입력하세요."]
    for value, limit, label in (
        (name, 40, "이름"),
        (form.job_title.strip(), 40, "직책"),
        (form.phone.strip(), 30, "연락처"),
        (form.memo.strip(), 200, "메모"),
    ):
        if len(value) > limit:
            errors.append(f"{label}: {limit}자 이내로 입력하세요.")
    return tuple(errors)


def remove_contact(
    session: Session, site_id: int, actor: CurrentUser, contact_id: int, now: datetime
) -> None:
    """명부에서 뺀다(행은 보존). 계정 연결도 함께 풀린다(활성 연결 인덱스에서 빠짐)."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    contact = _contact_or_404(session, site_id, contact_id)
    contact.removed_at = now
    session.commit()


def link_contact(
    session: Session, site_id: int, actor: CurrentUser, contact_id: int, email: str
) -> tuple[str, ...]:
    """명부의 사람을 가입한 계정과 연결한다. 그 사용자의 회사 = 업체 회사일 때만(D-066)."""
    require_role(session, actor, site_id, MANAGE_ROLES)
    contact = _contact_or_404(session, site_id, contact_id)
    if contact.user_id is not None:
        return ("이미 계정이 연결돼 있습니다. 먼저 연결을 해제하세요.",)
    target = auth_service.find_user(session, email)
    if target is None or not target.is_active:
        return ("가입한 사용자의 휴대폰 번호나 이메일을 입력하세요.",)
    participant = repository.participant(session, site_id, contact.participant_id)
    if participant is None or participant.organization_id != target.organization_id:
        return ("이 업체 소속 사용자만 연결할 수 있습니다. 먼저 참여자로 추가해 업체를 맞추세요.",)
    contact.user_id = target.user_id
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return ("이 사용자는 이 현장 명부의 다른 사람과 이미 연결돼 있습니다.",)
    return ()


def unlink_contact(session: Session, site_id: int, actor: CurrentUser, contact_id: int) -> None:
    require_role(session, actor, site_id, MANAGE_ROLES)
    contact = _contact_or_404(session, site_id, contact_id)
    contact.user_id = None
    session.commit()


def _participant_or_404(session: Session, site_id: int, participant_id: int) -> ProjectParticipant:
    participant = repository.participant(session, site_id, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="참여 업체를 찾을 수 없습니다")
    return participant


def _contact_or_404(session: Session, site_id: int, contact_id: int) -> ParticipantContact:
    contact = repository.contact(session, site_id, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다")
    return contact


def _participant_errors(
    form: ParticipantForm, need_name: bool, prime: bool = False
) -> tuple[str, ...]:
    errors = []
    name = " ".join(form.organization_name.split())
    if need_name and not name:
        errors.append("업체 이름을 입력하세요.")
    if len(name) > auth_service.ORGANIZATION_MAX:
        errors.append(f"업체 이름은 {auth_service.ORGANIZATION_MAX}자 이내로 입력하세요.")
    if not prime and form.category not in CATEGORY_LABELS:
        errors.append("업체 구분을 고르세요.")
    trades = [" ".join(t.split()) for t in form.work_trades]
    if not prime and not any(trades):
        errors.append("맡은 업종을 하나 이상 고르세요. 목록에 없으면 직접 입력을 고르세요.")
    if any(t not in WORK_TRADE_NAMES and len(t) > TRADE_CUSTOM_MAX for t in trades):
        errors.append(f"직접 입력한 업종은 {TRADE_CUSTOM_MAX}자 이내로 입력하세요.")
    if len(form.trade_note.strip()) > TRADE_NOTE_MAX:
        errors.append(f"공종 메모는 {TRADE_NOTE_MAX}자 이내로 입력하세요.")
    if len(form.business_no.strip()) > 20:
        errors.append("사업자번호는 20자 이내로 입력하세요.")
    if form.joined_on.strip() and _date(form.joined_on) is None:
        errors.append("참여 시작일을 날짜로 입력하세요.")
    return tuple(errors)


def _apply_participant_values(participant: ProjectParticipant, form: ParticipantForm) -> None:
    participant.category = form.category
    participant.trade_note = form.trade_note.strip() or None
    picked = list(dict.fromkeys(t for t in (" ".join(x.split()) for x in form.work_trades) if t))
    # 목록 업종은 목록 순서, 직접 입력한 업종은 그 뒤에(C04-45)
    participant.work_trades = [n for n in WORK_TRADE_NAMES if n in picked] + [
        t for t in picked if t not in WORK_TRADE_NAMES
    ]
    participant.business_no = form.business_no.strip() or None
    participant.joined_on = _date(form.joined_on)


def _group_label(participant: ProjectParticipant) -> str:
    if participant.kind == "prime":
        return KIND_LABELS["prime"]
    return CATEGORY_LABELS[cast(Category, participant.category or "subcontractor")]


def _date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def revoke_member(
    session: Session, site_id: int, actor: CurrentUser, membership_id: int, now: datetime
) -> tuple[str, ...]:
    require_role(session, actor, site_id, MANAGE_ROLES)
    coordinators = repository.lock_active_coordinators(session, site_id)
    membership = session.get(ProjectMembership, membership_id)
    if membership is None or membership.site_id != site_id or membership.revoked_at is not None:
        session.rollback()
        raise HTTPException(status_code=404, detail="참여자를 찾을 수 없습니다")
    if membership.role == "coordinator" and len(coordinators) <= 1:
        session.rollback()
        return ("마지막 조정자는 회수할 수 없습니다. 다른 조정자를 먼저 추가하세요.",)
    membership.revoked_at = now
    membership.revoked_by_user_id = actor.user_id
    session.commit()
    return ()


def grant_existing_site(session: Session, site_id: int, email: str, now: datetime) -> str:
    """참여 업체가 없는 기존 현장(0010 이전)에 개발자가 명시한 사용자를 원청 조정자로 둔다.

    소유자를 추정하지 않는다. 이미 원청이 있으면 그 회사 사용자만 조정자로 추가한다.
    """
    user = auth_service.find_user_by_email(session, email)
    if user is None or not user.is_active:
        raise ValueError(f"가입한 활성 사용자가 아님: {email}")
    if repository.active_membership(session, user.user_id, site_id) is not None:
        raise ValueError("이미 이 현장에 참여 중")
    participants = repository.participants(session, site_id)
    prime = next((p for p in participants if p.kind == "prime"), None)
    if prime is not None and prime.organization_id != user.organization_id:
        raise ValueError("이 현장의 원청 회사 소속이 아님")
    try:
        if prime is None:
            prime = ProjectParticipant(
                site_id=site_id, organization_id=user.organization_id, kind="prime"
            )
            session.add(prime)
            session.flush()
        session.add(_membership(prime, user.user_id, "coordinator", None, now))
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ValueError(f"없는 현장이거나 동시에 지정됨: {site_id}") from error
    return f"현장 {site_id}: {user.display_name}({user.organization_name})을 조정자로 지정"


def build_members_view(
    session: Session,
    site_id: int,
    site_name: str,
    viewer: CurrentUser,
    member_form: MemberForm | None = None,
    participant_form: ParticipantForm | None = None,
    participant_same_name: tuple[str, ...] = (),
    errors: tuple[str, ...] = (),
    message: str | None = None,
) -> MembersView:
    """업체 카드(구분·공종·기간·상태) + 담당자 명부 + 참여자. 쿼리 수는 업체·사람 수와 무관하다."""
    my_role = require_role(session, viewer, site_id, ALL_ROLES)
    can_manage = my_role in MANAGE_ROLES
    show_detail = my_role in CONTACT_DETAIL_ROLES
    member_form = member_form or MemberForm()
    participant_form = participant_form or ParticipantForm()
    participants = repository.participants(session, site_id)
    memberships = repository.active_memberships(session, site_id)
    contacts = repository.contacts(session, site_id)
    users = auth_service.describe_users(
        session,
        [m.user_id for m in memberships] + [c.user_id for c in contacts if c.user_id is not None],
    )
    names = auth_service.organization_names(session, (p.organization_id for p in participants))
    role_of = {m.user_id: cast(Role, m.role) for m in memberships}
    members_of: dict[int, list[ProjectMembership]] = {}
    for m in memberships:
        members_of.setdefault(m.participant_id, []).append(m)
    contacts_of: dict[int, list[ParticipantContact]] = {}
    for c in contacts:
        contacts_of.setdefault(c.participant_id, []).append(c)
    views = tuple(
        ParticipantView(
            participant_id=p.id,
            organization_name=names.get(p.organization_id, "이름 없음"),
            kind_label=_group_label(p),
            is_prime=p.kind == "prime",
            category="" if p.kind == "prime" else (p.category or "subcontractor"),
            trade_note=p.trade_note or "",
            work_trades=tuple(p.work_trades or ()),
            business_no=(p.business_no or "") if can_manage else None,
            joined_on="" if p.joined_on is None else p.joined_on.isoformat(),
            status_text=_status_text(p),
            is_ended=p.ended_at is not None,
            members=tuple(
                _member_view(m, users[m.user_id], viewer, can_manage)
                for m in members_of.get(p.id, [])
            ),
            contacts=tuple(
                _contact_view(c, users, role_of, show_detail) for c in contacts_of.get(p.id, [])
            ),
            people_count=_people_count(contacts_of.get(p.id, []), members_of.get(p.id, [])),
        )
        for p in participants
    )
    contact_options = tuple(
        Option(
            str(c.id),
            f"{names.get(p.organization_id, '')} · {c.name}"
            + (f" {c.job_title}" if c.job_title else ""),
            str(c.id) == member_form.contact_id,
        )
        for p in participants
        if p.ended_at is None
        for c in contacts_of.get(p.id, [])
        if c.user_id is None
    )
    return MembersView(
        site_id=site_id,
        site_name=site_name,
        my_role_label=ROLE_LABELS[my_role],
        can_manage=can_manage,
        participants=views,
        role_options=tuple(
            RoleOption(r, ROLE_LABELS[r], r == member_form.role) for r in ASSIGNABLE_ROLES
        ),
        category_options=tuple(
            Option(c, label, c == participant_form.category) for c, label in CATEGORY_LABELS.items()
        ),
        contact_options=contact_options if can_manage else (),
        member_form=member_form,
        participant_form=participant_form,
        participant_same_name=participant_same_name,
        member_same_name=_member_same_name(session, site_id, member_form, errors),
        errors=errors,
        message=message,
        join_code=_shown_code(session, site_id) if can_manage else "",
    )


def _shown_code(session: Session, site_id: int) -> str:
    row = repository.join_code(session, site_id)
    return "" if row is None else show_code(row.code)


def _member_same_name(
    session: Session, site_id: int, form: MemberForm, errors: tuple[str, ...]
) -> tuple[Option, ...]:
    """참여자 추가에서 같은 이름 업체 경고가 났을 때 고를 수 있는 선택지."""
    if SAME_NAME_MEMBER not in errors:
        return ()
    target = auth_service.find_user_by_email(session, form.email)
    if target is None:
        return ()
    matches = _same_name(session, site_id, target.organization_name)
    names = auth_service.organization_names(session, (p.organization_id for p in matches))
    return (
        *(
            Option(f"attach:{p.id}", f"{names[p.organization_id]}({_group_label(p)})에 붙이기")
            for p in matches
        ),
        Option("separate", "다른 업체로 따로 추가"),
    )


def _people_count(
    contacts: Sequence[ParticipantContact], members: Sequence[ProjectMembership]
) -> int:
    linked = {c.user_id for c in contacts if c.user_id is not None}
    return len(contacts) + sum(1 for m in members if m.user_id not in linked)


def _status_text(participant: ProjectParticipant) -> str:
    if participant.ended_at is not None:
        return f"제외 · {participant.ended_at.astimezone(KST):%Y-%m-%d}"
    if participant.joined_on is not None:
        return f"참여 중 · {participant.joined_on:%Y-%m-%d}부터"
    return "참여 중"


def _contact_view(
    contact: ParticipantContact,
    users: dict[int, UserInfo],
    role_of: dict[int, Role],
    show_detail: bool,
) -> ContactView:
    account = None
    if contact.user_id is not None and contact.user_id in users:
        role = role_of.get(contact.user_id)
        account = f"{users[contact.user_id].display_name} 계정 · " + (
            ROLE_LABELS[role] if role else "참여 권한 없음"
        )
    return ContactView(
        contact_id=contact.id,
        name=contact.name,
        job_title=contact.job_title,
        phone=contact.phone if show_detail else None,
        memo=contact.memo if show_detail else None,
        account_text=account,
    )


def _member_view(
    membership: ProjectMembership, user: UserInfo, viewer: CurrentUser, can_manage: bool
) -> MemberView:
    return MemberView(
        membership_id=membership.id,
        display_name=user.display_name,
        email=user.email if can_manage else None,
        role_label=ROLE_LABELS[cast(Role, membership.role)],
        granted_text=f"{membership.created_at.astimezone(KST):%Y-%m-%d %H:%M}",
        is_me=user.user_id == viewer.user_id,
    )


def _membership(
    participant: ProjectParticipant,
    user_id: int,
    role: Role,
    granted_by: int | None,
    now: datetime,
) -> ProjectMembership:
    return ProjectMembership(
        site_id=participant.site_id,
        participant_id=participant.id,
        user_id=user_id,
        role=role,
        granted_by_user_id=granted_by,
        created_at=now,
    )


def build_team_all(
    session: Session, viewer: CurrentUser, sites: Sequence[SiteRecord]
) -> TeamAllView:
    """업체 탭 전체 현장(C04-36): 현장마다 업체 화면과 같은 계산으로 줄을 모은다(현장은 몇 곳).

    연락처·사업자번호 노출은 현장별 역할 규칙(build_members_view)을 그대로 따른다.
    """
    rows = tuple(
        TeamRow(s.site_id, s.name, p)
        for s in sites
        for p in build_members_view(session, s.site_id, s.name, viewer).participants
    )
    return TeamAllView(rows=rows)


def contact_cards(
    session: Session, viewer: CurrentUser, site_id: int, contact_ids: list[int]
) -> dict[int, ContactCard]:
    """이 현장 명부 담당자 카드(D-111). 전화번호는 명부와 같은 규칙으로 열람자에게 숨긴다."""
    if not contact_ids:
        return {}
    show_phone = require_role(session, viewer, site_id, ALL_ROLES) in CONTACT_DETAIL_ROLES
    rows = repository.contacts_by_ids(session, site_id, contact_ids)
    parts = {p.id: p for p in repository.participants(session, site_id)}
    names = auth_service.organization_names(session, (p.organization_id for p in parts.values()))
    return {
        c.id: ContactCard(
            contact_id=c.id,
            name=c.name,
            job_title=c.job_title,
            company=names.get(parts[c.participant_id].organization_id, "")
            if c.participant_id in parts
            else "",
            phone=(c.phone or None) if show_phone else None,
        )
        for c in rows
    }


def contact_choices(session: Session, viewer: CurrentUser, site_id: int) -> tuple[ContactCard, ...]:
    """대화방에서 고를 수 있는 이 현장의 명부 담당자(지운 사람 제외)."""
    ids = [c.id for c in repository.contacts(session, site_id)]
    cards = contact_cards(session, viewer, site_id, ids)
    return tuple(cards[i] for i in ids if i in cards)
