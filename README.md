# 나만의 용돈 기입장

Python 표준 라이브러리만 사용한 JSONL 파일 기반 콘솔 가계부입니다. 거래 CRUD,
검색, 월별 요약, 예산, 카테고리, CSV 가져오기/내보내기를 지원합니다.

이 문서는 과제 설명, 요구사항 충족 여부, 설계 근거, 실행 방법, 시연 절차와
검증 결과를 모두 포함합니다. 평가자는 이 README만으로 프로그램을 실행하고
구현 내용을 확인할 수 있습니다.

## 과제 목적

단순히 거래를 저장하는 프로그램이 아니라, 프로그램 종료 후에도 데이터가
유지되고 예외 상황에서도 데이터를 안전하게 관리할 수 있는 “작은 서비스”를
구현하는 것이 목적입니다. 다음 Python 개념을 실제 프로그램에 적용했습니다.

- JSONL 파일을 이용한 영구 저장과 CRUD
- 모델·저장소·서비스·CLI의 책임 분리
- `yield` 기반 제너레이터 스트리밍
- 데코레이터를 이용한 공통 관심사 분리
- `dataclass`와 타입 힌트를 이용한 데이터 계약
- 입력 검증, 사용자 친화적 오류와 비정상 종료 코드

## 요구사항 충족표

| PDF 요구사항 | 구현 내용 | 확인 위치/명령 |
|---|---|---|
| 거래 추가 | 날짜·타입·카테고리·금액 검증 및 재입력, id 자동 생성 | `python -m budget_app add` |
| 최신순 목록 | 날짜 최신순, `--limit`, 역방향 파일 제너레이터 | `list --limit 10`, `repositories.py` |
| 조건 검색 | 기간·카테고리·타입·메모·태그 검색 | `search --help` |
| 월별 요약 | 총수입·총지출·잔액·지출 TOP N | `summary --month 2026-07 --top 3` |
| 예산 | 월 예산 영구 저장, 사용률과 초과 경고 | `budget set/get` |
| 카테고리 | 추가·목록·삭제, 사용 중인 카테고리 삭제 차단 | `category add/list/remove` |
| 거래 수정 | id 기반 옵션 방식, 없는 id 처리 | `update --help` |
| 거래 삭제 | id 기반 삭제, 없는 id 처리 | `delete --id ID` |
| CSV 가져오기 | 정상 행 등록, 오류 행 건너뜀, 처리 건수 출력 | `import --from sample_import.csv` |
| CSV 내보내기 | 월 또는 기간 조건, UTF-8 CSV 생성 | `export --help` |
| 3개 이상 저장 파일 | 거래·카테고리·예산 JSONL 분리 | `data/` |
| 데이터 모델 | `Transaction` dataclass와 검증 함수 | `models.py` |
| 2개 이상 클래스 | 모델, 저장소, 스토어, 서비스 등 사용 | `budget_app/` |
| 3개 이상 모듈 | 모델·저장소·서비스·CLI·데코레이터 분리 | `budget_app/` |
| 제너레이터 | 거래 파일을 한 줄씩 정방향/역방향 처리 | `repositories.py` |
| 데코레이터 | 성공·실패·실행 시간 로그 기록 | `decorators.py`, `data/app.log` |
| 타입 힌트 | 함수 인자·반환값과 데이터 구조에 적용 | 전체 Python 코드 |
| 오류 처리 | 오류·힌트 출력, 스택트레이스 미노출, 비정상 종료 | 잘못된 id/날짜로 확인 |
| 표준 라이브러리 | 외부 패키지 없이 Python 3.10 이상에서 실행 | 설치 과정 없음 |

## 실행 환경

- Python 3.10 이상
- 외부 패키지 설치 불필요
- 프로젝트 루트에서 명령 실행

Windows PowerShell 기준:

```powershell
cd "C:\Users\user\Desktop\2026\2-1"
python --version
```

```bash
python -m budget_app --help
```

저장 위치를 바꾸려면 **하위 명령 앞**에 `--data-dir`을 지정합니다.

```bash
python -m budget_app --data-dir ./my_data category list
```

