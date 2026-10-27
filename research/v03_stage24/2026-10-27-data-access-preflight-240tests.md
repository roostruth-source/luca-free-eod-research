# LUCA V0.3 — 2026-10-27 실시간 전향 T0 이전 시장 데이터 연결 사전점검

**연구 전용 / NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS**

## 실측 연결 결과
- GitHub Actions 단발 실행: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40491454274
- GitHub job: **success**, 연구 전체 오프라인 안전시험 **240/240 통과**.
- 실제 외부 GET 응답:
  - Alpaca screener 세 소스: `SCREENER=GET_OK`.
  - 자동 발견 종목 1개에 대한 IEX snapshot: `IEX_SNAPSHOT=GET_OK_SCHEMA_ONLY`.
  - 같은 종목의 과거 IEX 1분봉 요청: `IEX_1MIN=GET_OK_SCHEMA_ONLY`.
- 결론: 세 데이터 API가 연결되고 조회 스키마가 정상. **현재 장중 신선한 분봉이 충분한지, 전체 시장 SIP 가격/호가, 급등 전조 예측이 유효한지는 검증되지 않음**. 과거 1분봉은 데이터 접근 권한 점검이며 전향 실측 아님.
- 출력: `READY=DATA_ENDPOINTS_ACCESSIBLE_ONLY`, `NO_LIVE_T0`, `NOT_VALIDATED`, `NO_ORDERS`.
- 이 단계는 기존 라이브 1회성 전향 시험을 트리거하지 않았고, 연구용 사전점검 파일만 트리거.
- SEC GitHub HTTP403, market cap/float/희석 위험 미확인 지속. **매수 A/B 승인 금지**.

## 코드 및 안전
- 신규 `research/v03_stage24/market_data_preflight.py` 및 `test_market_data_preflight.py` (12개 독립 오프라인 테스트).
- 단발 workflow `.github/workflows/luca-v03-market-preflight-once.yml`: 연구 브랜치 요청 파일에만 반응, GET-only 3종 데이터 접근 검사. 비밀 API 키를 결과에 쓰지 않음. 7일 보존 진단 아티팩트.
- 현재 기존 실측 source workflow `LUCA V03 forward IEX once on isolated request file`는 0건. **오늘 밤 예약된 23:02 KST Work 실행을 중복 트리거하지 않음**.
- 운영 main, 배포, /api/radar, 정기 알림, 기존 5일/20일 고정 시험, 거래 API 수정 없음.

## 다음 단계
1. 23:02 KST 전향 1회 예약이 실제 GitHub `prospective_live_request.txt`를 트리거했는지 확인.
2. 그 실행의 source run ID, `frozen_t0.json` 동결 해시, `forward_review.json` 16분 뒤 IEX 분봉 수, 신호 0건/자료 0건 구분 확인.
3. 02:15 KST 결과 확인 예약에서 동일 T0의 5/15/30/60분 후속 실측과 실패 실행 목록을 검증. 없는 자료를 0% 수익률로 쓰지 않음.
4. SEC/float/SIP/실체결 증거 전까지 연구 상태만 유지.
