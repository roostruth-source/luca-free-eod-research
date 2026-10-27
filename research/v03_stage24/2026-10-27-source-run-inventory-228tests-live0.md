# LUCA V0.3 — 실패한 GitHub 전향 실행도 포함하는 원본 실행 기록 (2026-10-27)

**연구 전용 · NOT_VALIDATED · SEC_UNVERIFIED · NO_ORDERS**

## 실제 확인
- 연구 전용 `source_run_inventory.py` + `test_source_run_inventory.py` 추가.
- GitHub 연구 브랜치 단발 메타데이터 실조회: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40488999055
- **228/228 전체 독립 연구 안전시험 통과.**
- 해당 실조회 당시 **`LUCA V03 forward IEX once on isolated request file` GitHub workflow의 실행 0건**. 따라서 성공 0, 실패/취소 0, 대기 0. **이것은 시장 신호가 0건이라는 증거가 아니라 해당 특정 GitHub workflow 실행 자체가 없었다는 의미**.
- 연구 브랜치 전체 GitHub Actions는 여러 건 있었지만, 이 전향 실측 workflow는 아직 실행되지 않음. 일반 연구/단위시험을 전향 실측으로 오인하면 안 됨.
- 첫 실조회 실행 [40488855280](https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40488855280)은 GitHub의 브랜치 전용 workflow file 이름 조회가 404를 반환해 **메타데이터 조회 실패**. 그 후 `repos/{owner}/{repo}/actions/runs?per_page=100`로 전체 목록을 읽고, **해당 source workflow 이름·경로·브랜치·push 이벤트만 엄격히 추출**하도록 수정한 후 재실행 [40488999055](https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40488999055) 성공.
- 첫 404는 **새 연구 메타데이터 감사 workflow 자체의 실패**이지, 전향 T0 주식 관찰의 실패가 아님. 이 차이를 명시적으로 유지.

## 보호 장치
- GitHub 완료 상태 `success`, `failure`, `cancelled`, `timed_out`, `skipped` 등과 진행 중 상태를 분리. 성공 GitHub 실행이라도 종목 신호 성공, T0 해시 검증 성공, 매수 수익 실현으로 간주하지 않음.
- 동일 run ID 중복 차단, 다른 workflow/branch 혼입 차단, API 응답이 일부 페이지만 반환된 경우 **실행 횟수 계산 중단**. 100개 초과시 페이지 처리 구현 전에는 미완성으로 처리.
- GitHub가 아예 기동되지 못한 외부 ChatGPT Work/예약 시도는 GitHub Actions 목록에서 관찰되지 않으므로 **전체 예약 성공률 계산 금지**.
- 별도 `luca-v03-run-inventory-once.yml`는 연구 요청 파일만 트리거, 정기 예약/운영/거래 API 없음.
- 기존 `luca-v03-followup-once.yml`에도 optional 읽기 전용 기록을 추가하여 장중 T0 후속 실행 시 성공/실패/대기 상태 메타데이터를 아티팩트로 보존.
- 기존 5거래일/20거래일 고정 연구, 운영 `main`, `/api/radar`, 정기 알림, 배포, 실제 주문 기능 **변경하지 않음**.

## 다음 연구 순서
1. 이미 별도 예약된 2026-10-27 23:02 KST **전향 T0 단 한 번 실행**을 GitHub에서 확인. 중복 실행 금지.
2. 2026-10-28 02:15 KST 결과 확인 시 실측 source run ID, GitHub 실행 상태, T0 동결 해시/관찰 분봉/후속 60분 성숙 상태를 따로 검증.
3. 소스 GitHub 실패 실행과 데이터 없는 종목, 신호 없는 종목을 분리. SEC 403, Float/시총/호가 검증 미완료 상태에서는 A/B 매수 가능 등급을 절대 발급하지 않음.

**이 시점 실제 전향 실측 데이터 0건. 228은 오프라인 검수 테스트 통과 건수임.**
