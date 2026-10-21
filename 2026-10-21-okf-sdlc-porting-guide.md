---
type: Howto
title: OKF 문서 정리 이식 안내서 (BHQ 방식) — SDLC 문서 사슬에 분류·목차·링크 얹기
description: BHQ 에서 쓰는 SDLC 문서 사슬(의도 → 스펙 → 계획 → 태스크 계획 → 실행서)에 OKF(Open Knowledge Format) v0.2 의 type·목차·링크를 얹고, 밀리지 않게 기계로 지키는 방법. 도구 okf.py · 설정 okf.toml · 밀림 막기 guard.sh · 이식 순서 · 함정 · 점검표
date: 2026-10-21
tags: [process, sdlc, okf, documentation, ssot, claude-code, template, bhq, porting]
Archives: false
URL: "https://github.com/GoogleCloudPlatform/open-knowledge-format"
---

# OKF 문서 정리 이식 안내서 (BHQ 방식)

> **이 문서 쓰는 법**
> - **사람:** §0~§2 를 읽으면 전체 그림이 잡힌다. §6 이 설치 순서, §9 가 점검표다.
> - **Claude Code 에게:** 새 저장소에 이 파일을 복사한 뒤 이렇게 말한다.
>   "이 문서 §6 의 1단계부터 깔아 줘. §5 의 종류 규칙은 먼저 나한테 물어봐."
>   단계 하나를 끝내고 관문을 통과하면 다음 단계로 간다.
>
> **짝 문서:** [`2026-10-06-ai-native-sdlc-porting-guide.md`](2026-10-06-ai-native-sdlc-porting-guide.md)(SDLC 이식 안내서).
> SDLC 안내서는 **무엇을 언제 쓰나**를 다룬다. 이 문서는 **쓴 것을 어떻게 꽂아 두나**를 다룬다. SDLC 를 먼저 깔고 이 문서를 얹는다.
>
> 셸·TOML 코드는 2026-10-21 에 연습용 저장소와 BHQ 두 저장소에서 꺼내 돌려 본 것만 실었다. 예외인 CI 파일은 §7.3 에 따로 적었다.

---

## 0. 30초 요약

**비유: 도서관.** SDLC 는 책을 쓰는 순서다. OKF 는 다 쓴 책을 도서관에 꽂는 규칙이다.

| 도서관 | OKF | BHQ 에서 |
|---|---|---|
| 책등의 분류 스티커 | 머리말의 `type` 한 줄 | `type: Task Plan` |
| 서가마다 붙은 목록 카드 | 폴더마다 자동 목차 `index.md` | `plan/index.md`, `docs/plans/index.md` |
| "이 책은 저 책 3장을 보라"는 화살표 | 문서 사이 보통 마크다운 링크 | `` [`plan.md`](../plan.md) `` |
| 사서의 순회 점검 | 기계 검사 | `okf.py check --strict` + `guard.sh` |

**네 규칙**
1. **모든 문서에 `type` 한 줄을 단다.** OKF 가 요구하는 것은 이것 하나다.
2. **목차는 손으로 쓰지 않는다.** 도구가 머리말을 읽어 `index.md` 를 만든다.
3. **문서 이름을 적었으면 링크로 감싼다.** 글자는 그대로 두고 감싸기만 한다.
4. **밀림은 기계가 막는다.** 사람이 순서를 기억하게 두면 반드시 밀린다(§7 실측: 3주에 계획서 27개).

**한 문서의 한 바퀴**

```
SDLC 순서대로 문서를 쓴다 (계획서 · 실행서 · 결정 기록 …)
      ↓
label → link → index      (도구가 type · 링크 · 목차를 채운다)
      ↓
check --strict            (규격 위반 0)
      ↓
git commit                ← pre-commit 의 guard.sh 가 밀린 것이 있으면 막는다
```

---

## 1. SDLC 와 OKF 는 어떻게 맞물리나

### 1.1 SDLC 문서마다 종류가 하나씩

SDLC 사슬의 각 칸이 OKF `type` 하나가 된다. BHQ 가 실제로 쓰는 값이다.

| SDLC 단계 | 문서 | `type` | 사는 곳 |
|---|---|---|---|
| 의도 | `intent.md`, `intents/*` | `Intent` | plan |
| 정본 색인 | `spec.md` | `Spec` | plan |
| 설계 | `*-design.md` | `Design` | plan |
| 결정 기록 | `ui/adr/ADR-*.md` | `ADR` | plan |
| 마스터 계획 | `plan.md`, `*-plan.md` | `Plan` | plan |
| 에이전트 편성 | `agent.md` | `Agent Guide` | plan |
| 근거 조사 | `research/*` | `Research` | plan |
| 다른 팀과 주고받은 글 | `*request*`, `*reply*`, `*notice*` | `Correspondence` | plan |
| 태스크 계획 | `docs/plans/T<n>-<slug>.md` | `Task Plan` | 코드 저장소 |
| 실행서(배포·운영 절차) | `docs/runbooks/*` | `Runbook` | 코드 저장소 |
| 앱 사이 계약 | `docs/account/*` | `Spec` | 코드 저장소 |

`type` 값은 OKF 가 정해 주지 않는다. 규격은 모르는 값을 거절하지 말라고만 한다(SPEC §11). 그래서 **프로젝트가 종류 목록을 정하고 설정 파일(`okf.toml`)에 적는다.** BHQ 는 plan 15종, 코드 저장소 4종을 쓴다.