`--data-dir`은 반드시 하위 명령보다 앞에 작성합니다. 같은 데이터를 계속
사용하려면 모든 명령에서 같은 저장 폴더를 지정해야 합니다.

## 설계와 동작 구조

```text
사용자
  │
  ▼
cli.py ── 명령 분석, 대화형 입력, 출력
  │
  ▼
services.py ── CRUD, 검색, 요약, 예산, CSV 업무 규칙
  │
  ▼
repositories.py ── JSONL 스트리밍, 원자적 파일 저장
  │
  ├── transactions.jsonl
  ├── categories.jsonl
  └── budgets.jsonl
```

- `models.py`: `Transaction` dataclass, 검색 조건, 날짜·금액·타입 검증
- `repositories.py`: 저장 파일 생성, 제너레이터 읽기, 임시 파일 교체
- `services.py`: 카테고리 규칙, CRUD, 검색, 통계, CSV 처리
- `cli.py`: `argparse` 명령과 사용자 화면
- `decorators.py`: 명령 실행 성공·실패와 소요 시간 기록
- `__main__.py`: `python -m budget_app` 진입점

### 제너레이터 스트리밍

`transactions.jsonl`은 날짜 오름차순으로 유지합니다. 최신순 목록과 검색에서는
파일 마지막 부분부터 일정 크기의 바이트 블록을 읽고 각 거래를 `yield`합니다.
따라서 거래 파일 전체를 한 번에 메모리에 올리지 않습니다.

```python
def iter_all(self, newest_first: bool = False) -> Iterator[Transaction]:
    ...
    for line in line_iterator:
        yield Transaction.from_dict(json.loads(line))
```

### 데이터 저장 안전성

수정·삭제처럼 기존 파일을 다시 작성하는 작업은 원본을 바로 덮어쓰지 않습니다.
같은 폴더에 임시 파일을 작성하고 `flush()`와 `fsync()`가 끝난 후
`os.replace()`로 교체합니다. 처리 중 오류가 발생했을 때 원본이 일부만
기록되는 위험을 줄이기 위한 방식입니다.

### 데코레이터

`@log_execution`을 CLI 실행 함수에 적용했습니다. 기능마다 로그 코드를
반복하지 않고 명령 실행 시각, 성공/실패와 실행 시간을 `data/app.log`에
기록합니다.

### 입력 검증

- 날짜: `YYYY-MM-DD` 형식의 실제 존재하는 날짜
- 타입: `income` 또는 `expense`
- 금액: 0보다 큰 정수
- 카테고리: 등록된 카테고리
- 월: `YYYY-MM`
- 검색 기간: 시작일이 종료일보다 빠르거나 같아야 함
- 수정·삭제: 실제 존재하는 거래 id

`add`에서 잘못된 날짜·타입·카테고리·금액을 입력하면 명령을 바로 종료하지
않고 오류 원인과 힌트를 보여 준 뒤 해당 값을 다시 입력받습니다. `-add`처럼
명령 형식이 잘못된 경우에는 `FriendlyArgumentParser`가 올바른 명령 예시와
`--help` 사용법을 출력하고 종료 코드 2를 반환합니다.

## 주요 명령

### 1. 거래 추가

`add`는 과제 요구대로 대화형으로 입력합니다.

```bash
python -m budget_app add
```

입력 순서: 날짜 → 타입 → 카테고리 → 금액 → 메모 → 태그

입력 예:

```text
날짜 (YYYY-MM-DD): 2026-07-29
타입 (income/expense): expense
카테고리: food
금액 (양수 정수): 15000
메모 (선택): 점심
태그 (쉼표 구분, 선택): meal,work
[저장 완료] id=TX-XXXXXXXXXXXX
```

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

오류 확인 예:

```bash
python -m budget_app delete --id NO-ID
```

```text
[오류] 거래를 찾을 수 없습니다: NO-ID
[힌트] list 또는 search 명령으로 id를 확인하세요.
```

PowerShell에서는 `$LASTEXITCODE`로 종료 코드를 확인할 수 있습니다.

## 평가용 전체 시연 순서

기존 데이터에 영향을 주지 않도록 별도 평가 폴더를 사용하는 예입니다.

