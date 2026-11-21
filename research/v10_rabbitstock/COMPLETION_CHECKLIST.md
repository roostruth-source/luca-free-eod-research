# LUCA V10 연구판 완성 체크리스트

기준일: 2026-11-19 (Asia/Seoul)

이 문서는 테스트 개수만으로 완성을 선언하지 않는다. 실제 GitHub Actions와 생성된 live artifact 근거가 있어야 `COMPLETE`로 바꾼다. 모든 단계는 `WATCH_ONLY`, `NOT_VALIDATED`, `SEC_UNVERIFIED`, `NO_ORDERS`를 유지한다.

| 번호 | 완성 기준 | 상태 | 현재 근거와 남은 일 |
|---:|---|---|---|
| 1 | NASDAQ 7.0·중국계 1.0 독립 탐지와 통합 watchlist | PARTIAL | Alpaca screener 출처 순위와 관찰시각은 원장에 고정된다. 좁은 SEC PRC Operations 문구를 근거로 중국계 1.0 live 집단·원장·성과표를 분리했다. 실제 SEC 원문 적중 artifact 확인 전까지 PARTIAL을 유지한다. |
| 2 | Volume-First·종목종류·역분할·상장위험 연결 | PARTIAL | Volume-First, 장전/정규장, ETF·Warrant·Unit 차단과 Nasdaq Financial Status 0점 보류는 실제 artifact로 확인됐다. SEC 원문에서 역분할·최저주가·상장미달·상장폐지/청문 문구를 보수적으로 0점 보류하는 연결도 구현됐다. 최신 실제 artifact에서 해당 원문 신호가 있는 종목을 확인하기 전까지 PARTIAL을 유지한다. |
| 3 | SEC 원문 기반 OS·Float·ATM·CB·Warrant·ELOC·등록효력·CB Reset | PARTIAL | ATM·ELOC·CB·Warrant·Shelf 문구와 SEC Company Facts의 공시 기준일 OS를 live 후보·전향 원장·성과집단에 연결했다. Float 주식 수·잔여한도·등록효력·CB Reset 계약식은 아직 미검증이다. GitHub Actions의 SEC HTTP 403에서는 추정하지 않는다. |
| 4 | SEC 직접 수집 영수증과 50종목·72시간 제한 | PARTIAL | capture/build/validate 코드와 회귀 테스트가 있다. 최신 실제 watchlist용 공식 bundle이 Actions artifact에 들어간 실행 근거는 아직 없다. |
| 5 | 전향 원장과 1·3·5·10거래일 성과 | PARTIAL | 해시 원장, MFE/MAE/종가 성과, 중복 티커 제거, 장전·정규장 분리는 구현됐다. 표본 30개 문턱과 실제 성능 검증을 분리했으며, 기업행사 보정·독립 시세·실제 체결 검증 전에는 완료로 바뀌지 않는다. |
| 6 | 아이폰용 쉬운 한국어 HTML/JSON | PARTIAL | 우선순위·이유·위험·종목 종류·상장상태·SEC 희석위험과 검증된 공시 기준일 OS를 쉬운 한국어로 표시한다. Float와 계약별 잔여한도 설명은 아직 필요하다. |
| 7 | 전체 CI와 실제 live artifact 안전 검증 | COMPLETE | PR #30과 병합 HEAD의 전체 CI가 성공했다. 최신 전향 원장 2,015건에서 주문금지·매수신호 오인 위반은 모두 0건이었다. SEC 403 때문에 실제 OS 관측은 없었으며 이를 검증 완료로 과장하지 않는다. |
| 8 | 주문 금지 안전 상태 | COMPLETE | 실제 artifact와 테스트에서 WATCH_ONLY·NOT_VALIDATED·NO_ORDERS가 유지된다. 자동매수·주문 endpoint는 없다. |
| 9 | 체크리스트와 근거 지속 갱신 | ACTIVE | 이 파일을 매 작업 후 커밋·Actions·artifact 근거와 함께 갱신한다. |
| 10 | 최종 회귀검사·완성 보고·자동화 정지 | PENDING | 1~9의 필수 항목과 외부차단 설명이 끝난 뒤 수행한다. main 병합과 배포는 별도 승인 대상이다. |

## 현재 검증 근거

- 장전 가격 문맥 PR: https://github.com/roostruth-source/luca-free-eod-research/pull/21
- 실제 성공 실행: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44531212641
- Nasdaq Financial Status PR: https://github.com/roostruth-source/luca-free-eod-research/pull/22
- Financial Status 실제 성공 실행: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44542213435
- PR #22 실제 결과: `D` 4개(CLRO·HIHO·NUR·UPLD) 모두 0점, `N` 30개, 다른 거래소 미제공 14개, 미확인 2개

## 다음 순서