### 1.2 `spec.md` 색인과 `index.md` 목차는 다른 물건이다

| | `spec.md` 1절 (SDLC) | `index.md` (OKF) |
|---|---|---|
| 답하는 물음 | 어느 문서가 **정본**인가 | 어떤 문서가 **있나** |
| 누가 쓰나 | 사람이 정한다 | 도구가 머리말에서 만든다 |
| 검사 | `scripts/check_index.sh` (색인이 가리키는 파일이 있나) | `okf.py index` (목차가 머리말과 같나) |

둘 다 둔다. 목차를 색인 대신 쓰지 않는다. 목차에는 낡은 판·초안도 다 나오기 때문이다.

### 1.3 `status` 낱말이 부딪친다

- BHQ SDLC: `draft → approved | rejected | superseded`. 승인의 정본은 파일의 `status` + 커밋 트레일러 `Approved-by:` 다.
- OKF: `draft | stable | deprecated`. `status` 가 없으면 `stable` 로 읽는다(SPEC §5.4).

BHQ 는 SDLC 값을 그대로 둔다. `approved` 는 OKF 값이 아니어서 OKF 를 읽는 쪽은 이해하지 못한다. 그래도 승인 기록을 두 곳에 나눠 적는 것보다 낫다고 봤다.
새 프로젝트에서 OKF 를 읽는 도구까지 쓸 생각이면 다른 길도 있다. homeagent 의 ADR-006 은 `status` 를 필수로 두고 승인 정본은 승인 줄·트레일러에 그대로 남기자고 제안했다(2026-09-29 Proposed, 승인 대기. Resources).

**에이전트는 승인을 뜻하는 값을 스스로 적지 않는다.** OKF 의 `verified` 칸도 마찬가지다. 승인은 사람이 한다(SDLC 안내서 §0 세 기둥 2).

---

## 2. OKF 요점 (v0.2, 2026-10-21 확인)

- Google Cloud 가 2026 년에 공개했다. BHQ 리서치는 간접 출처(검색 요약·블로그)로 6월 발표라고 적었고, GitHub 저장소 생성일은 2026-08-11 이다. 지금 판은 **v0.2** 다. 정본은 `GoogleCloudPlatform/open-knowledge-format` 의 `SPEC.md` 이고, 라이선스는 Apache-2.0 이다.
- **판 번호 말고 커밋으로 고정한다.** 같은 0.2 아래에서 2026-08-21 에 시각 표기 규칙이 바뀌었다. BHQ 는 `0b87c52c6ef9`(2026-08-21)에 고정한다. 2026-10-21 에 GitHub API 로 다시 보니 `SPEC.md` 의 마지막 커밋이 여전히 이것이었다.
- 모양은 **폴더 + 마크다운 + YAML 머리말**이다. 한 폴더 나무를 "묶음(bundle)"이라 부른다.
- **적합 조건은 셋뿐이다(SPEC §11).**
  1. 예약 파일이 아닌 `.md` 는 모두 읽히는 YAML 머리말을 가진다.
  2. 머리말마다 비지 않은 `type` 이 있다.
  3. 예약 파일 `index.md`·`log.md` 는 §8·§9 모양을 따른다.