```powershell
# 1. 도움말과 최초 초기화
python -m budget_app --help
python -m budget_app --data-dir ./evaluation_data category list

# 2. 예제 거래 3건 가져오기
python -m budget_app --data-dir ./evaluation_data import --from sample_import.csv

# 3. 목록과 조건 검색
python -m budget_app --data-dir ./evaluation_data list --limit 5
python -m budget_app --data-dir ./evaluation_data search --category food --type expense
python -m budget_app --data-dir ./evaluation_data search --from 2026-07-01 --to 2026-07-31

# 4. 예산과 월 요약
python -m budget_app --data-dir ./evaluation_data budget set --month 2026-07 --amount 50000
python -m budget_app --data-dir ./evaluation_data summary --month 2026-07 --top 3

# 5. CSV 내보내기
python -m budget_app --data-dir ./evaluation_data export --out evaluation_result.csv --month 2026-07

# 6. 오류 처리
python -m budget_app --data-dir ./evaluation_data delete --id NO-ID
$LASTEXITCODE

# 7. 자동 테스트
python -m unittest discover -v
```

예제 CSV 3건을 가져온 뒤 예산을 50,000원으로 설정하면 요약의 핵심 결과는
다음과 같습니다.

```text
총 수입: 3,000,000원
총 지출: 67,000원
잔액: 2,933,000원
예산: 50,000원 (사용률 134.0%)
[경고] 월 예산을 초과했습니다!
```

## 테스트

```bash
python -m unittest discover -v
```

테스트는 임시 폴더만 사용하며 실제 `./data`를 변경하지 않습니다.

검증 항목:

1. 거래·카테고리·예산 파일 자동 생성
2. 거래 추가·최신순 목록·검색·수정·삭제
3. 월별 합계와 예산 초과 판단
4. 사용 중인 카테고리 삭제 차단
5. 잘못된 날짜와 금액 거부
6. CSV 가져오기와 내보내기
7. 거래 파일 날짜 정렬
8. 사용자 오류의 비정상 종료와 스택트레이스 미출력
9. 잘못된 명령의 오류·힌트와 종료 코드 2
10. 대화형 거래 추가의 잘못된 값 재입력

최종 검증 결과:

```text
Ran 10 tests in 1.022s
OK
```

## 요구사항 해석과 선택 근거

PDF에서 선택하거나 해석해야 하는 부분은 다음과 같이 결정했습니다.

1. 긴 옵션은 설명과 전체 예시에 맞춰 `--limit`, `--from`처럼 `--`로 통일했습니다.
2. `update`는 허용된 두 방식 중 자동화하기 쉬운 옵션 방식을 선택했습니다.
3. 초기 카테고리는 안 A인 기본 카테고리 자동 생성을 선택했습니다.
4. 필수 모델에 생성 시각이 없으므로 “최신순”은 거래 날짜 내림차순으로
   정의했습니다. 날짜가 같으면 id 순서로 결과를 일정하게 유지합니다.
5. CSV 가져오기에서 유효한 행은 저장하고 잘못된 행은 `skipped`로 집계합니다.
   파일 부재 또는 필수 헤더 누락은 전체 오류로 처리합니다.
6. 추가 과제인 백업과 반복 거래 기능은 구현하지 않았습니다. 원자적 파일
   교체는 필수 요구사항의 데이터 안전성 권장 사항이기도 하므로 적용했습니다.

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

## 평가 시 핵심 설명

- JSONL을 선택한 이유: 한 줄이 한 거래여서 스트리밍하기 쉽고 태그 목록을
  자연스럽게 저장할 수 있습니다.
- 모듈을 분리한 이유: 화면, 업무 규칙, 저장 방식의 변경 영향을 줄이고 각
  계층을 독립적으로 테스트하기 위해서입니다.
- 제너레이터를 사용한 이유: 거래 수가 많아져도 전체 파일 크기만큼 메모리를
  사용하지 않기 위해서입니다.
- 데코레이터를 사용한 이유: 로그와 시간 측정이라는 공통 코드를 핵심 기능과
  분리하기 위해서입니다.