1. 역분할·상장통지 0점 보류를 최신 CI와 실제 SEC 원문 artifact로 검증한다.
2. 최신 watchlist용 SEC Company Facts bundle을 실제 수집해 OS가 표시되는 artifact를 검증한다. Float는 공식 주식 수 근거가 있을 때만 붙인다.
3. 중국계 1.0 SEC 원문 적중 후보가 실제 artifact에 나타나는지 확인한다.
4. 독립 5거래일 표본 30개가 모이면 사전 고정 기준으로 성능을 판정한다.

## 2026-11-21 역분할 가격단위 착시 차단 (CI 및 live 검증 대기)

- 성과 일봉을 Alpaca IEX `raw`와 `split-adjusted` 두 방식으로 별도 수집한다.
- 같은 관찰 구간의 거래일 또는 OHLC가 다르면 `CORPORATE_ACTION_BASIS_BLOCKED`로 격리해 MFE·MAE·종가수익 통계에서 제외한다.
- 신선한 가격 관찰 수와 가격단위 차단 수를 따로 기록해 표본이 사라진 이유를 숨기지 않는다.
- 두 자료가 같아도 같은 제공자의 내부 비교일 뿐 공식 기업행사 검증이 아니다. `corporate_action_basis_verified=false`, `CORPORATE_ACTION_BASIS_UNVERIFIED`, `NOT_VALIDATED`를 유지한다.
- 관련 회귀검사에는 동일 자료 통과, 가격 차이 격리, 거래일 불일치 격리를 포함한다. 전체 CI와 실제 artifact에서 차단 수·주문 금지·표본 집계를 확인하기 전까지 완료로 표시하지 않는다.

## 2026-11-21 성과 표본 종목범위 분리 (CI 및 live 검증 대기)

- 기존 성과표가 신선 가격만으로 ETF·ETP와 Nasdaq 상장위험 상태까지 모델 검토 표본에 포함할 수 있던 문제를 수정한다.
- 모델 표본은 공식 디렉터리의 보통주 후보이며 Financial Status가 `N` 또는 다른 거래소의 `NOT_AVAILABLE`인 행으로 제한한다.
- ETF·비보통주·Nasdaq `D/E/Q/G/H/J/K/S/C`·미확인·옛 범위 누락 행은 모델 표본에서 제외한다.
- 제외 자료는 삭제하지 않고 별도 `descriptive_scope_audit_segment_scorecards`에 남겨 비교한다. 이 별도 표는 모델 성능 표본이 아니다.
- 신선 가격 수, 역분할 단위 차단 수, 종목범위 차단 수를 각각 기록한다. 전체 CI와 실제 artifact에서 정정된 독립 표본 수를 확인하기 전까지 완료로 표시하지 않는다.

## 2026-11-21 SEC 희석위험 원문 연결 (CI 및 live 검증 대기)

- SEC 원문에서 `ATM`, `ELOC`, `CB`, `WARRANT`, `SHELF`를 분리해 원문 URL·접수시각·문맥과 함께 `sec_supply_context`에 고정한다.
- 한 항목이라도 발견된 일반주는 `HOLD_SEC_SUPPLY_RISK` 0점 보류한다. 전향 원장과 신호별 성과집단에도 같은 근거를 저장한다.
- 문구 검출은 현재 잔여한도, 실제 전환 가능 수량, 등록효력, 희석 완료의 확정 근거가 아니다. 해당 값은 계속 미검증으로 둔다.
- 공식 OS·Float 숫자를 아직 연결하지 않았으므로 `shares_outstanding=null`, `float_shares=null`, `os_verified=false`, `float_verified=false`를 강제한다. 임의 추정값을 넣지 않는다.
- 아이폰 HTML에는 영어 원문과 쉬운 한국어 뜻을 함께 표시한다. 로컬 테스트 이후 PR·Actions·실제 artifact 검증이 남아 있다.

### PR #24 CI와 실제 artifact 확인

- PR: https://github.com/roostruth-source/luca-free-eod-research/pull/24
- Actions #44802069010 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44802069010
- Artifact `14661033340` ZIP SHA-256 `abb8ad7e7f4c4af018f3a16283243cdb5afedce0314ed3557d928253c0808d95` 일치 확인.
- 정규장 후보 40개: 우선 관찰 1, 근거 부족 12, 가격 보류 5, 범위 보류 15, 상장상태 보류 7, SEC 희석위험 보류 0. 모든 보류 종목의 양수 점수 0건, 주문 금지 위반 0건.
- 40행 모두 `SEC_SUPPLY_TEXT_UNAVAILABLE`; `shares_outstanding`·`float_shares` 임의 입력 0건, `os_verified`·`float_verified` 오표시 0건.
- 전향 원장은 1,585건에서 1,625건으로 `CHAIN_CONTINUED`; 신규 40행의 `sec_supply_context` 저장을 확인했다.
- 이번 실행은 `SEC_TICKER_MAP_HTTP_403`으로 실제 ATM·ELOC·CB·Warrant·Shelf 원문 적중 사례가 없었다. 상태는 `CI_PASSED_LIVE_SEC_SUPPLY_TEXT_UNOBSERVED`이며 완성 기준 3은 PARTIAL을 유지한다.

