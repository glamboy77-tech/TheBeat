"""
The Beat - OpenDART 공시 수집 모듈
OpenDART API를 사용하여 공시 정보 수집 및 종목명 매칭
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from utils import get_data_collection_timerange, format_date_for_api
from stock_matcher import get_stock_list_cached, extract_stock_names

logger = logging.getLogger(__name__)


class DartCollector:
    """OpenDART 공시 수집기"""
    
    # 수집할 공시 유형 (보고서명 키워드)
    DISCLOSURE_KEYWORDS = [
        '공급계약',
        '유상증자',
        '주요사항보고서(인수합병)',
        '합병',
        '인수',
        '주요경영사항',
        '타법인주식',
        '전환사채',
        '신주인수권부사채'
    ]
    
    def __init__(self, api_key: str):
        """
        Args:
            api_key (str): OpenDART API 키
        """
        self.api_key = api_key
        self.api_url = "https://opendart.fss.or.kr/api/list.json"
        self.stock_list = get_stock_list_cached()
        
        logger.info(f"DartCollector 초기화 완료 (종목 수: {len(self.stock_list)})")
    
    def _get_corp_code_map(self) -> Dict[str, str]:
        """
        종목코드 → 고유번호(corp_code) 매핑 생성
        
        Returns:
            Dict[str, str]: {ticker: corp_code} 매핑
        """
        # DART API의 고유번호는 별도 다운로드가 필요하므로
        # 여기서는 종목코드를 그대로 사용 (DART API는 종목코드도 지원)
        corp_map = {}
        for stock in self.stock_list:
            corp_map[stock['ticker']] = stock['ticker']
        
        return corp_map
    
    def _search_disclosures(self, start_date: str, end_date: str, page_count: int = 100) -> List[Dict]:
        """
        공시 검색
        
        Args:
            start_date (str): 시작일 (YYYYMMDD)
            end_date (str): 종료일 (YYYYMMDD)
            page_count (int): 페이지당 건수 (최대 100)
        
        Returns:
            List[Dict]: 공시 리스트
        """
        params = {
            'crtfc_key': self.api_key,
            'bgn_de': start_date,
            'end_de': end_date,
            'page_count': min(page_count, 100),
            'page_no': 1
        }
        
        all_disclosures = []
        
        try:
            # 첫 페이지 요청
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != '000':
                logger.error(f"DART API 오류: {data.get('message', 'Unknown error')}")
                return []
            
            total_count = int(data.get('total_count', 0))
            total_page = int(data.get('total_page', 0))
            
            logger.info(f"DART 공시 총 {total_count}건 (페이지: {total_page})")
            
            # 첫 페이지 데이터 추가
            items = data.get('list', [])
            all_disclosures.extend(items)
            
            # 추가 페이지가 있으면 가져오기 (최대 5페이지까지)
            for page_no in range(2, min(total_page + 1, 6)):
                params['page_no'] = page_no
                response = requests.get(self.api_url, params=params, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                if data.get('status') == '000':
                    items = data.get('list', [])
                    all_disclosures.extend(items)
                    logger.info(f"페이지 {page_no} 수집 완료 ({len(items)}건)")
            
            logger.info(f"총 {len(all_disclosures)}건 공시 수집 완료")
            return all_disclosures
            
        except requests.exceptions.RequestException as e:
            logger.error(f"DART API 요청 실패: {e}")
            return []
    
    def _filter_by_keywords(self, disclosures: List[Dict]) -> List[Dict]:
        """
        키워드로 공시 필터링
        
        Args:
            disclosures (List[Dict]): 전체 공시 리스트
        
        Returns:
            List[Dict]: 필터링된 공시 리스트
        """
        filtered = []
        
        for disclosure in disclosures:
            report_nm = disclosure.get('report_nm', '')
            
            # 키워드 매칭
            for keyword in self.DISCLOSURE_KEYWORDS:
                if keyword in report_nm:
                    disclosure['matched_keyword'] = keyword
                    filtered.append(disclosure)
                    break
        
        logger.info(f"키워드 필터링: {len(disclosures)}건 → {len(filtered)}건")
        return filtered
    
    def _match_stock_info(self, disclosure: Dict) -> Optional[Dict[str, str]]:
        """
        공시의 종목 정보 매칭
        
        Args:
            disclosure (Dict): 공시 정보
        
        Returns:
            Optional[Dict]: 매칭된 종목 정보
        """
        corp_name = disclosure.get('corp_name', '')
        stock_code = disclosure.get('stock_code', '')
        
        # 1. 종목코드로 직접 매칭
        if stock_code:
            for stock in self.stock_list:
                if stock['ticker'] == stock_code:
                    return stock
        
        # 2. 회사명으로 매칭
        if corp_name:
            stocks = extract_stock_names(corp_name, self.stock_list)
            if stocks:
                return stocks[0]
        
        return None
    
    def collect_disclosures(self, base_date: Optional[datetime] = None) -> List[Dict]:
        """
        전일 16:00 ~ 현재(또는 base_date) 공시 수집 및 종목명 매칭
        
        Args:
            base_date (datetime, optional): 기준 시간. 백테스트용.
            
        Returns:
            List[Dict]: 종목명이 매칭된 공시 리스트
            [
                {
                    'corp_name': '회사명',
                    'report_nm': '보고서명',
                    'rcept_no': '접수번호',
                    'rcept_dt': '접수일자',
                    'matched_keyword': '매칭된 키워드',
                    'stock': {'name': '삼성전자', 'ticker': '005930', 'market': 'KOSPI'}
                },
                ...
            ]
        """
        # 수집 시간 범위 가져오기
        start_datetime, end_datetime = get_data_collection_timerange(base_date)
        
        # DART API는 날짜만 사용 (시간 무시)
        start_date = format_date_for_api(start_datetime)
        end_date = format_date_for_api(end_datetime)
        
        logger.info(f"공시 수집 시작: {start_date} ~ {end_date}")
        
        # 공시 검색
        disclosures = self._search_disclosures(start_date, end_date)
        
        if not disclosures:
            logger.warning("수집된 공시가 없습니다.")
            return []
        
        # 키워드 필터링
        filtered_disclosures = self._filter_by_keywords(disclosures)
        
        # 종목 정보 매칭
        matched_disclosures = []
        for disclosure in filtered_disclosures:
            stock_info = self._match_stock_info(disclosure)
            
            if stock_info:
                disclosure_data = {
                    'corp_name': disclosure.get('corp_name', ''),
                    'report_nm': disclosure.get('report_nm', ''),
                    'rcept_no': disclosure.get('rcept_no', ''),
                    'rcept_dt': disclosure.get('rcept_dt', ''),
                    'flr_nm': disclosure.get('flr_nm', ''),  # 공시제출인명
                    'matched_keyword': disclosure.get('matched_keyword', ''),
                    'stock': stock_info
                }
                matched_disclosures.append(disclosure_data)
        
        logger.info(f"총 {len(matched_disclosures)}건 공시 수집 완료 (종목 매칭됨)")
        
        return matched_disclosures


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    # 환경변수 로드
    load_dotenv()
    
    print("=" * 60)
    print("The Beat - OpenDART 공시 수집 테스트")
    print("=" * 60)
    
    # API 키 확인
    api_key = os.getenv('DART_API_KEY')
    
    if not api_key:
        print("\n⚠️  .env 파일에 DART_API_KEY를 설정해주세요.")
        print("\n예시 (.env 파일):")
        print("DART_API_KEY=your_api_key")
        print("\nAPI 키 발급: https://opendart.fss.or.kr/")
        exit(1)
    
    # 공시 수집기 생성
    collector = DartCollector(api_key)
    
    # 공시 수집
    disclosures = collector.collect_disclosures()
    
    # 결과 출력
    print(f"\n수집된 공시: {len(disclosures)}건")
    print("=" * 60)
    
    for i, disclosure in enumerate(disclosures[:10], 1):  # 처음 10개만 출력
        print(f"\n[{i}] {disclosure['corp_name']} - {disclosure['report_nm']}")
        print(f"    키워드: {disclosure['matched_keyword']}")
        print(f"    접수일: {disclosure['rcept_dt']}")
        print(f"    종목: {disclosure['stock']['name']} ({disclosure['stock']['ticker']}) [{disclosure['stock']['market']}]")
        print(f"    접수번호: {disclosure['rcept_no']}")
    
    if len(disclosures) > 10:
        print(f"\n... 외 {len(disclosures) - 10}건")
    
    print("\n" + "=" * 60)
