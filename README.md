# The Beat 🎯

한국 주식 시장 장전 브리핑 텔레그램 봇

전일 장 마감(16:00)부터 당일 아침(08:00) 사이의 뉴스와 공시를 수집하고, AI로 호재/악재를 분석하여 텔레그램으로 전송합니다.

## 📋 주요 기능

- **뉴스 수집**: 네이버 뉴스 API로 '특징주', '단독', '공급계약' 키워드 뉴스 수집
- **공시 수집**: OpenDART API로 공급계약, 유상증자, 인수/합병 관련 공시 수집
- **종목명 매칭**: pykrx를 활용한 정확한 상장사 종목명 추출 (Longest Match First 알고리즘)
- **AI 분석**: Gemini 1.5 Flash로 호재/악재 분석
- **텔레그램 전송**: 분석 결과를 텔레그램으로 자동 전송

## 🏗️ 프로젝트 구조

```
TheBeat/
├── utils.py              # 날짜/시간 계산 유틸리티
├── stock_matcher.py      # 종목명 매칭 (pykrx + Longest Match First)
├── news_collector.py     # 네이버 뉴스 수집
├── dart_collector.py     # OpenDART 공시 수집
├── analyzer.py           # Gemini API 호재/악재 분석 (예정)
├── telegram_bot.py       # 텔레그램 전송 (예정)
├── main.py               # 메인 실행 파일 (예정)
├── requirements.txt      # 의존성 패키지
└── .env                  # 환경 변수 (API 키)
```

## 🚀 설치 및 설정

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. API 키 발급

#### Naver Search API
1. [네이버 개발자 센터](https://developers.naver.com/apps/#/register) 접속
2. 애플리케이션 등록 → 검색 API 선택
3. Client ID와 Client Secret 발급

#### OpenDART API
1. [OpenDART](https://opendart.fss.or.kr/) 접속
2. 회원가입 후 API 키 발급

#### Google Gemini API
1. [Google AI Studio](https://aistudio.google.com/app/apikey) 접속
2. API 키 생성

#### Telegram Bot
1. 텔레그램에서 [@BotFather](https://t.me/BotFather) 검색
2. `/newbot` 명령어로 봇 생성
3. Bot Token 발급
4. 자신의 Chat ID 확인 ([@userinfobot](https://t.me/userinfobot) 사용)

### 3. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 API 키를 입력하세요:

```bash
cp .env.example .env
```

`.env` 파일 내용:
```env
NAVER_CLIENT_ID=your_naver_client_id_here
NAVER_CLIENT_SECRET=your_naver_client_secret_here
DART_API_KEY=your_dart_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

## 🧪 모듈별 테스트

### 시간 계산 테스트
```bash
python utils.py
```

### 종목명 매칭 테스트
```bash
python stock_matcher.py
```

### 뉴스 수집 테스트
```bash
python news_collector.py
```

### 공시 수집 테스트
```bash
python dart_collector.py
```

## 💡 핵심 로직

### Longest Match First 알고리즘

종목명 매칭 시 '삼성전자'와 '삼성전자우'를 정확히 구분하기 위해 **긴 종목명부터 매칭**합니다.

```python
# 예시: "삼성전자우 주가 급등"
# ✅ 올바른 매칭: '삼성전자우' (005935)
# ❌ 잘못된 매칭: '삼성전자' (005930)
```

### 시간 범위 계산

주말과 공휴일을 자동으로 고려하여 데이터 수집 시작 시점을 계산합니다.

```python
# 월요일 오전 8시 실행 시
# 시작: 지난 금요일 16:00
# 종료: 현재 시간 (월요일 08:00)
```

## 📊 데이터 흐름

```
1. utils.py → 수집 시간 범위 계산 (전일 16:00 ~ 현재)
2. stock_matcher.py → pykrx로 전체 상장 종목 리스트 생성
3. news_collector.py → 네이버 뉴스 수집 + 종목명 추출
4. dart_collector.py → OpenDART 공시 수집 + 종목명 매칭
5. analyzer.py → Gemini API로 호재/악재 분석
6. telegram_bot.py → 텔레그램 브리핑 전송
```

## 🔧 개발 현황

- [x] 시간 계산 로직 (`utils.py`)
- [x] 종목명 매칭 (`stock_matcher.py`)
- [x] 뉴스 수집 (`news_collector.py`)
- [x] 공시 수집 (`dart_collector.py`)
- [x] AI 분석 (`analyzer.py`)
- [x] 텔레그램 전송 (`telegram_bot.py`)
- [x] 메인 통합 (`main.py`)

## 📝 라이선스

MIT License

## 🤝 기여

이슈 및 PR을 환영합니다!
