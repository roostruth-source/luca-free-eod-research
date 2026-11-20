# LUCA V10 연구판 완성 체크리스트

기준일: 2026-11-19 (Asia/Seoul)

이 문서는 테스트 개수만으로 완성을 선언하지 않는다. 실제 GitHub Actions와 생성된 live artifact 근거가 있어야 `COMPLETE`로 바꾼다. 모든 단계는 `WATCH_ONLY`, `NOT_VALIDATED`, `SEC_UNVERIFIED`, `NO_ORDERS`를 유지한다.

| 번호 | 완성 기준 | 상태 | 현재 근거와 남은 일 |
|---:|---|---|---|
| 1 | NASDAQ 7.0·중국계 1.0 독립 탐지와 통합 watchlist | PARTIAL | Alpaca screener 출처 순위와 관찰시각은 원장에 고정된다. 중국계 1.0을 별도 cohort(집단)로 표시하는 live 필드는 아직 필요하다. |
| 2 | Volume-First·종목종류·역분할·상장위험 연결 | PARTIAL | Volume-First, 장전/정규장, ETF·Warrant·Unit 차단과 Nasdaq Financial Status 0점 보류는 실제 artifact로 확인됐다. Reverse Split과 개별 상장유지 통지의 live 연결은 남아 있다. |
| 3 | SEC 원문 기반 OS·Float·ATM·CB·Warrant·ELOC·등록효력·CB Reset | PARTIAL | 동결 연구 모듈은 존재하지만 현재 live watchlist와 완전히 연결되지 않았다. GitHub Actions의 SEC HTTP 403에서는 추정하지 않고 미검증 상태를 유지한다. |
| 4 | SEC 직접 수집 영수증과 50종목·72시간 제한 | PARTIAL | capture/build/validate 코드와 회귀 테스트가 있다. 최신 실제 watchlist용 공식 bundle이 Actions artifact에 들어간 실행 근거는 아직 없다. |
| 5 | 전향 원장과 1·3·5·10거래일 성과 | PARTIAL | 해시 원장, MFE/MAE/종가 성과, 중복 티커 제거, 장전·정규장 분리는 구현됐다. 독립 5거래일 표본 30개 전에는 성능 검증 완료가 아니다. |
| 6 | 아이폰용 쉬운 한국어 HTML/JSON | PARTIAL | 우선순위·이유·위험·종목 종류를 표시한다. SEC 공급위험과 상장상태의 쉬운 설명을 더 연결해야 한다. |
| 7 | 전체 CI와 실제 live artifact 안전 검증 | COMPLETE | PR #21 run 44531212641과 PR #22 run 44542213435 성공. 최신 후보 50개에서 Nasdaq `D` 4개가 모두 거래소 상태 위험으로 0점 보류됐고 위험 종목의 비정상 점수는 0건이었다. |
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

1. Reverse Split(역분할)과 상장유지 통지를 live 후보에 연결한다.
2. SEC 공식 bundle이 있을 때만 OS·Float·희석 증거를 live 후보에 붙인다.
3. 중국계 1.0 cohort를 별도 표시하고 성과표도 분리한다.
4. 독립 5거래일 표본 30개가 모이면 사전 고정 기준으로 성능을 판정한다.

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