## 2026-11-21 SEC Company Facts OS 연결 (CI 및 403 artifact 검증 완료)

- 공식 SEC Company Facts의 `EntityCommonStockSharesOutstanding`만 OS(발행주식 수) 후보로 허용한다.
- 제출일 당일의 장중 선후를 추정하지 않고 제출일 다음 UTC 날짜부터만 사용한다. URL·해시·HTTP Date·수집시각·CIK·기준일·제출일·Form·Accession을 함께 검증한다.
- 같은 공시 정체성에 서로 다른 주식 수가 들어오거나 미래 수집시각·비공식 URL·해시/CIK 불일치가 있으면 실패 처리한다.
- SEC `EntityPublicFloat`는 달러 시장가치이므로 Float 주식 수로 환산하지 않는다. `float_shares=null`, `float_verified=false`를 유지한다.
- 검증된 OS는 아이폰 HTML과 해시 전향 원장에 고정하고 성과표를 `os:verified_point_in_time`과 `os:unverified`로 분리한다.
- 로컬 관련 테스트 65개와 V10 전체 회귀검사 214개, 기존 IEX 연결검사 14개 통과.
- PR #25: https://github.com/roostruth-source/luca-free-eod-research/pull/25
- PR Actions #44804901206 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44804901206
- 병합 HEAD `8192fe6` Actions #44805074385 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44805074385
- 병합 artifact `14663950048` ZIP SHA-256 `5c265578e4f2c2e8df938d0fa1bf83664493aae3ad84e35417473e9e0ac0ced1` 일치 확인.
- 실제 후보 40개: 근거 부족 14, 범위 보류 16, 상장상태 보류 6, 가격 보류 4. 주문금지 위반 0건, 보류종목 양수 점수 0건.
- 전향 원장 1,666건, 신규 40건, `CHAIN_CONTINUED`. 성과표 신선 관찰 223건, 독립 신선 티커 82개.
- 이번 실행도 `SEC_TICKER_MAP_HTTP_403`이라 실제 Company Facts 포함 bundle이 없었다. 따라서 OS·Float 입력은 모두 0건이며, 코드·회귀·안전 artifact는 통과했지만 **실제 OS 숫자가 표시된 live artifact 검증은 남아 있다.**

### OS 기준일 신선도 차단 (CI 및 403 artifact 검증 완료)

- SEC 공식 OS의 기준일에서 관찰일까지 `os_age_days`를 계산한다.
- 180일 초과 공식값은 삭제하지 않고 `os_stale=true`로 보존하되 현재 희석비율 계산에는 사용하지 않는다.
- 180일 이내도 실시간 현재값으로 부르지 않으며, Float·잔여 발행한도·등록효력은 계속 별도 미검증이다.
- 아이폰 HTML에는 기준일·경과일과 “오래된 과거값(현재 비율 계산 금지)”를 쉬운 말로 표시한다.
- 전향 원장은 경과일·오래됨 여부를 재계산해 위조된 신선도 표시를 거부한다. 성과표는 180일 이내와 오래된 OS 집단을 분리한다.
- V10 전체 회귀검사 224개와 기존 IEX 연결검사 14개 통과.
- PR #30: https://github.com/roostruth-source/luca-free-eod-research/pull/30
- PR Actions #44870593320 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44870593320
- 병합 HEAD `1328d212a696833d0d7a1e113c88011b0123b58b` Actions #44870814211 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44870814211
- 병합 artifact `14693538709`, GitHub SHA-256 `38833867bb200219b03fea01ceff0b41a98819631f81a2942c6c407fd5650d47`.
- PR artifact를 직접 검사한 결과 전향 원장 2,015건·신규 45건·`CHAIN_CONTINUED`, 주문금지 위반 0건, `priority_is_buy_signal=true` 오인 0건이었다.
- 성과표는 신선 관찰 303건, 독립 신선 티커 84개, 독립 3거래일 성숙 30개, 독립 5거래일 성숙 0개다. `sample_size_gate_met=false`, `performance_validation_ready=false`, `prediction_accuracy_verified=false`를 유지한다.
- 이번 실행도 SEC 원문 접근이 막혀 `os_verified=true` 실관측은 0건이었다. 새 필드는 430개 원장 행에 안전하게 고정됐고, 확인되지 않은 OS는 `os_current_enough_for_ratio=false`로 남았다. **코드·CI·안전 artifact는 검증됐지만 실제 오래된 Company Facts OS 적중 사례는 아직 없다.**

## 2026-11-21 중국계 1.0 live 집단 분리 (CI 및 403 artifact 검증 완료)

