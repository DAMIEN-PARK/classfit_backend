#!/usr/bin/env python3
"""plan/ 문서를 OKF(Open Knowledge Format) 묶음으로 맞추는 도구.

하는 일은 넷이다.
  label  문서 머리말에 `type` 을 붙인다. 읽히지 않는 머리말 줄은 따옴표로 고친다. 본문은 건드리지 않는다.
  link   본문에 백틱으로 적은 `….md` 를 링크로 바꾼다. 글자는 그대로 두고 링크로 감싸기만 한다.
  index  폴더마다 목차 `index.md` 를 만든다(자동 생성 표시가 있는 것만 덮어쓴다).
  check  규격 §11 의 세 조건을 검사하고 링크 상태를 센다. 위반이 있으면 exit 1.

label·link·index 는 기본이 미리 보기다. 실제로 쓰려면 `--apply` 를 준다.

  python3 scripts/okf/okf.py label            # 무엇이 바뀔지 보기
  python3 scripts/okf/okf.py label --apply
  python3 scripts/okf/okf.py link --apply
  python3 scripts/okf/okf.py index --apply
  python3 scripts/okf/okf.py check

설정은 같은 폴더의 okf.toml 에 있다(제외 폴더 · 종류 규칙 · 잇기 규칙 · 기준 규격 커밋).
"""
from __future__ import annotations

import argparse
import collections
import fnmatch
import os
import posixpath
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    sys.exit(
        "멈춤: 이 파이썬에 PyYAML 이 없다 — " + sys.executable + "\n"
        "  폴더에 .python-version 이 있으면 python3 가 다른 판을 가리킨다.\n"
        "  backend 에서는 가상환경의 파이썬으로 돌린다: .venv/bin/python ../plan/scripts/okf/okf.py …"
    )

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parent.parent
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
KEY_LINE = re.compile(r"^([A-Za-z_][\w-]*):(?:\s+(.*))?$")
DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")
RESERVED = {"index.md", "log.md"}
ALWAYS_SKIP = {".git", ".omc", "node_modules", "__pycache__"}
# 링크가 가리키는 곳이 될 수 없는 폴더(남의 꾸러미가 든 곳)
NEVER_TARGET = ALWAYS_SKIP | {".venv", "venv", "site-packages"}
# 링크 경로에 그대로 넣으면 마크다운이 깨지는 글자
UNSAFE_IN_PATH = set("%#?<>[]|`\"'")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
GENERATED_MARK = "<!-- okf:generated — scripts/okf/okf.py index 가 만든다. 손으로 고치지 않는다. -->"

# 백틱 안의 `경로.md` 또는 `경로.md#닻`
TOKEN = re.compile(r"`([^`\n]+?\.md)(#[^`\n\s]*)?`")
# 경로로 볼 수 있는 글자만(한글 포함). `<n>`·`*`·빈칸이 있으면 틀이나 무늬다.
CLEAN_PATH = re.compile(r"^[\w./@+~\-]+$")
# link 가 만든 모양: [`….md`](경로)
LINKED = re.compile(r"\[(`[^`\n]+?\.md(?:#[^`\n\s]*)?`)\]\([^)\s]+\)")
MD_LINK = re.compile(r"\]\(([^)\s]+?\.md)(#[^)\s]*)?\)")


class OkfError(Exception):
    pass


