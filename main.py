"""
The Beat - 메인 실행 파일
데이터 수집 -> AI 분석 -> 텔레그램 전송 전체 프로세스 실행
"""

import asyncio
import logging
import sys
from datetime import datetime

# 모듈 임포트
from utils import get_data_collection_timerange
from news_collector import NaverNewsCollector
from dart_collector import DartCollector
from analyzer import GeminiAnalyzer
from telegram_bot import TelegramSender
from redis_sender import TheBeatSender
from market_checker import check_market_status_once

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
        
        # [Step 0] 키움 웹소켓으로 장 상태 확인
        logger.info("[Step 0] 장 상태 확인 (키움 웹소켓)")
        market_status = await check_market_status_once()
        
        logger.info(f"장 상태: {market_status['status_name']}")
        logger.info(f"개장 여부: {market_status['is_open']}")
        logger.info(f"개장 시간: {market_status['open_time']}")
        
        # 휴장이면 텔레그램 알림 후 종료
        if not market_status['is_open']:
            logger.info("오늘은 휴장일입니다. 브리핑을 보내지 않고 종료합니다.")
            
            # 휴장 알림 메시지 전송 (선택사항)
            import os
            from dotenv import load_dotenv
            load_dotenv()
            
            sender = TelegramSender()
            today = datetime.now()
            day_name = ['월','화','수','목','금','토','일'][today.weekday()]
            休장_msg = [{"stock": "휴장", "grade": "INFO", "sector": "공지", 
                        "point": f"오늘({today.strftime('%Y-%m-%d')} {day_name})은 한국 거래소 휴장일입니다."}]
            
            await sender.send_holiday_message(today)
            logger.info("휴장 메시지 전송 완료")
            sys.exit(0)
        
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
        # 마지막 영업일을 브리핑 기준 날짜로 사용
        from utils import get_last_trading_day
        last_trading_day_str = get_last_trading_day()
        report_date = datetime.strptime(last_trading_day_str, "%Y%m%d")
        
        sender = TelegramSender()
        # 개장 시간 정보를 함께 전달
        await sender.send_report(analyzed_results, report_date, market_status['open_time'])
        
        # 5. Redis 송신 (S/A 등급만)
        logger.info("[Step 4] Redis 송신 (S/A 등급 필터링)")
        try:
            redis_sender = TheBeatSender()
            redis_stats = redis_sender.blast_news_batch(analyzed_results)
            logger.info(f"Redis 송신 완료: 전송 {redis_stats['sent']}건, 필터링 {redis_stats['filtered']}건, 중복 {redis_stats['duplicated']}건")
        except Exception as e:
            logger.warning(f"Redis 송신 실패 (무시하고 계속): {e}")
        
        logger.info("모든 작업이 성공적으로 완료되었습니다.")
        
    except Exception as e:
        logger.error(f"실행 중 치명적인 오류 발생: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