- SEC 원문에서 “대부분의 사업을 중국에서 운영” 또는 “PRC 자회사/VIE를 통해 사업 운영”처럼 좁은 문구만 `PRC_OPERATIONS` 근거로 인정한다.
- 단순 China 언급·중국산 물품 일부 구매 문장은 중국계 분류에서 제외한다.
- 근거가 있으면 `CHINA_1_0`, 없거나 원문이 차단되면 기본 연구 경로 `NASDAQ_7_0`에 두되 `issuer_region=UNVERIFIED`로 남겨 비중국 기업이라고 확정하지 않는다.
- 원문 URL·공시 접수시각·Form·문맥을 전향 원장에 고정하고, 성과표를 `profile:china_1_0`·`profile:nasdaq_7_0`으로 분리한다.
- 분류는 매수 신호가 아니며 `current_operating_region_confirmed=false`, `classification_is_buy_signal=false`, `NO_ORDERS=true`를 강제한다.
- V10 전체 회귀검사 220개와 기존 IEX 연결검사 14개 통과.
- PR #27: https://github.com/roostruth-source/luca-free-eod-research/pull/27
- PR Actions #44806173121 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44806173121
- 병합 HEAD `701ceb4` Actions #44806328010 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44806328010
- 병합 artifact `14663811751` ZIP SHA-256 `6cae8c089d39fdbfd9e57c0c8e8391243ba31bb15a4f23ecf306ecd1712a4adb`.
- PR artifact 실측 후보 41개, 주문금지 위반 0건, 전향 원장 1,746건·신규 41건·`CHAIN_CONTINUED`.
- 이번 실행은 `SEC_TICKER_MAP_HTTP_403`이라 41개 모두 `SEC_ISSUER_REGION_TEXT_UNAVAILABLE`, `issuer_region=UNVERIFIED`였고 `CHINA_1_0` 적중은 0건이었다. 기존 옛 관찰을 새 분류로 소급 수정하지 않아 성과표 독립집단은 `profile:legacy_context_missing`만 존재했다. **실제 PRC Operations 원문 적중 artifact 검증은 남아 있다.**

## 2026-11-21 성능 검증 준비도 안전장치 (CI 대기)

- 독립 신선 티커 30개와 5거래일 성숙 결과 30개는 `sample_size_gate_met`으로 분리한다.
- 표본 수가 채워져도 Corporate Action(기업행사) 가격단위 미검증, IEX 단일 시세, 실제 체결·슬리피지 미측정이 남으면 `performance_validation_ready=false`를 강제한다.
- `readiness_blockers`에 `CORPORATE_ACTION_BASIS_UNVERIFIED`, `IEX_SINGLE_FEED_REFERENCE_ONLY`, `REAL_FILL_AND_SLIPPAGE_NOT_MEASURED`를 명시한다.
- 30개 독립 티커·5거래일 30개를 만든 회귀 사례에서도 성능 검증 완료가 되지 않는 테스트를 추가했다. V10 전체 221개 통과, PR·Actions·artifact 검증이 남아 있다.

## 2026-11-20 SEC 역분할·상장통지 연결 (CI 및 live 검증 대기)

- SEC 공시 원문에서 `REVERSE_SPLIT`, `MINIMUM_BID`, `LISTING_DEFICIENCY`, `DELISTING_OR_HEARING`을 분리해 원문 URL·접수시각·문맥과 함께 고정한다.
- 발견 종목은 거래량·가격이 강해도 `HOLD_FINANCIAL_OR_LISTING_STATUS` 0점 보류한다.
- 키워드 일치는 현재 상장미달 상태, 역분할 효력일, 상장폐지 확정의 증명이 아니다. `current_status_confirmed=false`, `effective_date_confirmed=false`, `sec_clearance=false`를 강제한다.
- 원문 수집 실패·일부 문서 미검토는 안전 판정으로 바꾸지 않는다. 기존 `WATCH_ONLY / NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS`를 유지한다.
- 전향 원장과 성과표에 신호별 집단을 분리했다. 로컬 전체 테스트 통과 후 PR·Actions·실제 artifact 검증이 남아 있다.

### PR #23 CI와 실제 artifact 확인

- PR: https://github.com/roostruth-source/luca-free-eod-research/pull/23
- Actions #44693489323 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44693489323
- Artifact `14609123830` ZIP SHA-256 `0ce52fd594695b58d8e8441f340f91d84ad439cf81061b7797ad3af408dd6c8b` 일치 확인.
- `live_watchlist.json` 50행: 가격 보류 28, 종목종류 보류 14, 거래소 상장상태 보류 8. 보류 50개 전부 0점, `NO_ORDERS=true`, `buy_allowed=false`, `NOT_VALIDATED` 위반 0건.
- 전향 원장은 1,290건에서 1,340건으로 `CHAIN_CONTINUED`; 신규 50행의 `listing_action_context` 저장을 확인했다.
- 이번 실행은 `SEC_TICKER_MAP_HTTP_403`으로 50행 모두 `SEC_LISTING_TEXT_UNAVAILABLE`; 실제 역분할·상장통지 원문 적중 사례는 관찰되지 않았다. 따라서 상태는 `CI_PASSED_LIVE_SEC_TEXT_UNOBSERVED`이며 완성 기준 2는 PARTIAL을 유지한다.