@dataclass
class Config:
    okf_version: str
    spec_commit: str
    exclude_dirs: list[str]
    exclude_dir_globs: list[str]
    rules: list[dict]
    bundle_name: str
    workspace_aliases: list[str]
    external_roots: list[str]
    external_name_dirs: list[str]
    stop_names: set[str]
    old_version_dirs: list[str]
    no_link: list[dict]
    path_bases: list[str]
    external_names: list[dict]
    never_target_globs: list[str]

    @classmethod
    def load(cls, path: Path) -> "Config":
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        name = raw.get("bundle_name", "plan").strip("/")
        # 옛 열쇠 external_name_dirs 는 "T<숫자> 로 시작하는 이름만" 이라는 뜻이었다.
        names = list(raw.get("external_names", []))
        names += [{"dir": d, "match": r"^T\d"} for d in raw.get("external_name_dirs", [])]
        for n in names:
            n["dir"] = n["dir"].strip("/")
            n["skip"] = [s.strip("/") for s in n.get("skip", [])]
            re.compile(n["match"])
        return cls(
            path_bases=[b.strip("/") for b in raw.get("path_bases", [name])],
            external_names=names,
            never_target_globs=list(raw.get("never_target_globs", raw.get("exclude_dir_globs", []))),
            okf_version=raw["okf_version"],
            spec_commit=raw["spec_commit"],
            exclude_dirs=[d.strip("/") for d in raw.get("exclude_dirs", [])],
            exclude_dir_globs=list(raw.get("exclude_dir_globs", [])),
            rules=list(raw["rules"]),
            bundle_name=name,
            workspace_aliases=list(raw.get("workspace_aliases", [])),
            external_roots=list(raw.get("external_roots", [])),
            external_name_dirs=[d.strip("/") for d in raw.get("external_name_dirs", [])],
            stop_names=set(raw.get("stop_names", [])),
            old_version_dirs=[d.strip("/") for d in raw.get("old_version_dirs", [])],
            no_link=list(raw.get("no_link", [])),
        )

    def excluded(self, rel_dir: str) -> bool:
        if not rel_dir:
            return False
        parts = rel_dir.split("/")
        if any(p in ALWAYS_SKIP for p in parts):
            return True
        if any(fnmatch.fnmatch(parts[0], g) for g in self.exclude_dir_globs):
            return True
        return any(rel_dir == d or rel_dir.startswith(d + "/") for d in self.exclude_dirs)

    def never_a_target(self, rel: str) -> bool:
        """사본·런타임 폴더는 링크가 가리키는 곳이 될 수 없다."""
        parts = rel.split("/")
        if any(p in NEVER_TARGET for p in parts):
            return True
        if any(fnmatch.fnmatch(p, g) for p in parts for g in self.never_target_globs):
            return True
        return any(fnmatch.fnmatch(parts[0], g) for g in self.exclude_dir_globs)

    def type_for(self, rel: str) -> str:
        for rule in self.rules:
            if fnmatch.fnmatch(rel, rule["pattern"]):
                return rule["type"]
        raise OkfError(f"종류 규칙이 없는 문서: {rel} — okf.toml 의 rules 에 더한다")

    def in_old_version(self, rel: str) -> bool:
        return any(rel.startswith(d + "/") for d in self.old_version_dirs)


@dataclass
class Scan:
    concepts: list[str] = field(default_factory=list)
    reserved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def scan(root: Path, cfg: Config) -> Scan:
    out = Scan()
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        keep = []
        for d in sorted(dirnames):
            child = f"{rel_dir}/{d}" if rel_dir else d
            if d in ALWAYS_SKIP:
                continue
            if cfg.excluded(child):
                for sub, _dn, fn in os.walk(Path(dirpath) / d):
                    for f in fn:
                        if f.endswith(".md"):
                            out.skipped.append(os.path.relpath(os.path.join(sub, f), root).replace(os.sep, "/"))
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            if not f.endswith(".md"):
                continue
            rel = f"{rel_dir}/{f}" if rel_dir else f
            (out.reserved if f in RESERVED else out.concepts).append(rel)
    out.concepts.sort()
    out.reserved.sort()
    out.skipped.sort()
    return out


def parse_yaml(text: str):
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def repair_lines(lines: list[str]) -> tuple[list[str], list[str]]:
    """혼자서 YAML 로 안 읽히는 `키: 값` 줄만 값을 큰따옴표로 감싼다."""
    fixed, notes = [], []
    for line in lines:
        m = KEY_LINE.match(line)
        if m and m.group(2) is not None and parse_yaml(line) is None:
            new = f"{m.group(1)}: {quote(m.group(2))}"
            got = parse_yaml(new)
            if got != {m.group(1): m.group(2)}:
                raise OkfError(f"따옴표로 고쳐도 같은 값이 안 나온다: {line!r}")
            fixed.append(new)
            notes.append(m.group(1))
        else:
            fixed.append(line)
    return fixed, notes


def assert_body_kept(rel: str, original_body: str, new_text: str) -> None:
    """만든 글을 다시 읽어 머리말을 떼고, 남은 본문이 원본과 같은지 본다(조립에 쓴 값과 비교하지 않는다)."""
    again = FRONTMATTER.match(new_text)
    if again is None:
        raise OkfError(f"만든 글에서 머리말을 못 찾는다: {rel}")
    if new_text[again.end():] != original_body:
        raise OkfError(f"본문이 달라졌다: {rel}")


def read_checked(root: Path, rel: str) -> str:
    raw = (root / rel).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r\n" in raw:
        raise OkfError(f"BOM 또는 CRLF 가 있다: {rel}")
    return raw.decode("utf-8")