- 원자적 교체를 사용한 이유: 수정·삭제 도중 실패해 원본 파일이 부분적으로
  기록되는 위험을 줄이기 위해서입니다.
- 타입 힌트를 사용한 이유: 함수의 입력과 출력 계약을 명확하게 하고 유지보수와
  자동완성을 돕기 위해서입니다.

이 프로젝트는 PDF의 필수 기능을 대상으로 구현했으며 선택형 추가 과제는
평가 범위에 포함하지 않았습니다.

## 평가 발표 진행 방법

평가 문항에는 기능 이름만 나열하지 않고 다음 순서로 답한다.

> 결론 → 구현 방법 → 선택 이유 → 코드 또는 실행 결과

평가 시작 시에는 다음과 같이 프로젝트 전체를 먼저 소개한다.

> 이 프로그램은 JSONL 파일에 데이터를 영구 저장하는 콘솔 가계부입니다.
> 거래 추가·조회·검색·수정·삭제, 월별 요약, 예산, 카테고리와 CSV
> 가져오기·내보내기를 구현했습니다. 기능 동작뿐 아니라 데이터 안전성,
> 모듈 구조, 제너레이터 스트리밍, 데코레이터와 타입 힌트를 중심으로
> 설명하겠습니다.

### 권장 설명 순서

1. `--help`로 구현한 명령과 옵션을 보여 준다.
2. 샘플 CSV를 가져와 영구 저장과 CSV 스키마를 확인한다.
3. `list`와 `search`로 최신순 조회와 제너레이터 스트리밍을 설명한다.
4. `budget set`과 `summary`로 예산 사용률과 초과 경고를 확인한다.
5. 모듈·클래스의 책임과 update/delete의 원자적 파일 교체를 설명한다.
6. 존재하지 않는 id를 삭제해 오류 메시지·힌트·종료 코드를 확인한다.
7. 테스트를 실행해 핵심 기능의 검증 결과를 보여 준다.

### 평가용 시연 명령

기존 데이터와 섞이지 않도록 별도 `evaluation_data` 폴더를 사용한다.

```powershell
# 자동 테스트
python -m unittest discover -v

# 명령과 옵션 확인
python -m budget_app --help

# 초기 파일 생성 및 카테고리 확인
python -m budget_app --data-dir ./evaluation_data category list

# CSV 가져오기와 영구 저장
python -m budget_app --data-dir ./evaluation_data import --from sample_import.csv

# 최신순 목록과 조건 검색
python -m budget_app --data-dir ./evaluation_data list --limit 3
python -m budget_app --data-dir ./evaluation_data search --category food --type expense

# 예산 설정과 월별 요약
python -m budget_app --data-dir ./evaluation_data budget set --month 2026-07 --amount 50000
python -m budget_app --data-dir ./evaluation_data summary --month 2026-07 --top 3

# CSV 내보내기
python -m budget_app --data-dir ./evaluation_data export --out evaluation_result.csv --month 2026-07

# 오류 메시지와 비정상 종료 코드 확인
python -m budget_app --data-dir ./evaluation_data delete --id NO-ID
$LASTEXITCODE
```

평가 직전에는 불필요한 외부 라이브러리 import가 없는지 확인하고 자동 테스트가
실제로 통과하는지 다시 검증한다. README의 과거 실행 결과만 제시하지 않고,
평가 환경에서 실행한 최신 결과를 직접 보여 주는 것이 중요하다.

### 평가 마무리 멘트

> 이 프로젝트는 단순히 명령이 동작하는 데서 끝나지 않고 영구 저장, 입력
> 검증, 책임 분리, 제너레이터 스트리밍, 공통 기능 분리와 원자적 파일 교체를
> 적용했습니다. 따라서 데이터가 많아지거나 오류가 발생하는 상황까지 고려한
> 유지보수 가능한 콘솔 서비스로 구현했습니다.

## 실제 평가 문항별 답변

아래 내용은 평가 화면의 문항 순서에 맞춘 구두 설명입니다.

### 항목 1 — 기능, 영구 저장, 오류 처리

#### 1) 필수 명령이 요구사항대로 동작하는가?

