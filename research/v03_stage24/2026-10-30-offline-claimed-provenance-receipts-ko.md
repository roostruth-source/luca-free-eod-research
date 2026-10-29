# 루카 V0.3 — 오프라인 원본 출처·수집 시각 영수증 검사 (2026-10-30)

## 왜 필요한가요?
서로 다른 날짜의 주가 자료를 제출했더라도 **언제, 어디서 수집했다고 주장하는지**와 파일의 디지털 지문(해시값)이 맞는지 확인해야 합니다. 이를 위해 기존 `offline_multisession_audit.audit_session_bundle` 위에 **선택형 보조 검사** `offline_archive_provenance.audit_claimed_receipts`를 추가했습니다. 기존 연구·실측 코드는 건드리지 않습니다.

## 쉬운 말로
- **원본 해시**: 파일 내용의 디지털 지문. 한 글자라도 바뀌면 달라집니다.
- **봉인 해시**: 연구를 시작하기로 정한 시각과 종목 명단의 디지털 지문.
- **수집 영수증**: 자료를 어디에서, 언제 가져왔다고 *기록한* 메모. **진짜로 그때 수집했다는 증명서는 아닙니다.**
- **1분봉**: 1분 동안의 가격 기록. 10:05 봉은 보통 10:05에 시작하므로 10:06 전에 완성된 봉이라고 주장하면 모순입니다.

## 검사하는 내용
각 날짜에 대해 영수증 1개가 있어야 하며 다음 필드를 확인합니다.
`session_day_ny`, `observation_id`, `capture_id`, `source_label`, `source_kind`, `raw_content_sha256`, `commitment_sha256`, `claimed_commitment_recorded_at_utc`, `claimed_raw_captured_at_utc`와 모든 안전 상태 필드.

- 제출한 원본/봉인의 해시와 영수증 해시가 정확히 같은지 검사합니다.
- 같은 수집 ID를 다른 날짜에 다시 쓰거나 날짜별 영수증이 빠지면 거부합니다.
- 수집 시각과 봉인 기록 시각은 UTC 시간대가 명시돼야 합니다. 시간대가 빠지거나 UTC가 아니면 거부합니다.
- 봉인 기록 시각이 기준 시각보다 **늦다고 주장하면** 거부합니다.
- 원본 수집 시각이 기준 시각보다 이르거나 마지막 1분봉 종료 시각보다 빠르다고 주장하면 거부합니다.
- 가격 봉이 0개라면 출처 영수증이 있어도 **가격 증거가 없다**고 경고합니다.
- 기준 시각 **이후** 가격 봉이 있다면 결과 확인용 자료일 수 있지만, 기준 시각에 이미 알았던 신호의 증거로 쓰면 안 된다고 경고합니다.
- 출처 종류는 `SYNTHETIC`(가상 시험) 또는 `UNVERIFIED_ARCHIVE`(미검증 보관본)만 허용합니다.
- 외부에서 검증했다고 주장하는 플래그는 받지 않습니다. 검증 결과는 언제나 `false`입니다.

## 사용 예시
```python
from offline_archive_provenance import audit_claimed_receipts

report = audit_claimed_receipts(
    sessions=[{"session_day_ny": "2026-10-29", "raw": raw_day1, "manifest": manifest_day1}],
    receipts=[{
        "session_day_ny": "2026-10-29",
        "observation_id": "synthetic-day-1",
        "capture_id": "synthetic-capture-1",
        "source_label": "test-only",
        "source_kind": "SYNTHETIC",
        "raw_content_sha256": "<기존 감사에서 계산한 원본 해시>",
        "commitment_sha256": "<기존 봉인 해시>",
        "claimed_commitment_recorded_at_utc": "2026-10-29T14:04:00+00:00",
        "claimed_raw_captured_at_utc": "2026-10-29T14:40:00+00:00",
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "source_externally_verified": False,
        "timestamps_externally_verified": False
    }]
)
```
예시 시각·해시·자료는 **실제 거래 증거가 아닙니다**. 실제 호출에서는 각 자료의 마지막 봉 종료 시각과 일치해야 합니다.

## 중요한 한계
해시와 시간 기록이 서로 맞아도 사람이 가짜 데이터를 만들어 해시와 영수증을 함께 계산할 수 있습니다. **독립적인 수집 시각 증명, 외부 데이터 제공자의 원본 응답, 공식 개장 확인, SEC 검증, 실전 체결 가능성**은 이번에 확인하지 않았습니다. 여러 날짜의 기록을 독립 표본으로 계산하거나 예측 승률을 주장하지 않습니다. 기존 3차 실측·실시간 시세 API·Secret·주문·보호 브랜치·Ruleset은 변경하지 않습니다.

## 회귀 검사
```bash
python -m unittest discover -s research/v03_stage24 -p 'test_*.py' -v
```
안전 상태: `NOT_VALIDATED / SEC_UNVERIFIED / D / NO_ORDERS`.
