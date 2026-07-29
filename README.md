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
| 거래 추가 | 날짜·타입·카테고리·금액·메모·태그 대화형 입력, id 자동 생성 | `python -m budget_app add` |
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

최종 검증 결과:

```text
Ran 8 tests in 0.493s
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