`cli.py`의 `build_parser()`에서 모든 명령과 옵션을 정의하고,
`dispatch()`에서 각 명령을 `BudgetService` 기능으로 연결했습니다.

| 명령 | 동작 |
|---|---|
| `add` | 대화형 입력을 검증하고 UUID 기반 id를 생성하여 저장 |
| `list` | `--limit`만큼 날짜 최신순으로 스트리밍 출력 |
| `search` | 기간·카테고리·타입·메모·태그 조건 검색 |
| `summary` | 월 수입·지출·잔액과 지출 TOP N 출력 |
| `export` | 월 또는 기간에 해당하는 거래를 CSV로 출력 |
| `import` | CSV 각 행을 검증하여 정상 거래 등록 |
| `update` | id와 변경 옵션으로 거래 수정 |
| `delete` | id에 해당하는 거래 삭제 |

자동 테스트의 `test_add_list_search_update_delete`,
`test_summary_and_budget_warning`, `test_import_export_csv`에서 핵심 흐름을
검증했습니다.

#### 2) 프로그램을 다시 실행해도 데이터가 유지되는가?

메모리가 아니라 다음 파일에 즉시 저장하므로 프로세스가 종료되어도 유지됩니다.

```text
transactions.jsonl  거래
categories.jsonl    카테고리
budgets.jsonl       예산
```

저장소 객체를 새로 만들어도 같은 `--data-dir`을 가리키면 파일에서 기존 값을
다시 읽습니다. `test_initializes_three_storage_files`에서 세 파일의 생성을
검증했습니다.

#### 3) 카테고리 추가·목록·삭제와 사용 중 카테고리 처리는?

`CategoryStore`가 카테고리를 영구 저장하며 `BudgetService.remove_category()`는
삭제 전 모든 거래를 스트리밍하여 사용 여부를 확인합니다. 사용 중이면 삭제하지
않고 다음과 같은 사용자 오류를 반환합니다.

```text
[오류] 사용 중인 카테고리는 삭제할 수 없습니다: food
[힌트] 해당 거래를 다른 카테고리로 수정한 뒤 다시 시도하세요.
```

`test_category_in_use_cannot_be_removed`로 검증했습니다.

#### 4) 예산 저장과 사용률·초과 여부는?

`BudgetStore.set()`이 `YYYY-MM`별 예산을 `budgets.jsonl`에 저장합니다.
`monthly_summary()`는 `지출 ÷ 예산 × 100`으로 사용률을 계산하며 지출이
예산보다 크면 초과 경고를 출력합니다.

```text
예산: 50,000원 (사용률 134.0%)
[경고] 월 예산을 초과했습니다!
```

#### 5) CSV 스키마는 지켰는가?

가져오기와 내보내기는 모두 `csv.DictReader/DictWriter`를 사용합니다.
내보내기는 `utf-8-sig`로 작성하여 Excel에서도 한글을 안정적으로 열 수 있고,
가져오기는 UTF-8과 UTF-8 BOM을 모두 읽습니다. 헤더는 다음 순서로 고정됩니다.

```text
date,type,category,amount,memo,tags
```

필수 열은 `date`, `type`, `category`, `amount`이며, 필수 헤더가 빠지면 거래를
읽기 전에 전체 오류로 처리합니다.

#### 6) 잘못된 입력과 파일 오류는 어떻게 처리하는가?

예상 가능한 사용자 오류는 `AppError(message, hint)`로 표현합니다.
`main()`이 이를 받아 스택트레이스 없이 `[오류]`와 `[힌트]`를 표준 오류로
출력합니다. 파일 오류와 예상하지 못한 오류도 최상위에서 잡아 스택트레이스를
노출하지 않습니다. 대화형 `add`의 날짜·타입·카테고리·금액은
`prompt_validated()`가 검증하며 잘못된 경우 올바른 값을 입력할 때까지 다시
묻습니다.

명령 문법 오류는 `FriendlyArgumentParser.error()`가 처리합니다. 예를 들어
`python -m budget_app -add`는 다음 힌트를 출력하고 종료 코드 2로 끝납니다.

