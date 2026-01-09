"""
The Beat - 백테스트 실행 모듈
특정 과거 시점(YYYYMMDD 08:20)을 기준으로 데이터 수집 및 AI 분석 시뮬레이션
"""

import argparse
import logging
import asyncio
import json
import os
from datetime import datetime
from dotenv import load_dotenv

from utils import get_data_collection_timerange
from news_collector import NaverNewsCollector
from dart_collector import DartCollector
from analyzer import GeminiAnalyzer
from telegram_bot import TelegramSender

# 로깅 설정 (파일 및 콘솔)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def run_backtest(target_date_str: str):
    try:
        # 날짜 파싱 (YYYYMMDD)
        target_date = datetime.strptime(target_date_str, "%Y%m%d")
        
        # 시뮬레이션 시점 설정: 해당 날짜 오전 08:20
        # 예: 20260102 -> 2026-01-02 08:20:00
        simulated_now = target_date.replace(hour=8, minute=20, second=0, microsecond=0)
        
        logger.info("=" * 60)
        logger.info(f"The Beat 백테스트 시작")
        logger.info(f"타겟 날짜: {target_date_str}")
        logger.info(f"시뮬레이션 시점: {simulated_now}")
        logger.info("=" * 60)
        
        # 환경변수 로드
        load_dotenv()
        naver_id = os.getenv('NAVER_CLIENT_ID')
        naver_secret = os.getenv('NAVER_CLIENT_SECRET')
        dart_key = os.getenv('DART_API_KEY')
        gemini_key = os.getenv('GEMINI_API_KEY')
        
        if not all([naver_id, naver_secret, dart_key, gemini_key]):
            logger.error("필수 API 키가 설정되지 않았습니다.")
            return

        # 1. 데이터 수집 (시뮬레이션 시점 기준)
        logger.info("[Step 1] 과거 데이터 수집 시작")
        
        # 뉴스 수집
        news_collector = NaverNewsCollector(naver_id, naver_secret)
        news_list = news_collector.collect_news(base_date=simulated_now)
        
        # 공시 수집
        dart_collector = DartCollector(dart_key)
        disclosure_list = dart_collector.collect_disclosures(base_date=simulated_now)
        
        total_items = len(news_list) + len(disclosure_list)
        logger.info(f"총 {total_items}건 데이터 수집 완료 (뉴스: {len(news_list)}, 공시: {len(disclosure_list)})")
        
        # 2. AI 분석
        logger.info("[Step 2] AI 분석 시작")
        analyzed_results = []
        
        if total_items > 0:
            analyzer = GeminiAnalyzer()
            # API 비용 고려하여 중요도 순 또는 최신 순 일부만 분석 가능
            news_slice = news_list[:30]
            disclosure_slice = disclosure_list[:20]
            
            # 실제 AI 분석 수행
            analyzed_results = analyzer.analyze(news_slice, disclosure_slice)
            
            # 재료 강도순 정렬 (S > A > B > C)
            grade_priority = {'S': 0, 'A': 1, 'B': 2, 'C': 3}
            analyzed_results.sort(key=lambda x: grade_priority.get(x.get('grade', 'C').upper(), 99))
            
            logger.info(f"분석 완료: {len(analyzed_results)}건 (등급순 정렬됨)")
        else:
            logger.info("분석할 데이터가 없습니다.")
            return

        # 3. 결과 출력 (텔레그램 전송 대신 콘솔 출력)
        logger.info("[Step 3] 백테스트 결과 리포트")
        sender = TelegramSender()
        formatted_message = sender._format_report(analyzed_results)
        
        print("\n" + "="*20 + " [텔레그램 메시지 미리보기] " + "="*20)
        print(formatted_message)
        print("="*65 + "\n")
        
        # 파일 저장 옵션
        output_filename = f"backtest_result_{target_date_str}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(analyzed_results, f, indent=2, ensure_ascii=False)
        logger.info(f"분석 결과 파일 저장 완료: {output_filename}")

    except ValueError:
        logger.error("날짜 형식이 올바르지 않습니다. YYYYMMDD 형식으로 입력해주세요.")
    except Exception as e:
        logger.error(f"백테스트 중 오류 발생: {e}", exc_info=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The Beat 백테스트 도구")
    parser.add_argument("date", type=str, help="백테스트 기준 날짜 (YYYYMMDD)")
    
    args = parser.parse_args()
    
    asyncio.run(run_backtest(args.date))