def write_all(root: Path, todo: list[tuple[str, str, str]]) -> None:
    """(경로, 읽었을 때의 글, 새 글) 묶음을 쓴다.

    쓰기 직전에 전부 다시 읽어, 읽은 뒤로 누가 고친 파일이 하나라도 있으면 아무것도 쓰지 않는다.
    plan/ 은 여러 세션이 같이 고치는 곳이다.
    """
    moved = [rel for rel, old, _new in todo if read_checked(root, rel) != old]
    if moved:
        raise OkfError("읽은 뒤에 바뀐 문서가 있다(아무것도 쓰지 않았다): " + ", ".join(moved))
    for rel, _old, new in todo:
        write_atomic(root / rel, new)


@dataclass
class Change:
    rel: str
    type: str
    action: str  # "같음" | "type 추가" | "type 바꿈" | "머리말 새로 만듦"
    repaired: list[str]
    new_text: str | None
    old_text: str = ""


def label_one(root: Path, rel: str, want: str) -> Change:
    text = read_checked(root, rel)
    m = FRONTMATTER.match(text)

    if m is None:
        if text.startswith("---\n"):
            raise OkfError(f"머리말이 닫히지 않았다: {rel}")
        h1 = re.search(r"^#\s+(.+?)\s*$", text, re.M)
        title = h1.group(1) if h1 else Path(rel).stem
        head = ["---", f"type: {want}", f"title: {quote(title)}"]
        d = DATE_IN_NAME.search(Path(rel).name)
        if d:
            head.append(f"date: {d.group(1)}")
        head += ["---", ""]
        new_text = "\n".join(head) + "\n" + text
        assert_body_kept(rel, "\n" + text, new_text)
        fm = parse_yaml("\n".join(head[1:-2]))
        if fm is None or fm.get("type") != want or fm.get("title") != title:
            raise OkfError(f"새 머리말이 기대와 다르다: {rel}")
        return Change(rel, want, "머리말 새로 만듦", [], new_text, text)

    body = text[m.end():]
    lines = m.group(1).split("\n")
    had = [ln for ln in lines if ln.startswith("type:")]
    if len(had) > 1:
        raise OkfError(f"type 줄이 둘 이상이다: {rel}")
    rest = [ln for ln in lines if not ln.startswith("type:")]
    rest, repaired = repair_lines(rest)
    new_lines = [f"type: {want}"] + rest
    fm = parse_yaml("\n".join(new_lines))
    if fm is None:
        raise OkfError(f"고친 뒤에도 머리말이 안 읽힌다: {rel}")
    if fm.get("type") != want:
        raise OkfError(f"type 이 기대와 다르다: {rel}")
    new_text = "---\n" + "\n".join(new_lines) + "\n---\n" + body
    assert_body_kept(rel, text[m.end():], new_text)
    before = parse_yaml(m.group(1))
    if before is not None:
        for k, v in before.items():
            if k != "type" and fm.get(k) != v:
                raise OkfError(f"머리말 값이 달라졌다: {rel} 의 {k}")
    if new_text == text:
        return Change(rel, want, "같음", [], None, text)
    action = "type 추가" if not had else ("type 바꿈" if had[0] != f"type: {want}" else "머리말 고침")
    return Change(rel, want, action, repaired, new_text, text)


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".okf-tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def is_generated_index(text: str) -> bool:
    """자동 생성 표시가 머리말 바로 뒤 첫 줄에 있을 때만 도구가 만든 목차로 본다."""
    m = FRONTMATTER.match(text)
    rest = text[m.end():] if m else text
    return rest.lstrip("\n").startswith(GENERATED_MARK)


def cmd_label(root: Path, cfg: Config, apply: bool) -> int:
    s = scan(root, cfg)
    changes = [label_one(root, rel, cfg.type_for(rel)) for rel in s.concepts]
    by_action = collections.Counter(c.action for c in changes)
    print(f"묶음 문서 {len(changes)}개 · 제외 {len(s.skipped)}개")
    for c in changes:
        mark = "" if not c.repaired else f"  (따옴표로 고친 줄: {', '.join(c.repaired)})"
        print(f"  {c.action:<12} {c.type:<18} {c.rel}{mark}")
    print("요약:", dict(by_action))
    if not apply:
        print("미리 보기다. 쓰려면 --apply")
        return 0
    todo = [(c.rel, c.old_text, c.new_text) for c in changes if c.new_text is not None]
    write_all(root, todo)
    print(f"쓴 파일 {len(todo)}개")
    return 0


