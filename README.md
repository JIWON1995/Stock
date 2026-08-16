# SeagullPirates - 주식 분석 웹페이지

Django + MySQL 기반 주식 분석 웹페이지.

## 기술 스택

- Python 3.14
- Django 5.2 (LTS)
- MySQL 8.0 (원격 호스팅 DB, mysqlclient로 연결)
- Chart.js (종목 상세 페이지 시세 차트)
- DART Open API (종목 상세 페이지 공시 목록, requests로 연동)
- Gemini API (공시 원문 AI 요약/분석, requests로 연동)

> Django 6.1은 MySQL 8.4 이상을 요구해서, 8.0을 쓰는 원격 DB와 호환되는 5.2 LTS로 맞췄습니다.

## 프로젝트 구조

```
config/     # Django 프로젝트 설정 (settings, urls)
stocks/     # 주식 분석 앱 (models, views, admin, templates)
templates/  # 공통 base.html
.env        # DB 접속정보 등 환경변수 (git에 커밋되지 않음)
```

## DB 구조

기존에 키움증권 OpenAPI 연동으로 쌓여있던 원격 MySQL(`ywlove`) 테이블을 읽기 전용(`managed = False`)으로 매핑해서 사용합니다. 새 테이블을 만들지 않고 기존 데이터를 그대로 조회합니다.

- `SCODE` → `stocks.Stock` : 종목 마스터 정보 (종목코드, 종목명, 목표가/손절가 등)
- `OPT10081` → `stocks.DailyPrice` : 종목별 일봉(OHLCV) 시세, `Stock`과 FK로 연결

이 두 테이블은 읽기 전용이며, 아래 `stocks.DisclosureAnalysis`만 Django가 관리하는(`managed = True`) 신규 테이블입니다. `python manage.py migrate`로 생성했습니다.

- `stocks_disclosureanalysis` → `stocks.DisclosureAnalysis` : 공시(`rcept_no`)별 Gemini 분석 결과 캐시

## 실행 방법

```bash
cd /Users/kimjiwon/PycharmProjects/SeagullPirates
source .venv/bin/activate
python manage.py runserver
```

- 종목 목록: http://127.0.0.1:8000/
- 종목 상세: http://127.0.0.1:8000/stocks/<종목코드>/
- 관리자 페이지: http://127.0.0.1:8000/admin/

관리자 계정이 없다면 아래 명령어로 생성합니다.

```bash
python manage.py createsuperuser
```

## 환경변수 (.env)

DB 접속정보는 `.env` 파일에서 관리하며 저장소에는 커밋하지 않습니다 (`.gitignore`에 등록됨).

```
DEBUG=True
SECRET_KEY=...

DB_NAME=ywlove
DB_USER=redbull
DB_PASSWORD=...
DB_HOST=my8003.gabiadb.com
DB_PORT=3306

# https://opendart.fss.or.kr 에서 발급받은 Open API 인증키
DART_API_KEY=...

# https://aistudio.google.com 에서 발급받은 Gemini API 인증키
GEMINI_API_KEY=...
```

## 주요 기능

- 종목 목록: 종목코드/종목명 검색, 페이지네이션, 현재가·등락률(상승 빨강/하락 파랑)·거래량 표시
- 종목 상세: 현재가/전일대비/거래량 요약 카드, 최근 60거래일 시세표, Chart.js 라인 차트
- 종목 상세: DART 최근 1년 공시 목록 (원문 링크 연결, `stocks/dart.py`)
- 종목 상세: 공시별 Gemini AI 분석 (핵심 요약 / 투자자 시사점 / 리스크, `stocks/gemini_client.py`)
- Django admin: 종목(`Stock`) 조회/수정 (실데이터 보호를 위해 삭제 권한은 비활성화)

## DART 공시 연동 (`stocks/dart.py`)

- 종목코드(6자리)는 DART 고유번호(8자리, `corp_code`)와 달라서 `corpCode.xml`을 내려받아 매핑 테이블을 만든다. 매핑 결과는 `var/dart_corp_codes.json`에 캐싱하고 7일마다 갱신한다 (`var/`는 git에 커밋되지 않음).
- 공시 목록(`list.json`)은 최근 1년치를 조회하며, 종목별로 10분간 캐싱한다 (Django 기본 로컬 메모리 캐시).
- `DART_API_KEY`가 없거나 API 오류가 발생하면 페이지에 에러 메시지를 표시하고 나머지 페이지는 정상 렌더링한다.

## 공시 AI 분석 (`stocks/gemini_client.py`)

- 별도 스케줄러 없이, 종목 상세 페이지를 방문할 때마다 그 종목의 공시 목록 중 아직 분석되지 않은 것을 감지해서 즉석으로 분석한다.
- 공시 원문은 DART `document.xml`(원문 API)에서 내려받아 태그를 제거한 뒤 앞부분 4만 자까지만 Gemini(`gemini-flash-latest`)에 보낸다. 사업/분기보고서처럼 매우 큰 문서는 앞부분만 반영된다.
- 분석 결과는 `stocks.DisclosureAnalysis`에 `rcept_no`별로 영구 캐싱되어 같은 공시를 재분석하지 않는다.
- 응답 지연과 API 비용을 제한하기 위해 한 번의 페이지 방문에서 최대 3건만 새로 분석한다(`MAX_AUTO_ANALYZE_PER_VISIT`, `stocks/views.py`). 나머지 미분석 공시는 "다음 방문 시 자동으로 분석됩니다"로 표시되고, 다음 방문 때 이어서 분석된다.
- `GEMINI_API_KEY` 미설정, DART 원문 조회 실패, Gemini 응답 오류(타임아웃/일시적 5xx 등)는 모두 개별 공시 단위로 에러 메시지를 보여주고 페이지 전체는 정상 렌더링한다.
