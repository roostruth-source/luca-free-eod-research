# LUCA V0.3 — T0 동결 증거품질 자동검수 (2026-10-27)

**NOT_VALIDATED · SEC_UNVERIFIED · NO_ORDERS**

## 실제 코드 검증
- 연구 브랜치 전용 신규 파일 `research/v03_stage24/evidence_quality_gate.py` + `test_evidence_quality_gate.py`.
- GitHub Actions [40487785767](https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40487785767): 독립 연구시험 **180/180 전부 통과** (새 검사 25개).
- 원래 T0 동결 해시와 16분 IEX 첫 관찰 결과를 묶어 **관측 자료의 완전성**을 판정.
- 임의의 16분 구간을 소급 수정하지 않음. 초기에 후보가 된 전체 종목을 유지.
- 첫 창 관찰:
  - `PATTERN_RECORDED`: 실제 기록된 연구 패턴이 있음. 효과/수익 예측 증거는 아님.
  - `NO_PATTERN_OBSERVED`: 해당 관측 분봉 완전, 연구 패턴 없음. 주가 실패 또는 급등 부재 증거는 아님.
  - `NO_PATTERN_WITH_GAPS`: 분봉 부족한 상태에서 패턴 기록 없음.
  - `NO_IEX_BARS`: 아예 관찰봉 없음. 이 경우 실패 0%나 수익률 0%로 계산하지 않음.
- 후속 5·15·30·60분 신호 연구 및 고정시각 비교군 보고는 **선택적으로** 결합하며, 자료가 없으면 `AWAITING_OR_UNAVAILABLE`; 있더라도 동일 T0 해시/동일 첫 관찰/시간 성숙/전체 표본/개별 시각/분봉 누락/가정수익 표기/주문 차단 상태 등 맞아야 함.
- 신호가 있던 종목, 처음에 신호가 없던 종목, 데이터 부족 종목을 분리. 5·15·30·60분 가정가격 관찰은 신호를 직접 측정한 효과나 실제 체결수익 아님.
- 어떤 경우에도 `quality=INSUFFICIENT_FOR_PREDICTION`, `all_grades A=0,B=0,C=0,D=후보전수`, `prediction_accuracy_verified=false`, `real_trades_allowed=false`.
- 본 단계는 **오프라인/합성 데이터 안전시험**. 오늘 밤 1회 전향 실제 결과를 만든 것으로 말하면 안 됨.

## 실제 후속 연구 연결
- 기존 `.github/workflows/luca-v03-followup-once.yml` 파일의 옵션 스텝으로 추가. 기존 `followup_live_request.txt`가 트리거된 후에만 실행하고 별도의 `luca_v03_quality/quality.json` 아티팩트를 추가.
- 검증 오류는 감추지 않고 step 실패로 남기되 `continue-on-error`이므로 기존 시장 결과 수집에 영향을 주지 않음. 품질 보고 부재를 성공으로 해석하면 안 됨.
- 기존 오늘 밤 1회성 시험 23:02 KST 시작/02:15 KST 결과 확인 예약은 **변경하지 않음**. Work가 동일 GitHub 실측을 중복 트리거하지 않도록 주의.

## 다음 과학적 검증의 핵심
1. 실제 전향 T0 후보 동결과 이후 16분 실측 **실행 여부**를 먼저 GitHub에서 확인.
2. 부정확한 SEC 자료/시총/Float는 UNKNOWN으로 유지.
3. 연구 신호와 무신호/누락 대조군을 며칠 이상 비교하며, 신호가 0건인 날도 데이터 품질과 함께 보존.
4. 실거래를 논하려면 SIP 호가/체결 스프레드/슬리피지/거래정지/희석 유인을 독립 검증할 것.

**운영 main, /api/radar, 기존 정기알림, Stage24 고정20거래일, 별도5거래일 시험 및 실제 주문 기능 변경 없음.**