# ── 잇기 ────────────────────────────────────────────────────────────────────

IN_BUNDLE = "묶음 안"
IN_PLAN = "묶음 폴더 안·묶음 밖"
OUTSIDE = "묶음 폴더 밖"


@dataclass
class Linker:
    root: Path
    ws: Path
    cfg: Config
    concepts: set[str]
    by_name: dict[str, list[str]]
    ext_by_name: dict[str, list[str]]

    @classmethod
    def build(cls, root: Path, ws: Path, cfg: Config, s: Scan) -> "Linker":
        by_name: dict[str, list[str]] = collections.defaultdict(list)
        for rel in s.concepts:
            by_name[os.path.basename(rel)].append(rel)
        ext: dict[str, list[str]] = collections.defaultdict(list)
        for rule in cfg.external_names:
            base = ws / rule["dir"]
            if not base.is_dir():
                continue
            want = re.compile(rule["match"])
            for p in sorted(base.rglob("*.md")):
                inside = p.relative_to(base).as_posix()
                ws_rel = p.relative_to(ws).as_posix()
                if any(inside == k or inside.startswith(k + "/") or fnmatch.fnmatch(inside.split("/")[0], k) for k in rule["skip"]):
                    continue
                if cfg.never_a_target(ws_rel) or not want.search(p.name):
                    continue
                if ws_rel not in ext[p.name]:
                    ext[p.name].append(ws_rel)
        return cls(root, ws, cfg, set(s.concepts), by_name, ext)

    def plan_file(self, rel: str) -> bool:
        if rel.startswith("..") or rel.startswith("/") or self.cfg.never_a_target(rel):
            return False
        return (self.root / rel).is_file()

    def ws_file(self, ws_rel: str) -> bool:
        if ws_rel.startswith("..") or ws_rel.startswith("/"):
            return False
        parts = ws_rel.split("/")
        if parts[0] not in self.cfg.external_roots or self.cfg.never_a_target(ws_rel):
            return False
        return (self.ws / ws_rel).is_file()

    def from_ws(self, ws_rel: str) -> str | None:
        """BHQ 폴더 기준 경로 → 링크가 가리킬 곳(BHQ 폴더 기준)."""
        ws_rel = posixpath.normpath(ws_rel)
        prefix = self.cfg.bundle_name + "/"
        if ws_rel.startswith(prefix):
            return ws_rel if self.plan_file(ws_rel[len(prefix):]) else None
        return ws_rel if self.ws_file(ws_rel) else None

    def resolve(self, token: str, rel: str) -> tuple[str | None, str]:
        """(BHQ 폴더 기준 대상 경로 또는 None, 까닭)"""
        if not CLEAN_PATH.match(token):
            return None, "틀·무늬"
        for alias in self.cfg.workspace_aliases:
            if token.startswith(alias):
                got = self.from_ws(token[len(alias):])
                return (got, "경로") if got else (None, "못 찾음")
        if token.startswith("/") or token.startswith("~"):
            return None, "못 찾음"
        bare = "/" not in token
        if bare and token in self.cfg.stop_names:
            return None, "흔한 이름"
        here = posixpath.dirname(rel)
        name = self.cfg.bundle_name
        # 1) 부르는 문서 자리에서 본 경로  2) 설정한 뿌리들(path_bases)에서 본 경로
        # 3) BHQ 폴더에서 본 경로  4) backend 뿌리에서 본 경로
        tries = [posixpath.join(name, here, token)]
        tries += [posixpath.join(base, token) for base in self.cfg.path_bases]
        tries += [token, posixpath.join("backend", token) if token.startswith("docs/") else ""]
        for t in tries:
            if not t:
                continue
            got = self.from_ws(t)
            if got:
                return got, "경로"
        # 이름 있는 폴더가 적혀 있는데 그 경로에 파일이 없으면, 다른 저장소의 경로일 수 있다.
        # 그래서 이름만으로 잇지 않고, 적힌 폴더가 대상 경로의 꼬리와 맞을 때만 잇는다.
        #   `adr/ADR-001.md`  → ui/adr/ADR-001.md   (꼬리가 맞는다)
        #   `docs/요청서.md`   → plan/요청서.md        (꼬리가 안 맞는다 — 잇지 않는다)
        # `../x.md` 처럼 점으로만 된 앞머리는 폴더가 없는 것으로 본다.
        folders = [p for p in posixpath.dirname(token).split("/") if p not in ("", ".", "..")]
        if folders:
            tail = "/" + "/".join(folders + [posixpath.basename(token)])
            cands = [c for c in self.concepts if ("/" + c).endswith(tail)]
            if len(cands) > 1:
                old = self.cfg.in_old_version(rel)
                cands = [c for c in cands if self.cfg.in_old_version(c) == old]
            if len(cands) == 1:
                return posixpath.join(name, cands[0]), "꼬리"
            if len(cands) > 1:
                return None, "후보 여럿"
            ext = [e for es in self.ext_by_name.values() for e in es if ("/" + e).endswith(tail)]
            if len(ext) == 1:
                return ext[0], "꼬리"
            return (None, "후보 여럿") if ext else (None, "못 찾음")
        base = posixpath.basename(token)
        if base in self.cfg.stop_names:
            return None, "흔한 이름"
        cands = self.by_name.get(base, [])
        if len(cands) > 1:
            old = self.cfg.in_old_version(rel)
            cands = [c for c in cands if self.cfg.in_old_version(c) == old]
        if len(cands) == 1:
            return posixpath.join(name, cands[0]), "이름"
        if len(cands) > 1:
            return None, "후보 여럿"
        ext = self.ext_by_name.get(base, [])
        if len(ext) == 1:
            return ext[0], "이름"
        if len(ext) > 1:
            return None, "후보 여럿"
        return None, "못 찾음"

    def where(self, target_ws: str) -> str:
        prefix = self.cfg.bundle_name + "/"
        if not target_ws.startswith(prefix):
            return OUTSIDE
        return IN_BUNDLE if target_ws[len(prefix):] in self.concepts else IN_PLAN

    def href(self, target_ws: str, rel: str) -> str:
        src_dir = posixpath.dirname(posixpath.join(self.cfg.bundle_name, rel))
        out = posixpath.relpath(target_ws, src_dir)
        return out.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