- 규격이 **거절하지 말라고 하는 것**도 있다. 모르는 `type`, 모르는 머리말 칸, 깨진 링크, 없는 `index.md` 가 그렇다. 그래서 BHQ 는 깨진 링크를 `--strict` 일 때만 실패로 친다.
- 링크는 **보통 마크다운 링크**이고 종류가 없다. "부모·참조·의존" 같은 뜻은 앞뒤 문장이 나른다(SPEC §6.1). 규격은 `/` 로 시작하는 묶음 기준 경로를 권한다. BHQ 는 상대 경로를 쓴다(§8 함정 9).
- 신뢰 칸은 고르는 것이다. `sources`·`generated`·`verified`·`status`·`stale_after` 가 있다.
- **규격에 없는 것:** 묶음에서 폴더를 빼는 장치, 권한 개념, 종류 있는 관계(이슈 #16·#30 에서 논의 중). 빼는 범위는 설정으로 정한다. 그래서 "통과"는 **설정한 범위 안에서** 통과라는 뜻이다.

---

## 3. BHQ 의 실제 배치

```
BHQ/
├── plan/                          ← 기획 저장소 = 묶음 1 (뿌리 plan/)
│   ├── index.md                   자동 목차 (okf:generated 표시)
│   ├── intent.md  spec.md  plan.md  agent.md  *-design.md …
│   ├── research/index.md  ui/index.md  ui/adr/index.md …
│   └── scripts/okf/
│       ├── okf.py                 도구 (한 벌만 둔다)
│       └── okf.toml               plan 묶음 설정
└── backend/                       ← 코드 저장소
    └── docs/                      ← 묶음 2 (뿌리 backend/docs/)
        ├── okf.toml               backend 묶음 설정 (도구는 없음)
        ├── index.md  plans/index.md  runbooks/index.md  account/index.md
        └── plans/T<n>-<slug>.md …
```

| 묶음 | 뿌리 | 문서 수(10-21) | 종류 | 빼는 폴더 |
|---|---|---|---|---|
| plan | `plan/` | 71 | 15종 | `ui/html` · `scripts` · `schema/build` · `templates` · `bhq-fe-handoff-*` |
| backend/docs | `backend/docs/` | 141 | `Task Plan` · `Runbook` · `Spec` · `Readme` | 없음 |

**돌리는 법**

```sh
# plan 폴더에서 (plan 에는 가상환경이 없다. 이 맥의 plan 폴더 python3 는 pyenv 3.11 이고 PyYAML 이 있다)
python3 scripts/okf/okf.py check --strict

# backend 폴더에서 (도구는 형제 plan 저장소의 것을 쓴다)
.venv/bin/python ../plan/scripts/okf/okf.py --root docs --config docs/okf.toml check --strict
```

backend 에서는 맨 `python3` 를 쓰지 않는다. backend 폴더의 `.python-version` 이 PyYAML 없는 파이썬을 고른다(§8 함정 6).

---

## 4. 도구 `okf.py`

원본: BHQ plan 저장소 `scripts/okf/okf.py`(822줄, 2026-10-21 기준).
필요한 것: Python 3.11 이상(`tomllib`) + PyYAML. 다른 의존성은 없다.

### 4.1 네 명령

| 명령 | 하는 일 | 바꾸는 것 |
|---|---|---|
| `label` | 머리말에 `type` 을 단다. 머리말이 없으면 만든다. 읽히지 않는 줄은 따옴표로 고친다 | 머리말만 |
| `link` | 본문의 `` `X.md` `` 를 `` [`X.md`](상대경로) `` 로 감싼다 | 링크로 감싸기만 |
| `index` | 폴더마다 `index.md` 목차를 만든다 | `okf:generated` 표시가 있는 목차만 |
| `check` | SPEC §11 세 조건을 보고 링크를 센다. `--strict` 면 깨진 링크·이름 다른 링크도 실패 | 안 바꾼다 |

`label`·`link`·`index` 는 **기본이 미리 보기**다. `--apply` 를 줘야 쓴다.

### 4.2 스스로 멈추는 장치 (닫힌 쪽으로 멈춤)

도구는 애매하면 쓰지 않고 멈춘다. 멈춤은 고장이 아니라 사람에게 묻는 신호다.

| 멈춤 메시지 | 뜻 | 할 일 |
|---|---|---|
| `종류 규칙이 없는 문서: X — okf.toml 의 rules 에 더한다` | 새 폴더나 새 이름 꼴이 생겼다 | `rules` 에 한 줄 더한다 |
| `머리말이 없다. label 을 먼저 돌린다` | 순서를 건너뛰었다 | `label --apply` 부터 |
| `본문이 달라졌다` · `링크 말고 다른 글자가 달라졌다` | 도구가 본문을 건드릴 뻔했다 | 쓰지 않았다. 버그로 보고 |
| `읽은 뒤에 바뀐 문서가 있다(아무것도 쓰지 않았다)` | 다른 세션이 동시에 고쳤다 | 다시 돌린다 |
| `손으로 쓴 index.md 가 있다` | 사람이 쓴 목차를 덮어쓸 뻔했다 | 표시를 달지, 옮길지 정한다 |
| `BOM 또는 CRLF 가 있다` | 줄 끝·인코딩이 다르다 | 파일을 LF·UTF-8 로 |
| `no_link 규칙이 N줄에 맞았다` | 예외 규칙이 애매하다 | `line_has` 를 더 길게 |

### 4.3 BHQ 냄새가 남은 곳 (다른 프로젝트에서도 그대로 써도 된다)

- `bundle_name` 의 기본값이 `"plan"` 이다. 설정에 적으면 덮인다.
- 경로 찾기 넷째 단계가 `docs/…` 로 시작하는 참조를 `backend/docs/…` 에서 한 번 더 찾는다(`okf.py:408`). `backend` 폴더가 없으면 아무 일도 안 한다.
- PyYAML 이 없을 때의 안내문이 backend 를 예로 든다.

연습용 저장소(`docs/` 하나, BHQ 와 무관한 이름)에서 고치지 않고 돌려 네 명령이 모두 통과했다(§10).

---

## 5. 설정 `okf.toml`

### 5.1 칸 설명

| 칸 | 필수 | 뜻 |
|---|---|---|
| `okf_version` · `spec_commit` | 예 | 기준 규격. 커밋까지 적는다 |
| `rules` | 예 | `{ pattern, type }` 목록. 위에서부터 처음 맞는 것을 쓴다. `pattern` 은 묶음 뿌리 기준 fnmatch 이고 `*` 는 `/` 도 건넌다 |
| `bundle_name` | 사실상 예 | 작업 폴더에서 본 묶음 자리(`plan`, `docs`, `backend/docs`) |
| `spec_commit_date` | | 기준 커밋의 날짜. 사람이 읽으라고 적는다(도구는 안 읽는다) |
| `exclude_dirs` | | 묶음에서 빼는 폴더. 묶음 뿌리 기준 경로이고 그 아래 전부가 빠진다(사본·생성물·틀) |
| `exclude_dir_globs` | | 묶음에서 빼는 폴더 무늬. **맨 위 폴더 이름만** 맞춰 본다(`bhq-fe-handoff-*`) |
| `stop_names` | | 폴더 없이 이름만 적혔을 때 잇지 않는 흔한 이름(`README.md`·`CLAUDE.md` …) |
| `no_link` | | 글자는 파일 이름과 같지만 뜻은 그 파일이 아닌 줄. `{ file, line_has, tokens }` |
| `external_roots` | | 묶음 밖이지만 이어 줄 형제 폴더(`backend`, `request` …) |
| `external_names` | | 이름만 적힌 참조를 찾아볼 묶음 밖 폴더. `{ dir, match, skip }` — `match` 는 파일 이름 정규식, `skip` 은 그 폴더 안에서 뺄 하위 폴더 |
| `external_name_dirs` | | 옛 열쇠. `external_names` 에 `match = '^T\d'`(이름이 T+숫자로 시작) 를 준 것과 같다. TOML 에서 정규식은 작은따옴표로 쓴다. 큰따옴표 안의 `\d` 는 파싱 오류다 |
| `workspace_aliases` | | 본문에 절대 경로로 적힌 참조의 앞머리(`/Users/<나>/Desktop/BHQ/`). 떼어 내고 작업 폴더 기준으로 읽는다 |
| `path_bases` | | 경로를 풀 때 기준으로 삼을 뿌리들 |
| `old_version_dirs` | | 옛 판 폴더. 같은 이름이면 옛 판은 옛 판끼리 잇는다 |
| `never_target_globs` | | 링크 대상이 될 수 없는 폴더 무늬. 경로의 **모든 마디**를 맞춰 본다(인계 사본 등) |

### 5.2 최소 템플릿 (한 저장소, `docs/` 묶음)

2026-10-21 연습용 저장소에서 이 파일 그대로 `label`·`link`·`index`·`check --strict` 가 통과했다.

#### `docs/okf.toml`

```toml
okf_version = "0.2"
spec_commit = "0b87c52c6ef999286c745e19998fdfcd03d5dbee"
bundle_name = "docs"
exclude_dirs = []
stop_names = ["index.md", "log.md", "README.md", "CLAUDE.md", "AGENTS.md", "SKILL.md"]
rules = [
  { pattern = "intent.md",   type = "Intent" },
  { pattern = "spec.md",     type = "Spec" },
  { pattern = "plan.md",     type = "Plan" },
  { pattern = "adr/*",       type = "ADR" },
  { pattern = "plans/*",     type = "Task Plan" },
]
```

두 저장소 배치(SDLC 안내서 §2.A)라면 BHQ 의 두 설정 파일을 출발점으로 쓴다(Resources).

### 5.3 종류 규칙을 정하는 법

- **폴더 규칙을 먼저 쓴다**(`plans/*`, `adr/*`). 이름 꼴 규칙(`*-design.md`)은 그다음이다. 폴더가 더 오래 버틴다.
- **맨 끝에 "나머지 전부" 규칙을 두지 않는다.** 모르는 문서가 생기면 멈춰야 사람이 종류를 정한다. BHQ 가 3주 뒤에 멈춤 두 번(새 이름 꼴, 새 폴더 `docs/account/`)으로 밀림을 알아챈 것도 이 덕이다.
- 새 문서 틀(`templates/task-plan.md` 등)의 머리말에 **`type` 을 미리 넣어 둔다.** 그러면 처음부터 라벨이 붙은 채로 태어난다. 틀 폴더 자체는 묶음에서 뺀다(틀은 개념 문서가 아니다).

---

## 6. 설치 순서

단계마다 관문이 있다. 관문을 통과해야 다음 단계로 간다.
명령은 한 저장소·`docs/` 묶음 기준이다. `PY` 는 PyYAML 이 있는 파이썬이다.

```sh
okf() { "$PY" scripts/okf/okf.py --root docs --config docs/okf.toml "$@"; }
```

zsh 에서 `OKF="$PY scripts/okf/okf.py …"` 처럼 변수에 담으면 쪼개지지 않아 실패한다. 함수나 배열로 쓴다(§8 함정 10).

### 1단계: 도구와 설정

1. PyYAML 이 있는 파이썬 3.11 이상을 정한다. 보통은 저장소 가상환경이다. 없으면 `python3 -m venv .venv`(3.11 이상인 python3 로) 로 만들고, `.venv/bin/python -m pip install pyyaml` 한 뒤 `PY=.venv/bin/python` 으로 둔다.
2. `okf.py` 를 `scripts/okf/` 에 복사한다.
3. `docs/okf.toml` 을 §5.2 템플릿으로 만들고 종류 규칙을 채운다. **종류 목록은 사람이 정한다.**
4. 묶음에서 뺄 폴더를 정한다. §8 함정 3 의 "건드리면 안 되는 md" 를 먼저 찾는다.

**관문:** `okf label`(미리 보기)이 멈추지 않고 끝까지 돈다. 그러면 종류 규칙이 모든 문서를 덮는다는 뜻이다. `check` 로는 이 관문을 못 잰다. 라벨 전 문서는 `check` 가 "머리말 없음"으로 먼저 세어 버려 규칙 빠짐을 보지 못한다.

### 2단계: 라벨

```sh
okf label            # 미리 보기: 문서마다 "type 추가 / 머리말 새로 만듦 / 같음"
okf label --apply
```

**관문:** 다시 `okf label` 을 돌리면 요약이 `{'같음': N}` 하나뿐이다.

### 3단계: 링크 (사람이 문장을 읽는 단계)

```sh
okf link             # 미리 보기: 이을 수 · 못 이은 참조 상위 15개
```

1. **사본에서 먼저 돌린다.** 묶음을 임시 폴더에 복사하고 `--root <사본> --workspace <작업 폴더>` 로 `--apply` 한 뒤 원본과 `diff -r` 한다.
2. **문장을 읽는 독립 검증을 붙인다.** 새 링크마다 앞뒤 문장을 읽고 "문장이 말하는 문서가 링크 대상과 같은가"를 판정한다. 링크를 만든 세션이 아니라 다른 세션(검증 에이전트)이 한다.
3. 틀린 것은 `no_link` 에 적는다. 이미 이어진 것도 도구가 되돌린다.
4. 원본에 `--apply` 하고, 결과가 사본과 같은지 `diff -r` 로 본다.

**관문:** 독립 검증 "잘못 0". 기계 검사(모양·대상 존재)만으로는 이 관문을 못 넘는다. 이유는 §8 함정 1 에 있다.

### 4단계: 목차

```sh
okf index --apply
```

**관문:** 다시 `okf index` 를 돌리면 `목차 0개 만들 것` 이 나온다.

### 5단계: 검사

```sh
okf check --strict
```

**관문:** 마지막 줄이 `위반 0건 — 통과` 다. `외톨이`(아무 링크도 안 받는 문서)는 위반이 아니다. 목록만 보고 넘어간다.

### 6단계: 밀림 막기 연결

1. §7.2 의 `guard.sh` 를 `scripts/okf/` 에 두고 **실행 권한을 준다**(`chmod +x scripts/okf/guard.sh`). 권한이 없으면 hook 이 `Permission denied` 로 **정상 문서까지 모든 커밋을** 막는다.
2. §7.3 의 pre-commit(또는 pre-push)과 CI 에 건다. pre-commit 은 `OKF_PYTHON` 을 정한다. 안 정하면 guard 가 맨 `python3` 를 쓰고, 거기에 PyYAML 이 없으면 역시 모든 커밋이 막힌다.

**관문(셋 다):**
- 정상 문서 하나를 고쳐 커밋하면 `OKF guard OK` 가 나오고 커밋된다.
- 일부러 머리말 없는 문서를 만들어 커밋하면 `type 이 없는 문서가 있다` 또는 `머리말이 없다` 로 막힌다. 다른 메시지(`Permission denied`, `PyYAML 이 없거나`)로 막히면 통과가 아니다.
- 확인한 뒤 그 문서를 지운다.

### 7단계: 에이전트에게 알리기

`CLAUDE.md` 의 Commands 에 한 줄을 더한다.

```markdown
- 문서 정리(OKF): 문서를 만들거나 고친 뒤 `label --apply` → `link --apply` → `git diff` 로 새 링크의 앞뒤 문장을 읽는다 → `index --apply` → `check --strict`. 뜻이 다른 링크는 `docs/okf.toml` 의 `no_link` 에. 새 폴더면 rules 에 한 줄
```

**관문:** 새 세션에게 "계획서 하나 써 줘"라고 시켰을 때, 커밋 전에 네 명령을 돌리거나 guard 가 막는다.

---

## 7. 밀림 막기

### 7.1 BHQ 에서 실제로 밀렸다 (2026-10-21 실측)

09-29~30 에 두 묶음을 다 맞췄다. 그 뒤 3주 동안 이렇게 밀렸다.

| 잰 것 | plan | backend/docs |
|---|---|---|
| `type` 없는 문서 | 0 | **27** (T48a 부터 T61 까지 새 계획서 거의 전부) |
| `check` | 새 이름 꼴 계획서 2개에서 멈춤 | 새 폴더 `docs/account/` 에서 멈춤 |
| 링크로 안 감싼 참조 | 96 | 189 |
| 낡은 목차 | 0 | 3 |

**왜 밀렸나**
1. 네 명령을 **사람(과 에이전트)이 기억해야** 했다.
2. 도구가 plan 저장소에만 있어서 **backend CI 가 돌릴 수 없었다.** 그래서 아무도 경고하지 않았다.
3. 같은 시기에 SDLC 쪽(계획 → 승인 → 구현 → 검증)은 하루도 안 밀렸다. 그쪽은 훅·CI·PR 템플릿이 **막았기** 때문이다.

교훈은 SDLC 안내서 §0 세 기둥 3 과 같다. **권고는 밀리고, 강제는 안 밀린다.**

### 7.2 `guard.sh`: 정리할 것이 남았으면 실패

`label`·`link`·`index` 는 미리 보기가 끝까지 돌면 바뀔 것이 있어도 exit 0 을 낸다. 멈출 때만 `멈춤: …` 을 찍고 exit 2 다(`okf.py:816-818`). 그래서 guard 는 exit 코드로 멈춤을 잡고, 출력을 읽어 "바뀔 것이 0" 인지 본다.

#### `scripts/okf/guard.sh`

```bash
#!/usr/bin/env bash
# OKF 밀림 막기: 정리할 것이 남아 있으면 exit 1. pre-commit · pre-push · CI 가 같은 스크립트를 쓴다.
# usage: scripts/okf/guard.sh [묶음 뿌리=docs] [설정=<뿌리>/okf.toml]
set -uo pipefail
ROOT="${1:-docs}"; CONF="${2:-$ROOT/okf.toml}"
PY="${OKF_PYTHON:-python3}"
"$PY" -c 'import tomllib, yaml' 2>/dev/null \
  || { echo "OKF: $PY 에 PyYAML 이 없거나 3.11 미만이다 → OKF_PYTHON 에 PyYAML 있는 파이썬을 준다"; exit 1; }
OKF=("$PY" "$(dirname "$0")/okf.py" --root "$ROOT" --config "$CONF")
fail=0
out=$("${OKF[@]}" label 2>&1) || { echo "$out" | tail -3; exit 1; }
echo "$out" | grep -qE "^요약: \{'같음': [0-9]+\}$" \
  || { echo "OKF: type 이 없는 문서가 있다 → label --apply"; echo "$out" | grep -vE '^ +같음' | head -8; fail=1; }
out=$("${OKF[@]}" link 2>&1) || { echo "$out" | tail -3; exit 1; }
echo "$out" | grep -q '바뀌는 문서 0개' \
  || { echo "OKF: 링크로 안 감싼 참조가 있다 → link --apply 뒤 git diff 로 새 링크의 문장을 읽는다"; echo "$out" | head -4; fail=1; }
out=$("${OKF[@]}" index 2>&1) || { echo "$out" | tail -3; exit 1; }
echo "$out" | grep -q '목차 0개 만들 것' \
  || { echo "OKF: 목차가 낡았다 → index --apply"; echo "$out" | grep -v '같음' | head -6; fail=1; }
"${OKF[@]}" check --strict >/dev/null 2>&1 \
  || { echo "OKF: check --strict 실패"; "${OKF[@]}" check --strict 2>&1 | tail -5; fail=1; }
[ "$fail" = 0 ] && echo "OKF guard OK"
exit "$fail"
```

**2026-10-21 에 돌려 본 결과**

| 상황 | 결과 |
|---|---|
| 연습용 저장소, 정리 끝난 상태 | `OKF guard OK`, exit 0 |
| 머리말 없는 새 계획서 추가 | `type 이 없는 문서가 있다 → label --apply`, exit 1 |
| 규칙 없는 새 폴더 `runbooks/` 추가 | `멈춤: 종류 규칙이 없는 문서: runbooks/deploy.md — okf.toml 의 rules 에 더한다`, exit 1 |
| pre-commit 연결, guard 에 실행 권한 없음 | `Permission denied` 로 **정상 커밋도** 막힘 → 6단계 `chmod +x` |
| pre-commit 연결, 정상 문서 고침 커밋 | `OKF guard OK`, 커밋됨 |
| pre-commit 연결, 머리말 없는 문서 커밋 | `머리말이 없다. label 을 먼저 돌린다`, 커밋 막힘 |
| `OKF_PYTHON` 이 PyYAML 없는 파이썬 | `PyYAML 이 없거나 3.11 미만이다`, exit 1 |
| 파이썬 3.11.13 · 3.14.7 (PyYAML 있음) | 둘 다 `OKF guard OK` |
| 파이썬 3.10 이하 | 시험 못 함(이 맥에 없음). `import tomllib` 이 실패해 위 "3.11 미만" 메시지로 막히는 구조다 |
| BHQ plan (따라잡기 직후) | `OKF guard OK` |
| BHQ plan (**17분 뒤**) | `링크로 안 감싼 참조가 있다`, exit 1 — 다른 세션이 `plan.md` 68행을 새로 쓰면서 링크를 보통 글자로 되돌렸다(§8 함정 13). guard 가 없었다면 아무도 몰랐다 |
| BHQ backend/docs (따라잡기 가지) | `OKF guard OK` |

**한계 둘**
- guard 는 스테이징한 내용이 아니라 **작업 트리**를 본다. 커밋에 안 넣은 고침이 있으면 결과가 다를 수 있다. CI 에서 한 번 더 돌리는 이유다.
- guard 가 "링크로 안 감싼 참조"로 막을 때 `link --apply` 만 치면 문장 검증 없이 링크가 생긴다. 그러면 함정 1(같은 글자, 다른 뜻)이 커밋마다 되살아난다. `link` 미리 보기는 개수만 찍고 문서·줄은 안 보여 준다. 그래서 사본에 적용해 `diff -r` 하거나(3단계 1항), 적용한 뒤 `git diff` 로 새 링크의 앞뒤 문장을 읽는다.

### 7.3 거는 자리

#### `.githooks/pre-commit`

```bash
#!/usr/bin/env bash
# PyYAML 이 있는 파이썬을 준다. 못 찾으면 guard 가 정상 문서까지 모든 커밋을 막는다.
export OKF_PYTHON="${OKF_PYTHON:-.venv/bin/python}"
exec scripts/okf/guard.sh docs
```

```sh
chmod +x .githooks/pre-commit scripts/okf/guard.sh && git config core.hooksPath .githooks
```

가상환경 자리가 `.venv` 가 아니면 셋째 줄의 기본값을 바꾼다.

이미 `.githooks/pre-push` 를 쓰는 저장소(SDLC 안내서 §6.11)라면 거기에 `OKF_PYTHON="${OKF_PYTHON:-.venv/bin/python}" scripts/okf/guard.sh docs || exit 1` 한 줄을 더해도 된다. `OKF_PYTHON` 을 빼면 PyYAML 없는 `python3` 환경에서 push 가 전부 막힌다.

#### `.github/workflows/ci.yml` (일부)

> 이 조각은 돌려 보지 않았다. 안에서 부르는 `guard.sh` 만 위 표대로 돌려 봤다. SDLC 안내서 §6.12 의 결정론 잡에 단계로 붙인다.

```yaml
      - name: OKF guard
        run: |
          python -m pip install pyyaml
          OKF_PYTHON=python scripts/okf/guard.sh docs
```

### 7.4 저장소가 둘이면

CI 는 자기 저장소만 본다. 도구가 다른 저장소에 있으면 CI 가 못 돌린다(BHQ 가 밀린 이유 2).

| 안 | 장점 | 단점 |
|---|---|---|
| **도구를 각 저장소에 복사한다** | CI 가 바로 돌린다 | 사본이 어긋날 수 있다 → 사본 대조 한 줄(`sha256sum` 비교)을 guard 앞에 둔다 |
| CI 에서 기획 저장소도 받아 온다 | 도구 한 벌 | 비공개 저장소면 CI 에 읽기 토큰이 필요하다 |
| 한 저장소로 합친다(SDLC 안내서 §2.B) | 문제가 사라진다 | 기획 문서를 따로 나눠 보내기 어렵다 |

**추천:** 1인·작은 프로젝트는 한 저장소. 두 저장소라면 복사 + 사본 대조.

---

## 8. 함정 (BHQ 에서 실제로 밟은 것)

1. **같은 글자, 다른 뜻.** 도구는 파일 이름과 경로만 본다. 그래서 "플레이북은 `intent.md` → `spec.md` → `plan.md` 순서" 같은 일반 개념이나 다른 저장소의 같은 이름 파일, `T<n>` 같은 자리표시자까지 잇는다. 09-29 첫 적용 때 648곳 중 18곳이 이랬다. 10-21 따라잡기 때는 285곳을 전수로 읽었고 잘못 0, 애매 1 이었다(함정 13). 연습용 저장소에서도 "일반 개념으로서의 `spec.md`" 가 그대로 이어졌다. **문장을 읽는 검증만 잡는다.** 새 문서에 일반 개념으로 파일 이름을 쓸 때는 백틱을 쓰지 않는다.
2. **새 폴더·새 이름 꼴 → 멈춤.** 귀찮지만 장점이다. 모르는 문서를 아무 종류로나 분류하지 않는다(§5.3).
3. **건드리면 안 되는 md 가 있다.** 묶음에서 빼거나 묶음 밖에 둔다.
   - 해시로 묶인 문서: BHQ 약관 md 는 동의 기록이 파일 sha 를 가리킨다. 한 글자만 바뀌어도 기록이 끊긴다.
   - 시험이 읽는 문서: BHQ 는 실행서의 코드 블록·제목을 읽는 시험이 있다. 링크는 코드 블록 안을 안 건드리지만, 적용 뒤 전체 시험을 꼭 돌린다.
   - 에이전트 설정: `CLAUDE.md`·`SKILL.md`·에이전트 정의.
4. **`status` 낱말 충돌.** §1.3.
5. **저장소 사이 링크는 GitHub 에서 안 열린다.** `../backend/docs/…` 같은 링크는 두 저장소가 나란히 있는 작업 폴더와 편집기 미리 보기에서만 열린다.
6. **파이썬 판.** pyenv 가 폴더의 `.python-version` 을 따라 PyYAML 없는 파이썬을 고른다. 도구는 이때 까닭을 말하고 멈춘다. 가상환경 파이썬을 절대 경로로 쓴다.
7. **규격이 움직인다.** 판 번호가 같아도 규칙이 바뀐다. 커밋을 고정하고, 다음 단계 전에 `SPEC.md` 커밋이 바뀌었는지 본다.
8. **사본은 어긋난다.** 09-29 실측: 옵시디언 복사본 46개 중 27개가 원본과 달랐다(리서치 §11.7). 정본(SSOT)은 저장소 하나다. 사본 폴더는 묶음과 링크 대상에서 뺀다(`exclude_dir_globs`·`never_target_globs`).
9. **상대 경로 vs `/` 경로.** 규격은 `/` 로 시작하는 묶음 기준 경로를 권한다. BHQ 는 상대 경로를 골랐다. 인계 사본과 편집기 미리 보기에서도 링크가 살아야 했기 때문이다.
10. **zsh 는 변수를 안 쪼갠다.** `O="python okf.py --root docs"; $O check` 는 `command not found: python okf.py --root docs` 로 죽는다. 첫 낱말을 절대 경로로 쓰면 `no such file or directory` 가 나온다. 둘 다 통째를 명령 이름 하나로 읽은 것이다. 함수·배열을 쓴다(§6 머리).
11. **백틱 글자를 링크 글 안에 남긴다.** 다른 검사기가 백틱 글자를 읽을 수 있다. BHQ 의 `check_index.sh` 는 `spec.md` 색인 표의 백틱을 읽는다. 감싸기만 하면 그 검사도 그대로 통과한다.
12. **여러 세션이 같은 문서를 동시에 고친다.** 커밋은 `git add -A` 대신 파일을 지정해서 한다(`--pathspec-from-file`). 도구의 "읽은 뒤에 바뀐 문서" 멈춤이 동시 고침을 한 번 더 막는다.
13. **링크 대상은 작업 폴더의 지금 모습으로 찾는다.** 형제 저장소에 아직 병합 안 된 가지가 체크아웃돼 있으면, 그 가지에만 있는 파일로도 링크가 생긴다. 10-21 의 애매 1건이 이것이었다. plan 에서 진행 중인 T61b 계획서로 링크가 이어졌는데, 그 파일은 backend 의 병합 전 가지에만 있었다. 뜻은 맞아서 그대로 두었다. 그런데 17분 뒤(15:54 → 16:11) 그 가지를 맡은 세션이 `plan.md` 68행을 새로 쓰면서 링크가 보통 글자로 돌아갔다(§7.2 표). 그 가지(PR #225)가 병합된 뒤 `link --apply` 로 다시 잇는다. 링크를 만들기 전에 형제 저장소가 main 에 서 있는지 보거나, 독립 검증에서 "대상이 main 에 있나"(`git cat-file -e origin/main:<경로>`)를 같이 본다.

---

## 9. 이식 완료 점검표

- [ ] `okf.toml` 에 `spec_commit` 이 있고, `SPEC.md` 최신 커밋과 대조했다
- [ ] 종류 목록을 사람이 정했다. "나머지 전부" 규칙이 없다
- [ ] 건드리면 안 되는 md(해시로 묶인 문서·시험이 읽는 문서·에이전트 설정)를 묶음에서 뺐다
- [ ] `label` 다시 돌림 → `{'같음': N}`
- [ ] 새 링크를 다른 세션이 문장을 읽고 검증했다 → 잘못 0
- [ ] `index` 다시 돌림 → `목차 0개 만들 것`
- [ ] `check --strict` → `위반 0건 — 통과`
- [ ] 적용 뒤 전체 시험 통과(시험이 문서를 읽는 저장소라면)
- [ ] `guard.sh` 에 실행 권한이 있고, pre-commit 또는 pre-push 에 `OKF_PYTHON` 과 함께 걸려 있다
- [ ] 정상 문서 커밋은 `OKF guard OK` 로 통과하고, 머리말 없는 문서 커밋은 `type 이 없는 문서가 있다` 또는 `머리말이 없다` 로 막히는 것을 봤다(`Permission denied`·`PyYAML 이 없거나` 로 막혔다면 통과가 아니다)
- [ ] CI 결정론 잡에 guard 단계가 있다(저장소가 둘이면 §7.4)
- [ ] 새 문서 틀에 `type` 을 미리 넣었다
- [ ] `CLAUDE.md` 에 네 명령 한 줄이 있다

---

## 10. BHQ 따라잡기 기록 (2026-10-21)

| 저장소 | 커밋 | 바뀐 것 | 검증 |
|---|---|---|---|
| plan | `06562a5` | 문서 16개에 링크 96개 · 규칙 `*-plan.md` → `Plan` | `label` 같음 71 · `index` 같음 8 · `check --strict` 위반 0 · `check_index.sh` OK · 사본 결과와 `diff -r` 0 |
| backend | `fbd9def` (가지 `docs-okf-catchup`, PR #224) | 계획서 27개에 `type`(그중 머리말이 없던 6개는 새로 만듦) · 링크 189개 · 목차 3개 · 규칙 `account/*` → `Spec` | `check --strict` 위반 0 · `make verify` 7283 passed(가지 전용 시험 DB) |

두 저장소 합쳐 새 링크 285개를 다른 세션(검증 에이전트)이 앞뒤 문장과 대상 제목을 대조해 전수로 읽었다. 잘못 0 · 애매 1(§8 함정 13). 링크 말고 바뀐 글자는 없었다.

연습용 저장소(BHQ 와 무관한 `docs/` 하나, 문서 5개)에서는 도구를 고치지 않고 `label` 5 · `link` 5 · `index` 3 · `check --strict` 위반 0 이 나왔다. `guard.sh` 는 §7.2 표대로 움직였다.




---

# Resources

- OKF 규격: https://github.com/GoogleCloudPlatform/open-knowledge-format (`SPEC.md` @ `0b87c52c6ef999286c745e19998fdfcd03d5dbee`, 2026-08-21). 인용한 절: §5.4 status · §6.1 링크 · §11 적합 조건
- 짝 문서(SDLC 이식 안내서): `/Users/damienpark/Desktop/BHQ/2026-10-06-ai-native-sdlc-porting-guide.md`
- BHQ OKF 리서치(정본 기록, §11 이 적용 기록): `/Users/damienpark/Desktop/BHQ/plan/research/2026-09-29-okf-open-knowledge-format-research.md`
- 도구: `/Users/damienpark/Desktop/BHQ/plan/scripts/okf/okf.py` · plan 설정 `/Users/damienpark/Desktop/BHQ/plan/scripts/okf/okf.toml` · backend 설정 `backend/docs/okf.toml`
- BHQ SDLC 프로세스 설계: `/Users/damienpark/Desktop/BHQ/plan/2026-09-05-bhq-sdlc-process-design.md` (status 값은 118행)
- `status` 필수 프로필의 예: homeagent `ADR-006 plan/ 문서는 OKF v0.2 프로필로 쓴다` (옵시디언 `300.RESOURCE/360.Claude/homeagent-ADR-006-plan-docs-okf-format.md`)
- 저장소: plan `github.com/DAMIEN-PARK/BHQ_plan` · backend `bctone1/BHQ_backend`