```text
[오류] 명령어 또는 옵션이 올바르지 않습니다.
[힌트] 명령에는 하이픈을 붙이지 않습니다. 예: python -m budget_app add
[힌트] 전체 사용법: python -m budget_app --help
```

#### 7) 오류 종료 코드가 0이 아닌가?

정상은 `0`, 사용자 입력·업무 규칙 오류는 `2`, 파일 오류는 `3`, 예상하지
못한 오류는 `1`, 사용자 취소는 `130`입니다.
`test_error_has_nonzero_exit_code_without_traceback`에서 없는 id 삭제의 종료
코드가 0이 아니고 `Traceback`이 출력되지 않는지 확인했습니다.

### 항목 2 — 모듈, 클래스, 안전한 수정·삭제

#### 1) 모듈의 책임을 어떻게 나눴는가?

- `models.py`: 데이터 모양과 값 검증
- `repositories.py`: JSONL 파일 입출력과 원자적 저장
- `services.py`: 가계부 업무 규칙
- `cli.py`: 사용자 명령과 화면 출력
- `decorators.py`: 실행 로그와 시간 측정

CLI가 파일 형식을 직접 알지 않고 서비스가 화면 출력 방식을 알지 않게 분리한
것이 핵심입니다. 따라서 저장 방식 또는 화면을 변경할 때 다른 계층의 변경을
줄일 수 있습니다.

#### 2) 클래스의 책임 경계는 어떻게 정했는가?

- `Transaction`: 거래 한 건의 상태와 자체 유효성
- `SearchCriteria`: 검색 조건과 기간 유효성
- `TransactionRepository`: 거래 파일의 조회·저장·교체·삭제
- `CategoryStore`: 카테고리 파일 관리
- `BudgetStore`: 월 예산 파일 관리
- `BudgetService`: 여러 저장소를 조합하는 업무 규칙

데이터 자체의 규칙, 파일 관리, 여러 데이터를 조합하는 업무 규칙을 서로 다른
클래스에 배치했습니다.

#### 3) 파일 기반 update/delete를 어떻게 안전하게 처리했는가?

원본을 직접 수정하지 않고 다음 순서를 사용합니다.

1. 기존 거래를 읽어 수정 또는 삭제 결과를 생성
2. 원본과 같은 폴더의 임시 파일에 전체 결과 기록
3. `flush()`와 `os.fsync()`로 운영체제 버퍼까지 반영
4. 기록이 성공한 경우에만 `os.replace()`로 원본과 원자적 교체
5. 실패하면 임시 파일을 제거하고 기존 원본 유지

### 항목 3 — 제너레이터, 데코레이터, 타입 힌트

#### 1) list/search 스트리밍을 어떻게 구현했고 왜 유리한가?

`_iter_lines_reverse()`는 파일 끝에서 8KB 블록씩 읽어 완성된 JSONL 행을
하나씩 `yield`합니다. `TransactionRepository.iter_all(newest_first=True)`이
각 행을 `Transaction`으로 변환하고, `BudgetService.list_transactions()`와
`search()`도 결과를 다시 하나씩 `yield`합니다.

전체 파일을 `read()`나 `readlines()`로 올리지 않으므로 목록과 검색 자체는
거래 파일 크기에 비례해 메모리가 증가하지 않습니다. 또한 `list --limit 10`은
10건을 얻은 즉시 읽기를 중단할 수 있습니다.

#### 2) 데코레이터로 분리한 공통 기능과 분리 이유는?

`@log_execution`이 성공·실패 상태와 실행 시간을 `app.log`에 기록합니다.
로그와 시간 측정은 모든 명령에 공통이지만 거래 계산의 핵심 업무는 아닙니다.
데코레이터로 분리하면 각 명령에 `try/finally`, 시간 계산, 파일 기록 코드를
반복하지 않아도 되고 로그 형식도 한 곳에서 관리할 수 있습니다.

#### 3) 타입 힌트의 이점을 어떻게 확인했고 왜 도움이 되는가?

예를 들어 다음 시그니처는 검색 입력과 출력 계약을 명확하게 보여 줍니다.

```python
def search(self, criteria: SearchCriteria) -> Iterator[Transaction]:
```