@dataclass
class LinkResult:
    rel: str
    old_text: str
    new_text: str | None
    counts: collections.Counter
    misses: collections.Counter


def fenced_lines(lines: list[str]) -> list[bool]:
    """줄마다 코드 울타리 안(울타리 줄 포함)인지. 여는 표시와 같은 글자로, 같거나 더 길게 닫아야 닫힌다."""
    out: list[bool] = []
    mark = ""
    for line in lines:
        m = FENCE.match(line)
        if not mark:
            if m:
                mark = m.group(1)
                out.append(True)
            else:
                out.append(False)
            continue
        out.append(True)
        rest = line.strip()
        if m and m.group(1)[0] == mark[0] and len(m.group(1)) >= len(mark) and rest == m.group(1):
            mark = ""
    return out


def link_one(lk: Linker, rel: str) -> LinkResult:
    text = read_checked(lk.root, rel)
    m = FRONTMATTER.match(text)
    if m is None:
        raise OkfError(f"머리말이 없다. label 을 먼저 돌린다: {rel}")
    head, body = text[: m.end()], text[m.end():]
    counts: collections.Counter = collections.Counter()
    misses: collections.Counter = collections.Counter()
    self_ws = posixpath.join(lk.cfg.bundle_name, rel)
    rules = [(i, r) for i, r in enumerate(lk.cfg.no_link) if r["file"] == rel]
    hits: collections.Counter = collections.Counter()
    lines = body.split("\n")
    out: list[str] = []
    for line, fenced in zip(lines, fenced_lines(lines)):
        if fenced:
            out.append(line)
            continue
        heading = line.startswith("#")
        blocked: set[str] = set()
        for i, r in rules:
            if r["line_has"] in line:
                hits[i] += 1
                blocked.update(r["tokens"])

        def undo(mm: re.Match, blocked: set[str] = blocked) -> str:
            if mm.group(1).strip("`") in blocked:
                counts["되돌림: 잇지 않는 곳"] += 1
                return mm.group(1)
            return mm.group(0)

        if blocked:
            line = LINKED.sub(undo, line)

        def sub(mm: re.Match, line: str = line, heading: bool = heading, blocked: set[str] = blocked) -> str:
            if mm.start() > 0 and line[mm.start() - 1] == "[" and line[mm.end(): mm.end() + 2] == "](":
                counts["이미 링크"] += 1
                return mm.group(0)
            token = mm.group(1).strip()
            anchor = mm.group(2) or ""
            if heading:
                counts["건너뜀: 제목 줄"] += 1
                return mm.group(0)
            if token + anchor in blocked:
                counts["건너뜀: 잇지 않는 곳"] += 1
                return mm.group(0)
            if any(c in UNSAFE_IN_PATH for c in anchor[1:]):
                counts["건너뜀: 틀·무늬"] += 1
                return mm.group(0)
            target, why = lk.resolve(token, rel)
            if target is None:
                counts[f"건너뜀: {why}"] += 1
                if why in ("못 찾음", "후보 여럿"):
                    misses[token] += 1
                return mm.group(0)
            if target == self_ws:
                counts["건너뜀: 자기 자신"] += 1
                return mm.group(0)
            if any(c in UNSAFE_IN_PATH for c in target):
                counts["건너뜀: 경로에 특수 글자"] += 1
                return mm.group(0)
            if posixpath.basename(target) != posixpath.basename(token):
                raise OkfError(f"글과 대상의 파일 이름이 다르다: {rel} 의 {token} → {target}")
            counts[f"이음: {lk.where(target)}"] += 1
            return f"[{mm.group(0)}]({lk.href(target, rel)}{anchor})"

        out.append(TOKEN.sub(sub, line))
    for i, r in rules:
        if hits[i] != 1:
            raise OkfError(f"no_link 규칙이 {hits[i]}줄에 맞았다(딱 한 줄이어야 한다): {rel} 의 {r['line_has']!r}")
    new_body = "\n".join(out)
    # 링크 감싸기를 벗기면 원래 글과 같아야 한다.
    if LINKED.sub(r"\1", new_body) != LINKED.sub(r"\1", body):
        raise OkfError(f"링크 말고 다른 글자가 달라졌다: {rel}")
    new_text = head + new_body
    return LinkResult(rel, text, None if new_text == text else new_text, counts, misses)