## 2026-11-20 장전 Volume-First 점수 분리 (검증 대기)

- 코드: https://github.com/roostruth-source/luca-free-eod-research/commit/cabd64ddeb4f7f4ede43e02c1becf746f68c2ce9
- 회귀 테스트: https://github.com/roostruth-source/luca-free-eod-research/commit/bf2b7385c765b0755088f68814bc9395f8363b99
- 장전(PREMARKET)에서는 정규장 Volume-First 35점을 가산하지 않고 PREMARKET_VOLUME_FIRST_UNVERIFIED 위험을 남긴다.
- 상태: CI_PASSED_LIVE_PREMARKET_UNOBSERVED. HEAD `1553269`의 Actions #44563820386 성공(190+14=204 tests). 실제 artifact `14550697918`(SHA-256 `fc63a811f2d6881658cf9fb57c2fa4c07eab708b0699a662e5df12e65fa67e6a`) 다운로드 및 JSON 확인: 후보 45개, 보류 23개(범위/미검증 16, 상장상태 4, 가격 3) 모두 0점; 행별 NO_ORDERS·buy_allowed 위반 0건. 단, 이번 실제 관찰의 PREMARKET 후보는 0개이므로 장전 점수 분리의 live 검증은 아직 불가하며 COMPLETE로 표시하지 않는다.
- SEC 공식 원문 미수집; SEC_UNVERIFIED/FLOAT_UNVERIFIED 유지. main 병합·주문·배포 금지.

## 2026-11-20 최신 HEAD 실제 실행 증거

- https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44563820386 (HEAD `1553269`, push CI 성공; 전체 안전 테스트 190개 + 별도 테스트 14개 통과)
- 실제 ZIP artifact ID `14550697918`, 파일 7개, 위 SHA-256; `live_watchlist.json` 45개 중 우선 0·일반 2·근거 부족 20·보류 23. 보류 후보의 점수 0점 및 행별 주문 금지 위반 0건 확인.
- 장전(PREMARKET) 관찰 후보가 없어 장전 점수 분리는 테스트만 통과. 다음 장전 실관찰에서 별도 확인 필요.
- SEC ticker map은 `SEC_TICKER_MAP_HTTP_403`; 공식 원문 우회·추정값 사용 금지. `SEC_UNVERIFIED`/`FLOAT_UNVERIFIED` 위험을 행별 유지.
- 예측 성능 `NOT_VALIDATED`: 독립 5일 표본 부족. 이번 문서 커밋 자체의 후속 CI는 별도 확인 필요.

## 2026-11-20 장전 Screener Rank 세션 분리 (CI 및 live 검증 대기)

- 코드 커밋: https://github.com/roostruth-source/luca-free-eod-research/commit/bf343436c0f441b1c85973ef03957daf9c2413c2
- 회귀 테스트 커밋: https://github.com/roostruth-source/luca-free-eod-research/commit/86c0b2bad3097c2bc1685cd2369b35190d03547c
- PREMARKET 후보는 세션 출처가 고정되지 않은 active_volume, active_trades, gainers의 Screener Rank 가산점을 받지 않는다. PREMARKET_SCREENER_RANK_SESSION_UNVERIFIED 위험을 남긴다. REGULAR 후보의 기존 순위 가산점은 보존한다.
- 상태: PENDING_CI_AND_LIVE_ARTIFACT. 이번 변경의 전체 CI 실행 및 실제 장전 후보 관찰 결과는 아직 확인되지 않았다. 최신 성공 Actions #44626684567은 변경 전 HEAD 2e21b93 기준이므로 이 변경의 통과 근거로 쓰지 않는다.
- 안전 원칙: WATCH_ONLY / NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS; 주문·main 병합·배포 금지.

## 2026-11-20 11:19 KST 최신 HEAD CI 재검증

- 원격 HEAD `0d2bd0a8e63279a8df7a8419b3e82a03c7caeedc`에서 Actions #44652204318 (`2026-11-20T01:15:05Z`, push) **success**: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44652204318
- Job `test-and-build` #136009586575: 전체 연구 안전 테스트 **191개 OK**, 별도 테스트 **14개 OK** (총 **205개**). 보고서 생성·watchlist 수집·전향 원장 기록·주문 안전 검사·artifact 업로드 단계 모두 성공.
- Artifact `14591443219` (`luca-v10-executable-research-build`, 7개 파일, 262695 bytes, ZIP SHA-256 `ca4f9661af9c1480f9979dd3e8fc956b5d47070ab1dc4dbe2322fea6c77d3dc1`, 만료 2026-12-04) 생성 확인: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44652204318/artifacts/14591443219
- 로그의 최신 수집: `SEC_TICKER_MAP_HTTP_403`, 가격대 후보 51개 중 50개 제한(1개 제외). 1/3/5/10일 전향 평가 `mature_fresh={1:134,3:0,5:0,10:0}` 및 `ready=false`이므로 정확도 검증 불가.
- **주의**: 이번 점검은 Actions 로그와 artifact 메타데이터 검증이다. ZIP 내부의 실제 PREMARKET 후보, 종목별 0점, SEC/FLOAT 위험 필드까지 재검사하지 못했다. 장전 Screener Rank 분리는 `CI_PASSED_LIVE_PREMARKET_UNOBSERVED`로 유지하고 COMPLETE로 올리지 않는다.
- 다음 작업: 해당 artifact 내부 `live_watchlist.json`을 검사해 장전 순위 가산점 0점·세션 위험 표기·보류 0점·NO_ORDERS를 행별 검증한다. 주문·main 병합·배포 금지.

