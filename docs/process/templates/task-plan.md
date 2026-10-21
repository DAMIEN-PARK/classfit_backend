---
type: Task Plan
title: 
description: 
date: 
tags: 
Archives: false
URL: ""
---

# Plan: T<n> <slug> (from plan.md#T<n>, <YYYY-MM-DD>)

- 근거: intent `<파일>` · spec 절 `<설계 문서 §…>` · 태스크 `plan.md#T<n>`
- 승인: 
- 승인 방법: 승인자 `DAMIEN-PARK` 이 이 가지에 `git commit --allow-empty -m "approve: T<n>" -m "Approved-by: DAMIEN-PARK"` 를 더한다. 그 커밋 전에는 코드 변경이 없고, 에이전트는 위 줄과 `Approved-by` 를 쓰지 않는다.

## 바뀌는 파일

- `path/one.py` (new|modify): 한 줄 이유
- `tests/…` (new): 무엇을 고정하는가

## 작업 순서

1. …

## 위험

- 무엇이 깨질 수 있고, 어떻게 알아채는가(테스트·게이트·리허설).

## 증명

- 테스트: `pytest tests/…::test_…` 기대 결과
- 명령: `make verify` 출력 요약
- 계약: 설계 문서 Verify 줄 인용

## 리뷰

(다른 세션의 reviewer 가 쓴다. Important n건 · Nit n건, 소견과 고친 커밋. Important 0 이 될 때까지 고친다 — r3 §5.1-3)

## 계획과 다르게 한 것

(구현 중 채운다. 비어 있으면 계획대로다.)




---

# Resources