`criteria`에는 임의의 딕셔너리가 아니라 `SearchCriteria`가 필요하고, 반환값은
거래 목록을 한 번에 반환하는 `list`가 아니라 한 건씩 제공하는 반복자임을
알 수 있습니다. IDE 자동완성, 정적 분석, 코드 리뷰에서 잘못된 필드나 반환값
사용을 발견하기 쉬워집니다. 타입 힌트는 실행 중 값을 강제하지 않으므로 실제
입력 안전성은 `Transaction.__post_init__()`과 검증 함수가 담당하고, 테스트로
그 동작을 확인했습니다.

### 항목 4 — 저장 포맷, 대용량, 손상 CSV

#### 1) JSONL과 CSV의 장단점 및 JSONL 선택 근거는?

| 비교 | JSONL | CSV |
|---|---|---|
| 장점 | 자료형 표현이 명확하고 태그 배열을 그대로 저장 가능 | Excel 호환성과 표 형태 가독성이 좋음 |
| 단점 | 일반 사용자가 직접 편집하기 불편함 | 배열·중첩 데이터 표현과 쉼표 escaping이 복잡함 |
| 스트리밍 | 한 줄이 한 객체라 한 줄씩 처리하기 쉬움 | 역시 행 단위 처리가 가능함 |

내부 저장에는 `tags: list[str]`를 자연스럽게 표현하고 거래 한 건을 독립된
객체로 검증하기 쉬운 JSONL을 선택했습니다. 사용자 교환 형식은 Excel
호환성이 좋은 CSV로 분리했습니다.

#### 2) 거래가 10만 건이라면 병목과 개선 방법은?

현재 목록·검색은 스트리밍이므로 메모리 사용은 안정적입니다. 하지만 다음
부분은 병목이 됩니다.

- 추가·수정·삭제 때 전체 거래를 리스트로 만들고 다시 정렬·기록
- 월별 요약 때 전체 파일 순차 검색
- CSV 가져오기에서 행마다 거래 파일을 다시 작성하여 대량 입력 시 매우 느림

JSONL 제약을 유지한다면 CSV의 정상 행을 메모리 또는 임시 파일에서 먼저
검증한 뒤 한 번만 병합·정렬하는 배치 가져오기로 개선할 수 있습니다. 월별
파일로 파티셔닝하거나 월·id 인덱스 파일을 추가하면 검색 범위를 줄일 수
있습니다. 저장 방식 변경이 허용된다면 인덱스와 트랜잭션을 제공하는 SQLite가
대규모 CRUD에 더 적합합니다.

#### 3) CSV 일부 행이 깨졌을 때 사용자 신뢰를 어떻게 지키는가?

현재는 **부분 성공 방식**입니다. 각 행을 독립적으로 검증하여 정상 행은
저장하고 잘못된 행은 건너뛴 뒤 다음처럼 결과를 보고합니다.

```text
[완료] imported=5, skipped=2
```

원본 CSV는 수정하지 않으며, 파일 부재나 필수 헤더 누락처럼 파일 전체의
신뢰성이 없는 경우에는 가져오기를 시작하지 않고 오류로 종료합니다.

더 엄격한 운영 환경에서는 다음 두 모드를 제공하는 것이 좋습니다.

- `--partial`: 정상 행 반영 + 행 번호·오류 원인을 별도 리포트로 저장
- `--strict`: 전체 행을 먼저 검증하고 한 행이라도 실패하면 아무것도 반영하지
  않는 롤백 방식

현재 구현은 과제의 처리 건수 출력 요구에 맞춘 부분 성공 방식이며, 평가 시에는
부분 성공의 장점과 함께 행별 오류 리포트 및 배치 원자 저장이 다음 개선점임을
명확히 설명할 수 있습니다.

### 항목 5 — 보너스

백업과 반복 거래 같은 보너스 기능은 구현하지 않았습니다. 보너스 미구현은
필수 항목의 실패가 아니며, 필수 기능과 설명 가능성에 집중했습니다. 다만
수정·삭제의 임시 파일 및 원자적 교체는 필수 데이터 안전성에도 직접 도움이
되므로 적용했습니다.