## 2026-11-20 12:12 KST 실제 ZIP 내부 검증

- Actions #44652204318의 artifact `14591443219`를 직접 다운로드하여 ZIP SHA-256 `ca4f9661af9c1480f9979dd3e8fc956b5d47070ab1dc4dbe2322fea6c77d3dc1` 일치 확인. `live_watchlist.json` 50행 전수 검사.
- 관찰 시각 `2026-11-20T01:15:13.638970Z`, 세션 `OVERNIGHT_OR_CLOSED` 50행. 보류 이유별 28개 가격 오래됨/없음, 14개 범위 밖/미확인, 8개 상장상태 위험. **50개 모두 0점**, 행별 `WATCH_ONLY=true`, `NO_ORDERS=true`, `buy_allowed=false`, `NOT_VALIDATED` 위반 0건. `SEC_UNVERIFIED`와 `FLOAT_UNVERIFIED` 각 50개.
- 범위 분류: 일반주 후보 36, ETF/ETP 제외 7, 비보통주 제외 6, 심볼 디렉터리 미매핑 1. 전체가 야간/휴장 데이터이므로 PREMARKET Screener Rank 점수 분리의 실관찰 검증은 **불가**. CI 205개 통과 사실과 분리해 `CI_PASSED_LIVE_PREMARKET_UNOBSERVED` 유지.
- 새 코드 변경 없음. 본 증거 기록 커밋 자체의 후속 Actions는 별도 검증 전까지 완료 근거로 사용 금지. SEC 403 우회·주문·main 병합·배포 금지.

## 2026-11-20 SEC 공식 URL 출처 검증 강화 (실행 검증 대기)

- 코드 커밋 `bf49420`: SEC listing-action 입력 URL을 URL parser로 분해해 HTTPS, 정확한 `www.sec.gov` 호스트, 공식 EDGAR 경로, query/fragment 부재를 확인한다. 호스트 위장과 사용자정보 삽입을 거절한다.
- 테스트 커밋 `df55445`: 위장 도메인, @userinfo, query, HTTP URL을 거부하는 회귀 사례 추가.
- 최신 전체 CI 및 live artifact는 **아직 검증되지 않았다**. 이 변경을 완료 근거로 사용하지 않는다. SEC 403을 우회하지 않고 실제 원문이 없으면 SEC_UNVERIFIED/FLOAT_UNVERIFIED를 유지한다.
- 다음 검증: 최신 HEAD의 전체 Actions 실행, artifact 내부 URL 검증 및 주문 금지 확인. 주문·main 병합·배포 금지.

## 2026-11-20 20:16 KST 검증 근거 정리

- GitHub Actions #44701607027의 artifact 메타데이터를 API에서 재확인: HEAD `8c78e3d7c4f433c6fa3540eb5e7dba960da1666f`, artifact ID `14612832950`, 이름 `luca-v10-executable-research-build`, GitHub 제공 digest `sha256:156046ec21689b34fe5c2140d4add5d7dffe3634648aeb0e5804a8508d3abfc5`, 만료 2026-12-04. https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44701607027
- 직전 실행의 ZIP 내부 전수 검사 기록: 후보 50개 모두 `OVERNIGHT_OR_CLOSED`, 가격 보류 28·범위 보류 14·상장상태 보류 8, 모두 0점; 주문 금지 위반 0. 이 항목은 **직전 실행의 검사 기록**이며 이번 실행에서 ZIP을 재다운로드해 독립 재검증한 결과는 아니다.
- 본 실행에서 `prioritize_watchlist.py`를 직접 읽어 PREMARKET 출처 불명 Screener Rank 및 정규장 Volume-First 가산점 차단, SEC listing-action 위험의 0점 보류 로직 존재를 확인했다. 이는 **코드 확인**이지 실제 PREMARKET/SEC 적중 후보의 live 검증이 아니다.
- 완성 기준 2·3·4·5·6은 계속 PARTIAL. SEC 403 및 실제 장전/역분할 적중 사례 부족을 숨기지 않는다. 본 기록 커밋 후 CI/새 artifact 검증은 아직 이뤄지지 않았다. 주문·main 병합·배포 금지.

