# LUCA V10 연구판 완성 체크리스트

기준일: 2026-11-19 (Asia/Seoul)

이 문서는 테스트 개수만으로 완성을 선언하지 않는다. 실제 GitHub Actions와 생성된 live artifact 근거가 있어야 `COMPLETE`로 바꾼다. 모든 단계는 `WATCH_ONLY`, `NOT_VALIDATED`, `SEC_UNVERIFIED`, `NO_ORDERS`를 유지한다.

| 번호 | 완성 기준 | 상태 | 현재 근거와 남은 일 |
|---:|---|---|---|
| 1 | NASDAQ 7.0·중국계 1.0 독립 탐지와 통합 watchlist | PARTIAL | Alpaca screener 출처 순위와 관찰시각은 원장에 고정된다. 중국계 1.0을 별도 cohort(집단)로 표시하는 live 필드는 아직 필요하다. |
| 2 | Volume-First·종목종류·역분할·상장위험 연결 | PARTIAL | Volume-First, 장전/정규장, ETF·Warrant·Unit 차단은 구현됐다. Nasdaq Financial Status 연결은 현재 개발 중이다. Reverse Split과 개별 상장유지 통지의 live 연결은 남아 있다. |
| 3 | SEC 원문 기반 OS·Float·ATM·CB·Warrant·ELOC·등록효력·CB Reset | PARTIAL | 동결 연구 모듈은 존재하지만 현재 live watchlist와 완전히 연결되지 않았다. GitHub Actions의 SEC HTTP 403에서는 추정하지 않고 미검증 상태를 유지한다. |
| 4 | SEC 직접 수집 영수증과 50종목·72시간 제한 | PARTIAL | capture/build/validate 코드와 회귀 테스트가 있다. 최신 실제 watchlist용 공식 bundle이 Actions artifact에 들어간 실행 근거는 아직 없다. |
| 5 | 전향 원장과 1·3·5·10거래일 성과 | PARTIAL | 해시 원장, MFE/MAE/종가 성과, 중복 티커 제거, 장전·정규장 분리는 구현됐다. 독립 5거래일 표본 30개 전에는 성능 검증 완료가 아니다. |
| 6 | 아이폰용 쉬운 한국어 HTML/JSON | PARTIAL | 우선순위·이유·위험·종목 종류를 표시한다. SEC 공급위험과 상장상태의 쉬운 설명을 더 연결해야 한다. |
| 7 | 전체 CI와 실제 live artifact 안전 검증 | COMPLETE | PR #21 Actions run 44531212641 성공. 후보 50개 중 장전 신선 6개, 범위 밖 16개 0점, 오래된 가격 32개 0점, 범위 밖/오래된 자료의 비정상 점수 0건을 확인했다. |
| 8 | 주문 금지 안전 상태 | COMPLETE | 실제 artifact와 테스트에서 WATCH_ONLY·NOT_VALIDATED·NO_ORDERS가 유지된다. 자동매수·주문 endpoint는 없다. |
| 9 | 체크리스트와 근거 지속 갱신 | ACTIVE | 이 파일을 매 작업 후 커밋·Actions·artifact 근거와 함께 갱신한다. |
| 10 | 최종 회귀검사·완성 보고·자동화 정지 | PENDING | 1~9의 필수 항목과 외부차단 설명이 끝난 뒤 수행한다. main 병합과 배포는 별도 승인 대상이다. |

## 현재 검증 근거

- 장전 가격 문맥 PR: https://github.com/roostruth-source/luca-free-eod-research/pull/21
- 실제 성공 실행: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/44531212641
- 연구 브랜치 기준 커밋: `e0fe84af8ddb4b0a1f2f688160aedb3d35527335`

## 다음 순서

1. Nasdaq `Financial Status` 위험을 점수·원장·모바일 보고서에 연결한다.
2. Reverse Split(역분할)과 상장유지 통지를 live 후보에 연결한다.
3. SEC 공식 bundle이 있을 때만 OS·Float·희석 증거를 live 후보에 붙인다.
4. 중국계 1.0 cohort를 별도 표시하고 성과표도 분리한다.
5. 독립 5거래일 표본 30개가 모이면 사전 고정 기준으로 성능을 판정한다.
