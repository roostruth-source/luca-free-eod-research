# LUCA V0.3 — third independent observation raw-evidence preparation

Date: 2026-10-29 KST

Branch: `research/v03-stage24-evidence`

Baseline commit reviewed: `ca127392328a391c8f706fc11eb2e83863f704cf`

## Existing first and second observations verified before code changes

### First observation

- Actual source run `40517830351`; durable audit run `40532482508`.
- 12 symbols, 94/168 IEX one-minute slots (55.95%), 1/12 complete, zero recorded patterns.
- The durable manifest explicitly says raw IEX bar timestamps were not archived. Raw OHLCV was also not retained. The saved counts and safety fields pass their integrity tests, but the old pattern result cannot be independently recalculated from archived first-session raw bars.

### Second observation

- Source run [`40702295695`](https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40702295695): completed success, attempt 1, push event, exact research branch, source artifact `luca-v03-second-prospective-40702295695` (artifact id `12822917104`).
- Followup run [`40719409705`](https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40719409705): completed success, followup artifact `luca-v03-second-outcomes-40719409705` (artifact id `12830120781`).
- 12 symbols, 140/168 IEX one-minute slots (83.33%), 4/12 complete, two recorded pattern symbols: ELPW at 2026-10-28 14:11 UTC and STLA at 14:13 UTC.
- Frozen T0, review totals, per-symbol timestamp evidence, HTTP GET provenance, two-session coverage and D-grade safety fields agree. The source evidence explicitly records `raw_ohlcv_archived=false`; only timestamps and calculated pattern summaries survived. Therefore the two recorded patterns cannot be independently recalculated from the second artifact alone.

No first- or second-observation file was edited.

## Future raw evidence added

The unchanged detector remains `iex_1min_research.find_patterns`. Its file was not modified.

Every future review now additionally writes immutable `iex_raw_ohlcv_evidence.json` from the same in-memory bars used for `forward_review.json`; there is no second market-data request. The archive contains:

- every frozen symbol in original order, including zero-bar and no-signal symbols;
- canonical IEX 1-minute `t/o/h/l/c/v` values with `adjustment=raw`;
- every missing expected minute and an explicit unknown-cause marker;
- an honest per-symbol status: signal recorded, no signal in evaluable windows, no six-minute window, or no IEX bars;
- every signal timestamp, knowable-after timestamp and the exact six OHLCV bars used by the unchanged formula;
- hashes binding the frozen T0, old review, timestamp provenance, raw evidence and exact detector source code;
- D / SEC_UNVERIFIED / NOT_VALIDATED / NO_ORDERS safety fields.

The archive does not claim to retain raw HTTP response bytes. It retains the validated canonical OHLCV fields required for deterministic recalculation.

## Replay and tamper checks

`iex_raw_evidence.py` reconstructs the symbol-to-bars input only from the raw archive, calls the unchanged review and detector, and compares the recalculated result to the separately saved old review. Replay fails closed for:

- changed OHLCV or archive hash;
- a rehashed but changed price;
- changed old review or timestamp provenance;
- changed detector source identity;
- changed frozen universe;
- unsafe grade, SEC, validation, order or trade flags;
- duplicate/malformed/out-of-window bars.

Example after an approved future observation:

```bash
python research/v03_stage24/iex_raw_evidence.py \
  --frozen <artifact>/frozen_t0.json \
  --review <artifact>/forward_review.json \
  --timestamps <artifact>/iex_timestamp_provenance.json \
  --raw-evidence <artifact>/iex_raw_ohlcv_evidence.json
```

## Test result

- Before change: 465/465 existing offline tests passed.
- After change: 477/477 offline tests passed.
- Python compile check passed.
- No test contacted the market or placed an order; new replay fixtures are synthetic and are never described as actual observations.

## Changed files

- `research/v03_stage24/iex_raw_evidence.py` — new immutable OHLCV archive and replay verifier.
- `research/v03_stage24/test_iex_raw_evidence.py` — new archive, replay, tamper, missing-data and safety tests.
- `research/v03_stage24/iex_provenance_adapter.py` — exposes the already fetched validated bars to the archive without another request; original two-result interface remains compatible.
- `research/v03_stage24/future_iex_review.py` — writes the third immutable file atomically with review and timestamp evidence.
- `research/v03_stage24/test_future_iex_review.py` — verifies all three evidence files, empty bars and no partial output.
- `research/v03_stage24/test_second_source_end_to_end_offline.py` — verifies workflow entrypoints create safe replayable raw evidence.
- This report.

## Scope and safety confirmation

- `main` untouched.
- `/api/radar`, website and production paths untouched.
- Existing workflow, schedule, automation and alert files untouched.
- First and second observation data untouched.
- No third observation request, execution or approval created.
- No orders, trading approval or synthetic-to-real relabeling.
- `NOT_VALIDATED / NO_ORDERS / SEC_UNVERIFIED / D` preserved.