## 2026-11-20 22:18 KST 최신 Artifact 전수검사 (장전 세션 확인)

- HEAD `ef5c9c216ddada74d9824be05db423fc1f6b3db8`, Actions #44726347007, artifact `14624785304` ZIP 직접 다운로드; SHA-256 `026db454db3711c09c3523203048d94e26aa9ceebc19569581c776698d696b17`가 GitHub digest와 일치.
- `live_watchlist.json` 수집 UTC `2026-11-20T11:17:24.267910+00:00`, 50행 전부 `PREMARKET`으로 표기. 직전 실행의 `OVERNIGHT_OR_CLOSED`와 달라졌으나, **행별 trade_fresh=false / quote_fresh=false**여서 유효한 장전 가격 관찰이 아니다. 세션 라벨만으로 장전 점수 실전 검증 완료 처리 금지.
- 보류: 오래된/없는 가격 28, 범위 밖/미확인 14, 상장상태 위험 8. 50행 모두 score=0, WATCH_ONLY=true, NO_ORDERS=true, buy_allowed=false, validation_status=NOT_VALIDATED. 위반 0건. SEC_UNVERIFIED/FLOAT_UNVERIFIED 각 50행.
- screener_groups에 active_volume/gainers 등이 존재해도 유효 장전 거래·호가가 없어 점수 가산 0. SEC source `SEC_TICKER_MAP_HTTP_403`; 실제 SEC 역분할 신호 0건. 독립 5일 표본 30개 전 prediction accuracy 미검증 유지.
- 이 문서 커밋 이후의 CI/새 artifact는 아직 별도 확인 필요. 다음 작업은 **유효한 장전 가격/호가가 있는 후보**에서 session-specific Volume-First/Screener Rank 분리의 실관찰 검증. 주문·main 병합·배포 금지.

## 2026-11-21 00:17 KST — 최신 HEAD의 실제 장전 신선도·점수 검증

- 원격 HEAD `46cfce9f22f946b93de3a7b66f401ec71df2d906`; push Actions #44743180580 **success** (모든 test-and-build 단계 성공): https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44743180580
- 실제 artifact ID `14632365404` ZIP을 다운로드하여 SHA-256 `a114ad91ffbbfffa01b3045d42f0fc86fccbfab6e21e5081e20c2e6dfac863ee`가 GitHub digest와 일치함을 독립 확인. `live_watchlist.json` 50행 검사. 관찰 UTC `2026-11-20T13:18:54.999252+00:00`, 모두 PREMARKET.
- **새로운 실관찰 근거**: `trade_fresh=true` 9행, `quote_fresh=true` 9행, 양쪽 모두 true 7행. 그중 GRAB·NOK·PLUG 3개만 `PRIORITY_3_LOW_EVIDENCE` 30점(최근 IEX 장전 체결/호가 및 좁은 스프레드); KORU·NVD·PLTD·SNXX 4개는 신선한 가격/호가에도 종목 범위 미달로 **0점 보류**. 나머지 43행도 0점. 총 47행 보류(가격 25, 범위 14, 상장상태 8), 보류의 비정상 양수 점수 0건.
- 유효 장전 일반주 3행 모두 `PREMARKET_VOLUME_FIRST_UNVERIFIED`와 `PREMARKET_SCREENER_RANK_SESSION_UNVERIFIED` 위험을 표시하고, 정규장 거래량/검색기 순위 점수를 가산하지 않음. `active_volume` 검색기 순위가 존재해도 장전 근거로 오인하지 않음. IEX 단일 거래소 자료는 SIP 전체시장 검증이 아님.
- 50행 모두 `WATCH_ONLY=true`, `NO_ORDERS=true`, `buy_allowed=false`, `validation_status=NOT_VALIDATED`; 위반 0건. `SEC_UNVERIFIED`·`FLOAT_UNVERIFIED` 각 50행, SEC ticker map HTTP 403으로 공식 검증 불가.
- `prospective_outcomes.json`: 전향 원장 1,540건, 독립 1일 성과 61개, 독립 3/5/10일 성과 각 0개. 예측 정확도 검증 금지. **장전 신선 자료 점수 분리는 실제 artifact로 관찰됐으나 완성 기준 2 전체는 SEC 원문 역분할 적중 검증 부족으로 PARTIAL 유지.**
- 이 문서 변경 커밋 이후 CI/새 artifact는 별도 확인 전까지 완료 근거로 쓰지 않는다. 주문·main 병합·배포 금지.

## 2026-11-21 성능 검증 준비도 PR #29 연구 브랜치 통합 및 실제 검증

