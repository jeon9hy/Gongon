"""rules/ 폴더의 기준표를 읽는다. 공종 추가는 YAML 파일 추가로 한다(총정리 §4.3)."""

from collections.abc import Iterable
from functools import lru_cache
from types import MappingProxyType

from app.core.config import REPO_ROOT
from engine.judgment import RuleSet, load_rule_set

RULES_DIR = REPO_ROOT / "rules"

# 화면에서 고를 수 있는 공종(총정리 §1 표, §3 4단계). 기준표가 없는 공종은 판정하지 않는다(D-017).
# 타워크레인 운전은 예보로 순간풍속을 알 수 없어 늘 확인 필요만 나오므로 뺐다(D-032).
WORK_TYPE_LABELS = (
    "철골 작업",
    "콘크리트 타설",
    "이동식 크레인",
    "고소작업대",
    "도장·방수",
    "아스팔트 포장",
)
# 공종과 관계없이 모든 현장에 함께 판정하는 기준(총정리 §1 '공통(폭염)', D-027).
COMMON_LABELS = ("폭염(공통)",)


@lru_cache
def rule_sets_by_label() -> MappingProxyType[str, RuleSet]:
    """공종 이름 → 기준. 기준표 형식이 틀리면 앱 시작·첫 사용 시 바로 실패한다."""
    rule_sets = {}
    for path in sorted(RULES_DIR.glob("*.yaml")):
        rule_set = load_rule_set(path)
        if rule_set.work_type_label not in (*WORK_TYPE_LABELS, *COMMON_LABELS):
            raise ValueError(f"{path.name}: 알 수 없는 공종 {rule_set.work_type_label!r}")
        rule_sets[rule_set.work_type_label] = rule_set
    return MappingProxyType(rule_sets)


def judged_labels(work_types: Iterable[str]) -> tuple[str, ...]:
    """현장에 표시·판정할 항목: 고른 공종 + 기준표가 있는 공통 기준."""
    rule_sets = rule_sets_by_label()
    return (*work_types, *(label for label in COMMON_LABELS if label in rule_sets))
