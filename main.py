"""
The Beat - 메인 실행 파일
데이터 수집 -> AI 분석 -> 텔레그램 전송 전체 프로세스 실행
"""

import asyncio
import logging
from datetime import datetime

# 모듈 임포트
from utils import get_data_collection_timerange
from news_collector import NaverNewsCollector
from dart_collector import DartCollector
from analyzer import GeminiAnalyzer
from telegram_bot import TelegramSender

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("thebeat.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    try:
        logger.info("="*60)
        logger.info(f"The Beat 실행 시작: {datetime.now()}")
        logger.info("="*60)
        
        # 한국 거래소 개장일 체크 (주말 + 공휴일 자동 감지)
        def is_market_open():
            """오늘이 한국 거래소 개장일인지 확인"""
            from pykrx import stock
            import logging as log
            
            # pykrx 로그 억제
            log.getLogger("pykrx").setLevel(log.CRITICAL)
            log.getLogger().setLevel(log.CRITICAL)
            
            try:
                today = datetime.now().strftime("%Y%m%d")
                # 삼성전자(005930) 기준으로 오늘 거래 데이터 확인
                df = stock.get_market_ohlcv(today, today, "005930")
                return not df.empty
            except:
                # API 실패 시 평일 여부로 판단 (fallback)
                return datetime.now().weekday() < 5
            finally:
                # 로그 레벨 복구
                log.getLogger("pykrx").setLevel(log.WARNING)
                log.getLogger().setLevel(log.INFO)
        
        if not is_market_open():
            today = datetime.now()
            day_name = ['월','화','수','목','금','토','일'][today.weekday()]
            logger.info(f"오늘({today.strftime('%Y-%m-%d')} {day_name})은 한국 거래소 휴장일입니다. 실행을 건너뜁니다.")
            return
        
        # 1. 환경 변수 확인 및 초기화
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        naver_id = os.getenv('NAVER_CLIENT_ID')
        naver_secret = os.getenv('NAVER_CLIENT_SECRET')
        dart_key = os.getenv('DART_API_KEY')
        gemini_key = os.getenv('GEMINI_API_KEY')
        
        if not all([naver_id, naver_secret, dart_key, gemini_key]):
            logger.error("필수 API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
            return

        # 2. 데이터 수집
        logger.info("[Step 1] 데이터 수집 시작")
        
        # 뉴스 수집
        news_collector = NaverNewsCollector(naver_id, naver_secret)
        news_list = news_collector.collect_news()
        
        # 공시 수집
        dart_collector = DartCollector(dart_key)
        disclosure_list = dart_collector.collect_disclosures()
        
        total_items = len(news_list) + len(disclosure_list)
        logger.info(f"총 {total_items}건 데이터 수집 완료 (뉴스: {len(news_list)}, 공시: {len(disclosure_list)})")
        
        # 3. AI 분석
        logger.info("[Step 2] AI 분석 시작")
        analyzed_results = []
        
        if total_items > 0:
            analyzer = GeminiAnalyzer()
            # API 비용 및 속도를 고려하여 최대 30개로 제한 (중요도 로직은 별도 없으나 최신순)
            # 실제 운영 시에는 배치 처리가 필요할 수 있음
            news_slice = news_list[:20] 
            disclosure_slice = disclosure_list[:10]
            
            analyzed_results = analyzer.analyze(news_slice, disclosure_slice)
            logger.info(f"분석 완료: {len(analyzed_results)}건")
        else:
            logger.info("분석할 데이터가 없습니다.")

        # 4. 텔레그램 전송
        logger.info("[Step 3] 텔레그램 전송")
        sender = TelegramSender()
        await sender.send_report(analyzed_results)
        
        logger.info("모든 작업이 성공적으로 완료되었습니다.")
        
    except Exception as e:
        logger.error(f"실행 중 치명적인 오류 발생: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
