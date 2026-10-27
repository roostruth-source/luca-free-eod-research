# LUCA V0.3 — 한국어 전향 실측 결과 자동 요약 (2026-10-27)

**연구 전용 / NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS**

## 구현과 검증
- 신규 `research/v03_stage24/korean_forward_report.py` 및 `test_korean_forward_report.py`.
- 전체 연구 안전시험 **254/254 통과** (이번 단계 추가 14개):
  https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40492084476
- 초기 합성 시험에서 4개 불일치를 발견. 기존 엄격한 원본 검증이 거부하는 빈 후보/위조 해시/매수등급을 보고서가 무리하게 받아들이지 않도록 시험 기대값을 수정. 최종 재시험 통과.
- 성공한 GitHub 전향 source run의 `followup_source_metadata.json`, T0 `frozen_t0.json`, 16분 뒤 `forward_review.json` 필수. 선택적으로 5·15·30·60분 `outcomes.json` 및 `fixed_clock_reference.json` 결합.
- 원본 workflow/branch/run ID/성공 상태 및 T0 해시/동일 후보/시각/안전 플래그를 재검증. 위조된 자료는 보고서 생성 차단.
- 한국어 결과: 원본 GitHub 링크, T0 UTC 시각/해시, 후보 수, 관찰된 IEX 1분봉, 패턴 기록 수, 분봉 누락 수, 후속 5·15·30·60분 상태, 고정시각 비교 상태, 종목별 연구 D등급 및 이유.
- 분봉 누락과 완전 관찰 후 패턴 미발생 구분. 둘 다 급등 실패나 수익률 0%로 해석 금지. IEX는 SIP가 아님. SEC/Float 미확인 상태 유지.
- 기존 연구 브랜치의 `.github/workflows/luca-v03-followup-once.yml`에 선택적 한국어 Markdown 보고서 생성 단계 추가. 후속 검증이 실행될 때 `luca_v03_korean_report/report.md`로 저장. **알림 자동 전송 없음**. 오류 시 기존 아티팩트 수집을 막지 않되 보고서 부재는 미확인으로 보고.
- **실제 장중 T0 source workflow는 아직 실행 확인되지 않음**. 이번 단계는 합성 오프라인 검증만 완료, 실제 급등 예측 결과 없음.
- 이미 예약된 23:02 KST 전향 시험과 02:15 KST 결과 확인을 중복 기동하지 않음.
- 운영 main, 배포, /api/radar, 정기 스캐너 알림, 기존 5거래일/20거래일 관찰, 실제 주문 기능 변경 없음.

## Work 후속
1. 기존 1회 예약된 T0 시험의 GitHub 실행 및 동결 아티팩트를 먼저 확인.
2. 원본 성공 후에만 정확한 run ID로 기존 후속 1회 검증을 실행.
3. GitHub 후속 아티팩트에 `luca_v03_korean_report/report.md`가 생성됐는지 확인하여 쉬운 한국어로 사용자에게 요약. 없으면 생성되지 않았다고 명시.
4. 실제 SEC 증자/CB/워런트, Float, 시총, SIP/호가/슬리피지 미확인 상태에서 매수등급 승인 금지.
