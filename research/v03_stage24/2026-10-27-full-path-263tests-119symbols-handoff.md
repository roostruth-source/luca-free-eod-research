# LUCA V0.3 — 2026-10-27 실측 T0 직전 전체 데이터 경로 검사

**연구 전용 / SEC_UNVERIFIED / NOT_VALIDATED / NO_ORDERS**

## 실제 GitHub 실행
- 단발 read-only full-path 진단: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40492493883
- **GitHub job success**, 연구 전체 오프라인 **263/263 테스트 통과**.
- 실제 외부 Alpaca GET 결과: **스크리너 자동 검색 119종목**, IEX 스냅샷 **4개 배치 전부 성공**, **119종목에 가격 데이터**. API 호출은 자동 후보를 사용, 수동으로 임의 종목 지정 없음.
- 상태: `ALL_BATCH_GET_OK_SCHEMA_ONLY`. 과거 단일 종목 사전점검과 달리 실제 T0가 호출하는 다중 IEX 배치 접근 경로 전체를 시험.
- 이 숫자는 **119개가 매수 후보라는 뜻이 아니며**, 가격이 $0.20~$20 범위라는 뜻도 아니고, 신선한 정규장 호가라는 뜻도 아님. **장중 T0 신호 수는 아직 미확인**.
- 실제 외부 접근을 한 것은 GET-only screener + snapshots. 16분 후 실제 시장분봉, 예측 성능, SEC 증자/전환사채/워런트, 시총/Float, SIP 전체 호가, 체결 가능성은 미확인.

## 변경 범위
- `research/v03_stage24/full_path_access_probe.py` + `test_full_path_access_probe.py` (9개 오프라인 시험).
- 연구 브랜치의 별도 요청 파일로 **한 번만 실행**하는 `.github/workflows/luca-v03-full-path-access-once.yml`. 정기 실행 없음.
- 기존 연구 전향 T0 실행 요청 `prospective_live_request.txt` **생성/수정하지 않음**. 기존 23:02 KST 예약과 02:15 KST 확인 예약 중복 기동하지 않음.
- 운영 `main`, 배포, `/api/radar`, 기존 5/20일 고정 시험, 정기 알림, 거래 API 변경 없음.

## Work 다음 확인
1. **예약된 실제 T0 GitHub source workflow**가 지정된 미국 정규장 오전에 시작됐는지 확인; 없으면 `NOT_RUN`, 후보 0개라고 쓰지 않음.
2. source run 성공 여부와 `frozen_t0.json`, `forward_review.json`를 동일 GitHub run ID로 묶고 T0 해시 검증.
3. 5/15/30/60분 결과는 해당 시점이 지난 뒤 IEX 분봉이 실제 있을 때만 표시.
4. 한국어 보고서는 `luca_v03_korean_report/report.md`에서 읽고 누락 분봉과 신호 없음 구분.
5. SEC GitHub 403 및 Float 미확인 상태에서 모든 종목 연구 D/매수 금지 유지.

**263개는 프로그램 안전 테스트이지 급등 예측 적중 횟수가 아닙니다.**