- PR #29 `d72b195`를 **main이 아닌** `research/v10-rabbitstock-eval`에 squash 병합했다. 병합 HEAD `d239f7490d9541ebabdde9f59ce63899350410c5`.
- 병합 HEAD Actions #44828165414 성공: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44828165414 ; 모든 job 단계 성공, 실제 live artifact `14674812609` 생성.
- Artifact ZIP SHA-256 `c9605dedda825d29c2427630d3272b5a7a5ec5535bfb3dd66d05a697652abce9`가 GitHub digest와 일치. ZIP 내부 `live_watchlist.json`, `prospective_outcomes.json`, `validation_readiness.json` 직접 확인.
- 실측 후보 45개: 가격 보류 20, 범위 보류 19, 상장위험 보류 6. 보류 45개 모두 점수 0, `WATCH_ONLY=true`, `NO_ORDERS=true`, `buy_allowed=false`; `validation_status=NOT_VALIDATED` 유지.
- 전향 원장 1,835건, 독립 신선 티커 84개, 독립 5거래일 성숙 표본 0개. `sample_size_gate_met=false`, `performance_validation_ready=false`, `prediction_accuracy_verified=false` 확인. 기업행사 가격단위·IEX 단일 시세·실제 체결/슬리피지 미검증 사유가 명시됐다.
- SEC ticker map HTTP 403으로 45개 모두 공식 SEC 텍스트 확인 불가; 중국계 1.0 실측 적중 0개. 이를 정상 공시 검증이나 비중국 기업 확정으로 해석하지 않는다. 완성 기준 1~6은 여전히 PARTIAL이며 연구판 전체는 NOT_VALIDATED다.
- 이 근거를 추가한 문서 커밋 자체의 CI는 별도 확인이 필요하다. 다음 작업은 새 HEAD CI 및 artifact 확인 후 공식 SEC 원문 입력이 확보되는 경우만 역분할·희석 위험 live 적중을 검증하는 것이다.

## 2026-11-21 SEC 최종 응답 URL 검증 강화 (CI·live 확인 대기)

- 코드 커밋 `6da88b2`: `capture_sec_official_inputs.py`에서 HTTP 리다이렉트 후 `response.geturl()`을 요청한 공식 SEC URL과 정확히 비교한다. 다른 호스트 또는 다른 SEC 경로로 이동하면 `sec_capture_redirect_or_final_url_mismatch`로 실패한다.
- 회귀 테스트 커밋 `0659f78`: 정상 응답의 최종 URL을 모의 응답에 명시하고 비공식 호스트 및 다른 SEC 경로로 이동한 두 사례를 거절한다.
- 두 커밋은 연구 브랜치 전용이다. 최신 HEAD의 전체 CI·실제 live artifact가 아직 검증되지 않았으므로 **완료로 표시하지 않는다**. 이전 성공 Actions #44828311987은 변경 전 HEAD의 근거다.
- SEC HTTP 403 우회 금지. 공식 원문이 없으면 `SEC_UNVERIFIED`/`FLOAT_UNVERIFIED` 유지. `WATCH_ONLY`/`NOT_VALIDATED`/`NO_ORDERS` 유지, main 병합·주문·배포 금지.

## 2026-11-21 14:16 KST SEC 최종 URL 수정 이후 실제 결과물 재검증

- 검증 기준 HEAD: `a0cc74350401a4b11f9b1c1f4f3261d8ea793a4b` (원격 연구 브랜치와 동일, ahead/behind 0).
- 성공한 Actions: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44860326637 ; `test-and-build`의 연구 안전 테스트·보고서·관찰·전향 원장·주문 안전·업로드 단계 모두 success.
- Artifact ID `14689721990` 직접 다운로드, ZIP SHA-256 `96eaeba19a21443870eaeffeccc891ad457666469ec53218f2c4365cf1e85e39` GitHub digest와 일치. 파일 7개 포함.
- `live_watchlist.json` 45행 직접 확인: `OVERNIGHT_OR_CLOSED` 45행; 가격 오래됨/없음 보류 20, 종목 범위 제외/미검증 19, 상장상태 위험 6. 보류 45개 모두 `research_priority_score=0`; `WATCH_ONLY=true`, `NO_ORDERS=true`, `buy_allowed=false`, `validation_status=NOT_VALIDATED` 위반 0건.
- `SEC_UNVERIFIED` 및 `FLOAT_UNVERIFIED` 위험 각 45행. `source_status=SEC_TICKER_MAP_HTTP_403`; 실제 SEC 공식 문서 검증 성공으로 간주하지 않음. 장전 PREMARKET 실제 신선 시세 관찰도 0행.
- 이번 증거는 **기존 HEAD에 대한 CI·live 안전성 확인**이며 SEC 실제 적중·5거래일 독립 성과·예측 정확도 완료 근거가 아님. 이 문서 변경 커밋 자체의 후속 CI는 별도 검증 전까지 미확인으로 둔다.
- 다음 작업: 공식 SEC 입력 bundle을 확보할 수 있을 때 실제 URL·CIK·HTTP Date·UTC·SHA-256 영수증을 검증해 원문 적중 live artifact를 확인한다. 외부 차단이 지속되면 성숙 5거래일 원장과 신선한 PREMARKET 관찰을 우선 점검한다.
