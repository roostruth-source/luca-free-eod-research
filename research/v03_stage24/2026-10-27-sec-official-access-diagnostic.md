# LUCA V0.3 — SEC 공식 서버 접근 문제 독립 진단

**실행 시점:** 2026-10-27 KST / **상태:** NOT_VALIDATED · 실제 주문 금지

## 실제 GitHub Actions 결과
- 실행: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40476303905
- 독립 연구 브랜치: `research/v03-stage24-evidence`
- **70/70 오프라인 안전성 시험 통과**.
- GitHub Actions 환경에서 **SEC 소유 공식 URL 세 곳**에 GET-only 요청:
  - `https://www.sec.gov/files/company_tickers.json` → **HTTP 403**
  - `https://data.sec.gov/submissions/CIK0000896493.json` (GPUS) → **HTTP 403**
  - `https://data.sec.gov/submissions/CIK0001951222.json` (LAES) → **HTTP 403**
- SEC 서버가 응답한 구체적인 거부 원인은 아직 모름. 네트워크/UA/정책 중 어느 것인지 단정하지 말 것.
- 프록시, 비공식 미러, 우회 또는 과도한 재시도 없음.
- **공시 내용 검증 0건, CIK 신규 검증 0건, SEC 안전 승인 0건**. 연구판의 45개 가격대 후보 전부 공시 미확인·매수 금지 상태 유지.
- 진단 JSON은 workflow artifact `luca-v03-official-sec-diagnostic-40476303905`로 보관 (7일).

## 다음 단계
1. Work에서 SEC가 허용하는 접속 환경과 연락처가 포함된 적절한 User-Agent, 요청 빈도 등을 공식 정책에 맞게 확인. 실제 응답을 재검증하기 전에는 '해결됨'으로 표시하지 않기.
2. SEC 1차 자료 자동조회가 가능한 환경을 찾을 때까지 CIK/증자/ATM/전환/워런트/등록 효력은 **UNKNOWN / BLOCKED**로 유지.
3. 별도 IEX 1분봉 자료 품질 및 시간순 신호 계산 연구는 계속 가능하지만, **SEC 승인 및 매수등급과 연결하지 않기**.
4. 현재 수집한 119개 종목은 시세 스크리너 합집합이며, 그중 45개는 가격만 필터링됨. 시가총액·유통주식수 검증 미완료.

## 불변 조건
기존 main, 운영 사이트, /api/radar, 예약 알림, 5거래일 시험, Stage24 20거래일 고정 규칙 변경 없음. 자동주문 없음.