def cmd_link(root: Path, ws: Path, cfg: Config, apply: bool) -> int:
    s = scan(root, cfg)
    known = set(s.concepts)
    for r in cfg.no_link:
        if r["file"] not in known:
            raise OkfError(f"no_link 규칙의 문서가 묶음에 없다: {r['file']}")
    lk = Linker.build(root, ws, cfg, s)
    results = [link_one(lk, rel) for rel in s.concepts]
    total: collections.Counter = collections.Counter()
    misses: collections.Counter = collections.Counter()
    for r in results:
        total.update(r.counts)
        misses.update(r.misses)
    changed = [r for r in results if r.new_text is not None]
    print(f"묶음 문서 {len(results)}개 · 바뀌는 문서 {len(changed)}개")
    for k in sorted(total, key=lambda k: (not k.startswith("이음"), -total[k])):
        print(f"  {k:<28} {total[k]:>5}")
    if misses:
        print(f"못 이은 참조 {sum(misses.values())}건 · 서로 다른 글 {len(misses)}개(많은 순 15개):")
        for t, n in misses.most_common(15):
            print(f"  {n:>4}  {t}")
    if not apply:
        print("미리 보기다. 쓰려면 --apply")
        return 0
    write_all(root, [(r.rel, r.old_text, r.new_text) for r in changed])
    print(f"쓴 파일 {len(changed)}개")
    return 0


# ── 목차 ────────────────────────────────────────────────────────────────────

def read_frontmatter(root: Path, rel: str):
    text = (root / rel).read_text(encoding="utf-8")
    m = FRONTMATTER.match(text)
    return (parse_yaml(m.group(1)) if m else None), (text[m.end():] if m else text)


def link_target(name: str) -> str:
    return name.replace(" ", "%20")


