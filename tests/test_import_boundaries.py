"""docs/architecture.md의 의존 규칙을 import 수준에서 검사한다.

규칙을 바꿀 때는 이 표와 docs/architecture.md, docs/decisions.md를 함께 갱신한다.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# (검사 대상 패키지, 금지 import 접두사, 이유)
BOUNDARY_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("engine", ("app",), "engine은 app을 참조하지 않는다"),
    (
        "engine.judgment",
        (
            "engine.forecast",
            "engine.geo",
            "sqlalchemy",
            "psycopg",
            "httpx",
            "httpx2",
            "requests",
            "urllib.request",
            "fastapi",
            "starlette",
        ),
        "순수 판정은 DB·HTTP·웹·예보 수집 코드 없이 호출 가능해야 한다",
    ),
)


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


def is_forbidden(imported: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    return any(
        imported == prefix or imported.startswith(prefix + ".") for prefix in forbidden_prefixes
    )


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

    violations = []
    for path in sorted(package_dir.rglob("*.py")):
        module_name, is_package = module_name_for(path)
        source = path.read_text(encoding="utf-8")
        for imported in sorted(imported_modules(source, module_name, is_package)):
            if is_forbidden(imported, forbidden_prefixes):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {imported}")

    assert not violations, f"{reason}:\n" + "\n".join(violations)


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
