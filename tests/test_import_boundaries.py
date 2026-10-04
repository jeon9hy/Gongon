"""docs/architecture.md의 의존 규칙을 import 수준에서 검사한다.

규칙을 바꿀 때는 이 파일과 docs/architecture.md, docs/decisions.md를 함께 갱신한다.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

DB_HTTP_WEB = (
    "sqlalchemy",
    "psycopg",
    "alembic",
    "httpx",
    "httpx2",
    "requests",
    "urllib.request",
    "fastapi",
    "starlette",
)

# (검사 대상 패키지, 금지 import 접두사, 이유)
BOUNDARY_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("engine", ("app",), "engine은 app을 참조하지 않는다"),
    (
        "engine.judgment",
        ("engine.forecast", "engine.geo", *DB_HTTP_WEB),
        "순수 판정은 DB·HTTP·웹·예보 수집 코드 없이 호출 가능해야 한다",
    ),
    (
        "engine.geo",
        ("engine.forecast", "engine.judgment", *DB_HTTP_WEB),
        "위치·격자 변환은 계산만 한다",
    ),
    (
        "app.core",
        ("app.features", "app.jobs"),
        "공통 기반은 기능·실행 작업을 참조하지 않는다",
    ),
)

# 다른 기능에서 직접 쓰면 안 되는 기능 내부 모듈. 기능 간 호출은 service·schemas로만 한다.
FEATURE_PRIVATE_MODULES = ("repository", "models", "router")


def module_name_for(path: Path) -> tuple[str, bool]:
    """파일 경로를 (모듈 이름, 패키지 __init__ 여부)로 바꾼다."""
    parts = path.relative_to(REPO_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        return ".".join(parts[:-1]), True
    return ".".join(parts), False


def imported_modules(source: str, module_name: str, is_package: bool) -> set[str]:
    """소스가 import하는 모듈 이름을 절대 경로로 모은다. 상대 import도 풀어서 포함한다."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                package_parts = module_name.split(".")
                if not is_package:
                    package_parts = package_parts[:-1]
                anchor = package_parts[: len(package_parts) - (node.level - 1)]
                base = ".".join([*anchor, *([node.module] if node.module else [])])
            found.add(base)
            # `from engine import forecast`처럼 하위 모듈을 이름으로 가져오는 경우도 잡는다.
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def imports_under(package_dir: Path) -> Iterator[tuple[Path, str]]:
    """패키지 아래 모든 .py 파일의 (파일, import한 모듈) 쌍."""
    for path in sorted(package_dir.rglob("*.py")):
        module_name, is_package = module_name_for(path)
        source = path.read_text(encoding="utf-8")
        for imported in sorted(imported_modules(source, module_name, is_package)):
            yield path, imported


def is_forbidden(imported: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    return any(
        imported == prefix or imported.startswith(prefix + ".") for prefix in forbidden_prefixes
    )


def is_cross_feature_private_import(own_feature: str, imported: str) -> bool:
    """다른 기능의 repository·models·router를 직접 import하는지 판단한다."""
    parts = imported.split(".")
    if len(parts) < 4 or parts[:2] != ["app", "features"]:
        return False
    return parts[2] != own_feature and parts[3] in FEATURE_PRIVATE_MODULES


@pytest.mark.parametrize(
    ("package", "forbidden_prefixes", "reason"),
    BOUNDARY_RULES,
    ids=[rule[0] for rule in BOUNDARY_RULES],
)
def test_package_respects_import_boundary(
    package: str, forbidden_prefixes: tuple[str, ...], reason: str
) -> None:
    package_dir = REPO_ROOT.joinpath(*package.split("."))
    if not package_dir.is_dir():
        pytest.skip(f"{package} 패키지가 아직 없음")

    violations = [
        f"{path.relative_to(REPO_ROOT)} -> {imported}"
        for path, imported in imports_under(package_dir)
        if is_forbidden(imported, forbidden_prefixes)
    ]

    assert not violations, f"{reason}:\n" + "\n".join(violations)


def test_features_call_each_other_only_through_service() -> None:
    features_dir = REPO_ROOT / "app" / "features"
    if not features_dir.is_dir():
        pytest.skip("app/features 패키지가 아직 없음")

    violations = [
        f"{path.relative_to(REPO_ROOT)} -> {imported}"
        for path, imported in imports_under(features_dir)
        if is_cross_feature_private_import(path.relative_to(features_dir).parts[0], imported)
    ]

    assert not violations, "다른 기능은 service·schemas로만 호출한다:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    ("source", "module_name", "is_package", "expected_import"),
    [
        ("import app.main", "engine.judgment.evaluate", False, "app.main"),
        ("from app.features import sites", "engine.geo.grid", False, "app.features.sites"),
        ("from ..forecast import client", "engine.judgment.evaluate", False, "engine.forecast"),
        ("from .. import geo", "engine.judgment", True, "engine.geo"),
        ("from sqlalchemy.orm import Session", "engine.judgment.evaluate", False, "sqlalchemy.orm"),
    ],
)
def test_import_collector_catches_absolute_and_relative_imports(
    source: str, module_name: str, is_package: bool, expected_import: str
) -> None:
    # 검사기가 우회 경로(상대 import)를 놓치면 경계 테스트가 거짓 통과한다.
    assert expected_import in imported_modules(source, module_name, is_package)


@pytest.mark.parametrize(
    ("own_feature", "imported", "expected"),
    [
        ("judgments", "app.features.sites.repository", True),
        ("judgments", "app.features.sites.models.Site", True),
        ("judgments", "app.features.sites.service", False),
        ("judgments", "app.features.sites.schemas", False),
        ("sites", "app.features.sites.repository", False),
        ("judgments", "app.core.db", False),
    ],
)
def test_cross_feature_rule_allows_only_public_entry_points(
    own_feature: str, imported: str, expected: bool
) -> None:
    assert is_cross_feature_private_import(own_feature, imported) is expected