def one_line(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_index(root: Path, cfg: Config, s: Scan, rel_dir: str, all_dirs: set[str]) -> str:
    here = [c for c in s.concepts if os.path.dirname(c) == rel_dir]
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for rel in here:
        fm, _ = read_frontmatter(root, rel)
        fm = fm or {}
        name = os.path.basename(rel)
        title = one_line(fm.get("title")) or name
        desc = one_line(fm.get("description"))
        entry = f"* [{title}]({link_target(name)})" + (f" - {desc}" if desc else "")
        groups[str(fm.get("type") or cfg.type_for(rel))].append(entry)
    out: list[str] = []
    if rel_dir == "":
        out += ["---", f'okf_version: "{cfg.okf_version}"', "---", ""]
    out += [GENERATED_MARK, ""]
    for t in sorted(groups):
        out += [f"# {t}", ""] + groups[t] + [""]
    subs = sorted(d for d in all_dirs if d and os.path.dirname(d) == rel_dir)
    if subs:
        out += ["# 하위 폴더", ""]
        for d in subs:
            n = sum(1 for c in s.concepts if c.startswith(d + "/"))
            out.append(f"* [{os.path.basename(d)}]({link_target(os.path.basename(d))}/index.md) - 문서 {n}개")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def concept_dirs(s: Scan) -> set[str]:
    dirs: set[str] = set()
    for rel in s.concepts:
        d = os.path.dirname(rel)
        dirs.add(d)
        while d:
            d = os.path.dirname(d)
            dirs.add(d)
    return dirs


def cmd_index(root: Path, cfg: Config, apply: bool) -> int:
    s = scan(root, cfg)
    dirs = concept_dirs(s)
    same = 0
    todo: list[tuple[str, Path, str]] = []
    # 먼저 전부 만들고 전부 검사한다. 하나라도 걸리면 아무것도 쓰지 않는다.
    for d in sorted(dirs):
        path = root / d / "index.md"
        text = build_index(root, cfg, s, d, dirs)
        if path.exists():
            old = path.read_text(encoding="utf-8")
            if not is_generated_index(old):
                raise OkfError(f"손으로 쓴 index.md 가 있다(덮어쓰지 않는다): {d or '.'}/index.md")
            if old == text:
                same += 1
                print(f"  같음     {d or '.'}/index.md")
                continue
        todo.append((d, path, text))
    for d, path, text in todo:
        print(f"  {'씀' if apply else '만들 것'}   {d or '.'}/index.md")
        if apply:
            write_atomic(path, text)
    n = len(todo)
    print(f"목차 {n}개 {'씀' if apply else '만들 것'} · 같음 {same}개")
    if not apply:
        print("미리 보기다. 쓰려면 --apply")
    return 0


# ── 검사 ────────────────────────────────────────────────────────────────────

def unfenced(body: str) -> str:
    """코드 울타리 안의 줄을 걷어 낸다. link 와 같은 판정(fenced_lines)을 쓴다."""
    lines = body.split("\n")
    return "\n".join(ln for ln, inside in zip(lines, fenced_lines(lines)) if not inside)


def body_links(body: str) -> list[str]:
    """코드 블록과 백틱 글자를 걷어 낸 본문에서 .md 링크 경로를 뽑는다(닻은 뗀다)."""
    body = unfenced(body)
    body = re.sub(r"`[^`\n]*`", "", body)
    return [t for t, _a in MD_LINK.findall(body) if not re.match(r"[a-z][a-z0-9+.-]*://", t)]


def cmd_check(root: Path, ws: Path, cfg: Config, strict: bool) -> int:
    s = scan(root, cfg)
    concepts = set(s.concepts)
    bad: list[tuple[str, str]] = []
    types: collections.Counter = collections.Counter()
    kinds: collections.Counter = collections.Counter()
    broken: list[tuple[str, str]] = []
    misnamed: list[tuple[str, str, str]] = []
    touched: set[str] = set()
    name = cfg.bundle_name
    named = re.compile(r"\[`([^`\n]+?\.md)(?:#[^`\n\s]*)?`\]\(([^)\s#]+)(?:#[^)\s]*)?\)")
    for rel in s.concepts:
        text = (root / rel).read_text(encoding="utf-8")
        m = FRONTMATTER.match(text)
        if m is None:
            bad.append((rel, "머리말 없음"))
            continue
        fm = parse_yaml(m.group(1))
        if fm is None:
            bad.append((rel, "머리말이 YAML 로 안 읽힘"))
            continue
        t = str(fm.get("type") or "").strip()
        if not t:
            bad.append((rel, "type 없음"))
            continue
        types[t] += 1
        want = cfg.type_for(rel)
        if t != want:
            bad.append((rel, f"type 이 규칙과 다름: {t} ≠ {want}"))
        here = posixpath.dirname(posixpath.join(name, rel))
        for said, went in named.findall(unfenced(text[m.end():])):
            if posixpath.basename(said.strip()) != posixpath.basename(went):
                misnamed.append((rel, said, went))
        for target in body_links(text[m.end():]):
            target = target.replace("%20", " ").replace("%28", "(").replace("%29", ")")
            if target.startswith("/"):
                tgt = posixpath.normpath(posixpath.join(name, target.lstrip("/")))
            else:
                tgt = posixpath.normpath(posixpath.join(here, target))
            inside = tgt.startswith(name + "/")
            real = (root / tgt[len(name) + 1:]) if inside else (ws / tgt)
            if tgt.startswith("..") or not real.is_file():
                kinds["깨진 링크"] += 1
                broken.append((rel, target))
                continue
            if inside and tgt[len(name) + 1:] in concepts:
                kinds[IN_BUNDLE] += 1
                touched.add(rel)
                touched.add(tgt[len(name) + 1:])
            elif inside:
                kinds[IN_PLAN] += 1
            else:
                kinds[OUTSIDE] += 1
    for rel in s.reserved:
        text = (root / rel).read_text(encoding="utf-8")
        m = FRONTMATTER.match(text)
        fname = os.path.basename(rel)
        if fname == "index.md" and m is not None:
            fm = parse_yaml(m.group(1))
            if rel != "index.md":
                bad.append((rel, "맨 위가 아닌 index.md 에 머리말"))
            elif fm is None or set(fm) != {"okf_version"}:
                bad.append((rel, "맨 위 index.md 머리말은 okf_version 만"))
        if fname == "log.md":
            for h in re.findall(r"^## (.+)$", text, re.M):
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", h.strip()):
                    bad.append((rel, f"log.md 날짜 제목이 YYYY-MM-DD 가 아님: {h}"))
    print(f"기준 규격 OKF {cfg.okf_version} @ {cfg.spec_commit[:12]}")
    print(f"묶음 문서 {len(s.concepts)}개 · 예약 파일 {len(s.reserved)}개 · 제외 {len(s.skipped)}개")
    print("종류:", dict(types.most_common()))
    print("본문 링크:", {k: kinds.get(k, 0) for k in (IN_BUNDLE, IN_PLAN, OUTSIDE, "깨진 링크")})
    orphans = sorted(concepts - touched)
    print(f"묶음 안 링크로 이어진 문서 {len(touched)} / {len(concepts)} · 외톨이 {len(orphans)}개")
    for o in orphans:
        print(f"  외톨이: {o}")
    for rel, target in broken[:20]:
        print(f"  깨진 링크(규격상 위반 아님): {rel} → {target}")
    print(f"글과 대상의 파일 이름이 다른 링크 {len(misnamed)}개")
    for rel, said, went in misnamed[:20]:
        print(f"  이름 다름: {rel} 의 {said} → {went}")
    if s.skipped:
        print("제외한 md:")
        by_top = collections.Counter(p.split("/")[0] for p in s.skipped)
        for k, v in sorted(by_top.items()):
            print(f"  {k}/ {v}개")
    if bad:
        print(f"위반 {len(bad)}건")
        for rel, why in bad:
            print(f"  {rel}: {why}")
        return 1
    if strict and (broken or misnamed):
        print(f"규격 위반 0건. 다만 --strict: 깨진 링크 {len(broken)}개 · 이름 다른 링크 {len(misnamed)}개")
        return 1
    print("위반 0건 — 통과")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="plan/ 문서를 OKF 묶음으로 맞춘다")
    ap.add_argument("command", choices=["label", "link", "index", "check"])
    ap.add_argument("--apply", action="store_true", help="실제로 쓴다(label·link·index)")
    ap.add_argument("--strict", action="store_true", help="check: 깨진 링크·이름 다른 링크도 실패로 친다")
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="묶음 뿌리(기본: plan/)")
    ap.add_argument("--workspace", type=Path, default=None, help="plan 밖 문서를 찾을 BHQ 폴더(기본: 묶음 뿌리의 부모)")
    ap.add_argument("--config", type=Path, default=HERE / "okf.toml")
    args = ap.parse_args(argv)
    cfg = Config.load(args.config)
    root = args.root.resolve()
    # 묶음 자리가 `backend/docs` 처럼 두 단이면 BHQ 폴더는 묶음 뿌리에서 두 단 위다.
    ws = (args.workspace or root.parents[len(cfg.bundle_name.split("/")) - 1]).resolve()
    try:
        if args.command == "label":
            return cmd_label(root, cfg, args.apply)
        if args.command == "link":
            return cmd_link(root, ws, cfg, args.apply)
        if args.command == "index":
            return cmd_index(root, cfg, args.apply)
        return cmd_check(root, ws, cfg, args.strict)
    except OkfError as e:
        print(f"멈춤: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
