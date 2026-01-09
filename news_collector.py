"""
The Beat - 네이버 뉴스 수집 모듈
Naver Search API를 사용하여 특정 키워드 뉴스 수집 및 종목명 매칭
"""

import requests
import logging
from datetime import datetime
from typing import List, Dict, Optional
from utils import get_data_collection_timerange, format_date_for_api
from stock_matcher import get_stock_list_cached, extract_stock_names

logger = logging.getLogger(__name__)


class NaverNewsCollector:
    """네이버 뉴스 수집기"""
    
    # 수집할 키워드 목록
    KEYWORDS = ['특징주', '단독', '공급계약']
    
    def __init__(self, client_id: str, client_secret: str):
        """
        Args:
            client_id (str): 네이버 API Client ID
            client_secret (str): 네이버 API Client Secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_url = "https://openapi.naver.com/v1/search/news.json"
        self.stock_list = get_stock_list_cached()
        
        logger.info(f"NaverNewsCollector 초기화 완료 (종목 수: {len(self.stock_list)})")
    
    def _search_news(self, keyword: str, start_date: datetime, end_date: datetime, 
                     display: int = 100) -> List[Dict]:
        """
        특정 키워드로 뉴스 검색
        
        Args:
            keyword (str): 검색 키워드
            start_date (datetime): 검색 시작 시간
            end_date (datetime): 검색 종료 시간
            display (int): 가져올 뉴스 개수 (최대 100)
        
        Returns:
            List[Dict]: 뉴스 아이템 리스트
        """
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }
        
        params = {
            "query": keyword,
            "display": min(display, 100),  # 최대 100개
            "start": 1,
            "sort": "date"  # 최신순 정렬
        }
        
        try:
            response = requests.get(self.api_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            items = data.get('items', [])
            
            logger.info(f"키워드 '{keyword}': {len(items)}개 뉴스 수집")
            return items
            
        except requests.exceptions.RequestException as e:
            logger.error(f"뉴스 검색 실패 (키워드: {keyword}): {e}")
            return []
    
    def _filter_by_timerange(self, news_items: List[Dict], 
                            start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        시간 범위로 뉴스 필터링
        
        Args:
            news_items (List[Dict]): 뉴스 아이템 리스트
            start_date (datetime): 시작 시간
            end_date (datetime): 종료 시간
        
        Returns:
            List[Dict]: 필터링된 뉴스 리스트
        """
        filtered = []
        
        for item in news_items:
            try:
                # pubDate 형식: "Mon, 09 Jan 2026 16:00:00 +0900"
                pub_date_str = item.get('pubDate', '')
                pub_date = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %z")
                
                # 시간대 정보 제거하여 비교 (naive datetime으로 변환)
                pub_date_naive = pub_date.replace(tzinfo=None)
                
                if start_date <= pub_date_naive <= end_date:
                    filtered.append(item)
                    
            except Exception as e:
                logger.debug(f"날짜 파싱 실패: {e}")
                continue
        
        if len(filtered) > 0 or len(news_items) == 0:
            logger.info(f"시간 범위 필터링: {len(news_items)}개 → {len(filtered)}개")
        else:
            logger.debug(f"시간 범위 필터링: {len(news_items)}개 → {len(filtered)}개")
            
        return filtered
    
    def _extract_stocks_from_news(self, news_item: Dict) -> List[Dict[str, str]]:
        """
        뉴스 제목에서 종목명 추출
        
        Args:
            news_item (Dict): 뉴스 아이템
        
        Returns:
            List[Dict]: 매칭된 종목 리스트
        """
        title = news_item.get('title', '')
        
        # HTML 태그 제거
        title = title.replace('<b>', '').replace('</b>', '')
        title = title.replace('&quot;', '"').replace('&apos;', "'")
        
        # 종목명 추출
        stocks = extract_stock_names(title, self.stock_list)
        
        return stocks
    
    def collect_news(self, base_date: Optional[datetime] = None) -> List[Dict]:
        """
        전일 16:00 ~ 현재 시간(또는 base_date) 사이의 뉴스 수집 및 종목명 매칭
        
        Args:
            base_date (datetime, optional): 기준 시간. 백테스트용.
        
        Returns:
            List[Dict]: 종목명이 매칭된 뉴스 리스트
            [
                {
                    'title': '뉴스 제목',
                    'link': 'URL',
                    'description': '요약',
                    'pubDate': '발행일',
                    'keyword': '검색 키워드',
                    'stocks': [{'name': '삼성전자', 'ticker': '005930', 'market': 'KOSPI'}]
                },
                ...
            ]
        """
        # 수집 시간 범위 가져오기
        start_date, end_date = get_data_collection_timerange(base_date)
        
        logger.info(f"뉴스 수집 시작: {start_date} ~ {end_date}")
        
        all_news = []
        
        # 각 키워드별로 뉴스 수집
        for keyword in self.KEYWORDS:
            news_items = self._search_news(keyword, start_date, end_date)
            
            # 시간 범위 필터링
            filtered_items = self._filter_by_timerange(news_items, start_date, end_date)
            
            # 종목명 추출 및 매칭
            for item in filtered_items:
                stocks = self._extract_stocks_from_news(item)
                
                # 종목명이 있는 뉴스만 저장
                if stocks:
                    news_data = {
                        'title': item.get('title', '').replace('<b>', '').replace('</b>', ''),
                        'link': item.get('link', ''),
                        'description': item.get('description', '').replace('<b>', '').replace('</b>', ''),
                        'pubDate': item.get('pubDate', ''),
                        'keyword': keyword,
                        'stocks': stocks
                    }
                    all_news.append(news_data)
        
        # 중복 제거 (같은 링크)
        unique_news = []
        seen_links = set()
        for news in all_news:
            if news['link'] not in seen_links:
                unique_news.append(news)
                seen_links.add(news['link'])
        
        logger.info(f"총 {len(unique_news)}개 뉴스 수집 완료 (종목명 매칭됨)")
        
        return unique_news


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    # 환경변수 로드
    load_dotenv()
    
    print("=" * 60)
    print("The Beat - 네이버 뉴스 수집 테스트")
    print("=" * 60)
    
    # API 키 확인
    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("\n⚠️  .env 파일에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET를 설정해주세요.")
        print("\n예시 (.env 파일):")
        print("NAVER_CLIENT_ID=your_client_id")
        print("NAVER_CLIENT_SECRET=your_client_secret")
        exit(1)
    
    # 뉴스 수집기 생성
    collector = NaverNewsCollector(client_id, client_secret)
    
    # 뉴스 수집
    news_list = collector.collect_news()
    
    # 결과 출력
    print(f"\n수집된 뉴스: {len(news_list)}개")
    print("=" * 60)
    
    for i, news in enumerate(news_list[:10], 1):  # 처음 10개만 출력
        print(f"\n[{i}] {news['title']}")
        print(f"    키워드: {news['keyword']}")
        print(f"    발행일: {news['pubDate']}")
        stock_info = ', '.join([f"{s['name']}({s['ticker']})" for s in news['stocks']])
        print(f"    종목: {stock_info}")
        print(f"    링크: {news['link']}")
    
    if len(news_list) > 10:
        print(f"\n... 외 {len(news_list) - 10}개")
    
    print("\n" + "=" * 60)
