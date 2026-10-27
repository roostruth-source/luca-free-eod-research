# LUCA V0.3 — 2026-10-27 20:43 KST 전향 시험 직전 통합 모의검수

**연구 전용 / SYNTHETIC FIXTURES ONLY / NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS**

## GitHub 실행
- 연구 브랜치: `research/v03-stage24-evidence`.
- 모의검수 GitHub Actions https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40498203537 **성공**.
- 전체 오프라인 연구시험 **273/273 통과** (이번 10개 추가).
- `research/v03_stage24/test_live_trial_contract.py`: 합성 후보를 T0에 고정 -> 16분 후 합성 IEX 분봉으로 신호 검출 -> 합성 5/15/30/60분 가격과 전체 후보 고정시각 비교 -> 출처 확인된 한국어 보고서 생성까지 하나의 연결된 시험. 원본 후보 바꿔치기, GitHub 실패, 잘못된 브랜치, 성숙하지 않은 미래 결과, 데이터 0개와 신호 0개, A/B 승인 방지 등을 검수.
- 이번 시험은 합성 데이터만 사용했고, 실제 시장 예측 정확도를 측정하지 않았음.

## 실제 예약 상태 확인
- 2026-10-27 **23:02 KST** 첫 실제 전향 T0 예약 `6ae074bfe9fc81919c5887c830efc0ff`: 활성, 과거 실행 기록 없음 (20:41 KST 확인). 뉴욕 시간 **10:02 ET**.
- 2026-10-28 **02:15 KST** 원본 및 후속 검증 예약 `6ae074dfa26c81919213f5b223a9406b`: 활성, 과거 실행 기록 없음 (20:41 KST 확인). 뉴욕 시간 **13:15 ET**.
- 확인 당시 source workflow `LUCA V03 forward IEX once on isolated request file` GitHub 실행 **0건**, 요청 파일 `prospective_live_request.txt` 없음. 이 상태는 **아직 실행 전**, 종목 없음/실패가 아님.
- 앞서 GET-only 실제 데이터 연결 시험에서 119종목 스크리너 + 4개 IEX snapshot 배치 모두 정상, 263개 오프라인 안전시험 통과.

## Work에 넘길 실행 수칙
1. 23:02 KST 예약 작업이 **정확한 미국 장중 날짜/시간**에서 연구 브랜치 요청 파일을 단 한 번 만들도록. 중복 요청·수동 조기 기동 금지.
2. GitHub 원본 실행의 `frozen_t0.json`, `forward_review.json` 존재 및 T0 해시/후속 분봉을 실제 아티팩트로 확인. 후보 0/분봉 0/실패 구분.
3. 02:15 KST 예약은 **성공한 source run**만 후속 요청. 이후 한국어 보고서 `luca_v03_korean_report/report.md`를 확인. 생성되지 않았다면 누락이라고 명시.
4. 모든 신호 연구 D, SEC_UNVERIFIED, NOT_VALIDATED, NO_ORDERS. IEX 단일 거래소, 시총/Float/SEC 증자 검증 불가.
5. 운영 main, 사이트, /api/radar, 정기 알림, 기존 5/20일 고정 관찰, 실제 주문 기능 변경 금지.

**새 예약/알림/라이브 T0 실행 없음.**
