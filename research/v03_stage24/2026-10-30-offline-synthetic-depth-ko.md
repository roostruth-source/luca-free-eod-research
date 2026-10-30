# 루카 V0.3 — 가상 호가 수량 점검 (2026-10-30)

이번 단계는 외부 API, 주문, 실측 없이 **호가에 나온 수량보다 많이 거래했다고 가정하는 오류**를 표시합니다.

예: 매도호가 $1.05에 100주만 있다고 주장하는 자료로 1,000주를 모두 $1.05에 샀다고 계산하면 안 됩니다. 새 선택 입력 `bid_size`, `ask_size`는 각각 가상의 매수·매도 호가 수량입니다. 하나라도 빠지면 `depth_claim_missing=true`, 요청 수량이 하나라도 초과하면 `depth_claim_exceeded=true`입니다. 두 수량 모두 충분한 경우에도 `depth_claim_sufficient=true`는 **입력한 숫자끼리만 일치한다는 뜻**이며, 진짜 체결 가능성을 보증하지 않습니다.

기존 호출 `scenario(bid, ask, quantity, slippage_bps=0, halted=False)`은 그대로 작동하도록 새 인수를 뒤에 추가했습니다. 0, 음수, 문자열, 불리언, NaN 등 잘못된 수량은 거부합니다.

**한계:** 첫 호가의 수량만 비교하며 여러 가격대 호가, 취소·변경, 대기 주문, 거래 정지 사실, 실제 체결, 수수료, 실제 수익률을 검증하지 않습니다. 기존의 가상 손익 숫자는 어디까지나 가정 계산입니다. 실제 호가 자료 인증도 없습니다.

검사: `python -m unittest discover -s research/v03_stage24 -p 'test_*.py' -v`. 추가 회귀 테스트 4개를 작성했지만 실행 결과는 GitHub Actions 또는 별도 로컬 실행으로 확인해야 합니다.

**NOT_VALIDATED / SEC_UNVERIFIED / D / NO_ORDERS 유지.** 보호 브랜치·Ruleset·PR 병합·실측·시세 API·Secret·주문은 변경하지 않습니다.
