"""service/rules 의 순수성: classfit 안에서는 classfit.core 와 classfit.service.rules 만 부른다. DB 없음.

계약 ② (layers)는 rules 를 맨 아래에 둘 뿐이다. rules 가 crud·models·database 를 불러도
계약 ① 은 service > crud 라 지나가므로(Contracts: 3 kept 그대로) 이 시험이 잡는다(T2a 결정 iv).
DB 드라이버·ORM(sqlalchemy·psycopg)도 부르지 않는다.
"""

import ast
from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "src" / "classfit" / "service" / "rules"
PACKAGE = "classfit.service.rules"
ALLOWED = ("classfit.core", PACKAGE)
DB_LIBS = ("sqlalchemy", "psycopg")


def _imported(path: Path) -> list[str]:
    """파일이 부르는 이름 전부(from X import y 는 X.y). 상대 import 는 rules 패키지 기준으로 푼다."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = PACKAGE.rsplit(".", node.level - 1)[0]
                base = f"{parent}.{base}" if base else parent
            names += [f"{base}.{a.name}" for a in node.names]
    return names


def _inside(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def test_rules_imports_no_db_layers() -> None:
    files = sorted(RULES.glob("*.py"))
    assert RULES / "__init__.py" in files, f"rules 패키지를 못 찾았다: {RULES}"
    bad = [
        f"{path.name}: {name}"
        for path in files
        for name in _imported(path)
        if (_inside(name, "classfit") and not any(_inside(name, p) for p in ALLOWED))
        or any(_inside(name, lib) for lib in DB_LIBS)
    ]
    assert bad == [], f"rules 가 허용 밖을 부른다: {bad}"
