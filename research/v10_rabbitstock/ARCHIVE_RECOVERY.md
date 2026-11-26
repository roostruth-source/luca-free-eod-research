# LUCA V10 결과 묶음 보관·복구 절차

이 절차는 관찰 결과를 나중에 원본 그대로 확인하기 위한 것이다. 매수·매도 주문과는 관계없으며 항상 `WATCH_ONLY / NOT_VALIDATED / SEC_UNVERIFIED / D / NO_ORDERS` 상태를 유지한다.

## 결과 묶음이 하는 일

수동 일일 관찰이 성공하면 JSON·HTML 결과 9개를 `luca_v10_archive_bundle.zip` 한 파일로 묶는다. 묶음 안의 `manifest.json`에는 각 파일의 SHA-256 지문(파일이 한 글자라도 바뀌면 달라지는 확인값), 크기, 실행 커밋, Actions 실행 번호, 원장 건수와 마지막 해시가 들어간다.

묶음을 만들 때와 다시 열 때 다음을 모두 검사한다.

- 필수 결과 9개가 빠짐없이 있고 다른 파일이 끼지 않았는지
- `WATCH_ONLY`, `NOT_VALIDATED`, `NO_ORDERS`가 유지되는지
- 주문 허용 표시나 검증 완료 주장이 들어오지 않았는지
- 전향 원장의 건수와 해시 연결이 맞는지
- 압축파일 경로 조작, 중복 파일, 과도한 크기가 없는지
- 모든 원본 파일의 SHA-256 지문이 manifest와 같은지

## 내려받은 묶음 확인

저장소 루트에서 다음처럼 실행한다.

```bash
cd research/v10_rabbitstock
python archive_bundle.py verify /안전한/보관경로/luca_v10_archive_bundle.zip
```

`"verified": true`와 SHA-256 값이 출력돼야 한다. 실패한 파일은 정상 자료로 사용하지 말고, 원본 Actions 실행 번호와 오류 내용을 함께 보존한다.

## 새 폴더로 복구

복구 대상 폴더는 미리 존재하면 안 된다. 기존 증거를 덮어쓰지 않기 위한 안전장치다.

```bash
python archive_bundle.py recover /안전한/보관경로/luca_v10_archive_bundle.zip \
  --output-dir /안전한/새폴더/run-12345-recovered
```

복구 뒤에도 먼저 `verify` 결과와 SHA-256 값을 기록한다. `manifest.json`과 원본 결과 9개가 읽기 전용 파일로 나온다.

## Actions 보관 실패 때 복구 순서

1. 같은 실행에서 내려받아 둔 `luca_v10_archive_bundle.zip`을 찾는다.
2. `verify`로 지문·원장 연결·안전표시를 확인한다.
3. 새 빈 경로에만 `recover`한다. 기존 1·2차 또는 이전 V10 자료 위에 풀지 않는다.
4. 실행 URL, 실행 번호, 커밋, ZIP SHA-256, 검증시각, 오류 원인을 별도 사고기록에 남긴다.
5. 검증이 실패하면 일부 JSON이 보여도 연속 원장으로 사용하지 않는다.
6. 정상 묶음이 하나도 없으면 `PREVIOUS_SUCCESS_ARTIFACT_UNAVAILABLE`로 다음 관찰을 차단한다. 빈 원장을 새로 시작해 성공처럼 보고하지 않는다.

## 현재 한계와 장기 보관

GitHub Actions artifact는 현재 90일 보관이다. 이번 기능은 그 안의 파일을 검증 가능한 한 묶음으로 만들지만, 90일 밖의 저장소로 자동 복사하지는 않는다. 영구 보관을 자동화하려면 별도 archive 브랜치 또는 GitHub Release 중 하나를 정하고, 연구 워크플로에 최소 범위의 쓰기 권한을 주는 별도 승인이 필요하다.

승인 전에는 사용자가 성공 실행 직후 ZIP을 내려받아 두 곳 이상에 보관하고, 두 사본의 SHA-256이 같은지 확인하는 방식이 가장 안전하다. 이 수동 보관도 실제 시세 정확성이나 수익성을 검증해 주는 것은 아니다.
