# 나만의 용돈 기입장

Python 표준 라이브러리만 사용한 JSONL 파일 기반 콘솔 가계부입니다. 거래 CRUD,
검색, 월별 요약, 예산, 카테고리, CSV 가져오기/내보내기를 지원합니다.

## 실행 환경

- Python 3.10 이상
- 외부 패키지 설치 불필요
- 프로젝트 루트에서 명령 실행

```bash
python -m budget_app --help
```

저장 위치를 바꾸려면 **하위 명령 앞**에 `--data-dir`을 지정합니다.

```bash
python -m budget_app --data-dir ./my_data category list
```

## 주요 명령

### 1. 거래 추가

`add`는 과제 요구대로 대화형으로 입력합니다.

```bash
python -m budget_app add
```

입력 순서: 날짜 → 타입 → 카테고리 → 금액 → 메모 → 태그

### 2. 목록과 검색

```bash
python -m budget_app list --limit 10
python -m budget_app search --from 2026-07-01 --to 2026-07-31
python -m budget_app search --category food --type expense --q 점심 --tag meal
```

목록과 검색은 날짜 최신순입니다. `transactions.jsonl`을 통째로 읽지 않고,
파일 끝에서부터 한 줄씩 읽는 제너레이터로 처리합니다.

### 3. 월별 요약과 예산

```bash
python -m budget_app budget set --month 2026-07 --amount 500000
python -m budget_app budget get --month 2026-07
python -m budget_app summary --month 2026-07 --top 3
```

요약에는 총수입, 총지출, 잔액, 지출 카테고리 TOP N이 표시됩니다. 예산이
있으면 사용률을 보여 주고, 지출이 예산보다 크면 경고합니다.

### 4. 카테고리 관리

```bash
python -m budget_app category list
python -m budget_app category add health
python -m budget_app category remove health
```

최초 실행 시 `food`, `transport`, `housing`, `salary`, `etc`가 자동으로
생성됩니다. 거래에서 사용 중인 카테고리는 삭제할 수 없습니다.

### 5. 거래 수정과 삭제

수정 방식은 **옵션 기반**으로 고정했습니다.

```bash
python -m budget_app update --id TX-XXXXXXXXXXXX --amount 18000 --memo "저녁"
python -m budget_app delete --id TX-XXXXXXXXXXXX
```

수정 가능 옵션은 `--date`, `--type`, `--category`, `--amount`, `--memo`,
`--tags`입니다. 수정·삭제는 임시 파일에 쓴 뒤 `os.replace()`로 원자적으로
교체합니다.

### 6. CSV 가져오기와 내보내기

```bash
python -m budget_app import --from sample_import.csv
python -m budget_app export --out july.csv --month 2026-07
python -m budget_app export --out range.csv --from 2026-07-01 --to 2026-07-15
```

내보내기는 `--month` 또는 `--from`과 `--to`를 함께 지정해야 합니다.
가져오기에서 정상 행은 등록하고, 검증에 실패한 행은 건너뛴 뒤 처리 건수를
출력합니다. 파일이 없거나 헤더가 잘못된 경우에는 전체 작업을 오류로 종료합니다.

CSV는 UTF-8(BOM 허용), 헤더 포함이며 다음 스키마를 사용합니다.

| 열 | 필수 | 형식 |
|---|---:|---|
| `date` | Y | `YYYY-MM-DD` |
| `type` | Y | `income` 또는 `expense` |
| `category` | Y | 등록된 카테고리 |
| `amount` | Y | 양수 정수 |
| `memo` | N | 문자열 |
| `tags` | N | 쉼표로 구분한 문자열 |

## 저장 파일

기본 저장 폴더는 `./data`이며 첫 실행 때 자동 생성됩니다.

| 파일 | 내용 | 형식 |
|---|---|---|
| `transactions.jsonl` | 거래 내역 | JSON 객체 1개/줄 |
| `categories.jsonl` | 카테고리 | JSON 객체 1개/줄 |
| `budgets.jsonl` | 월 예산 | JSON 객체 1개/줄 |
| `app.log` | 명령 성공/실패 및 실행 시간 | 탭 구분 로그 |

거래 예시:

```json
{"id":"TX-ABC123DEF456","type":"expense","date":"2026-07-03","amount":12000,"category":"food","memo":"점심","tags":["meal","work"]}
```

## 오류와 종료 코드

- 정상: `0`
- 예상하지 못한 내부 오류: `1`
- 입력/업무 규칙 오류: `2`
- 파일 처리 오류: `3`
- 사용자가 `Ctrl+C`로 취소: `130`

사용자 오류에서는 스택트레이스를 표시하지 않고 `[오류]`와 `[힌트]`를
출력합니다. 명령 문법 자체가 잘못된 경우에는 `argparse` 표준 오류 코드 `2`를
사용합니다.

## 테스트

```bash
python -m unittest discover -v
```

테스트는 임시 폴더만 사용하며 실제 `./data`를 변경하지 않습니다.

## 프로젝트 구조

```text
budget_app/
├── __main__.py       # python -m 진입점
├── cli.py            # 명령 파싱과 출력
├── models.py         # dataclass와 검증
├── repositories.py   # JSONL I/O, 제너레이터, 원자적 저장
├── services.py       # CRUD, 검색, 요약, CSV 업무 규칙
└── decorators.py     # 실행 로그/시간 측정 데코레이터
tests/
└── test_budget_app.py
sample_import.csv
REPORT.md
```
