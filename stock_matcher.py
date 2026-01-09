"""
The Beat - 종목명 매칭 모듈
pykrx를 사용한 상장사 종목 리스트 생성 및 Longest Match First 알고리즘
"""

from pykrx import stock
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def get_all_listed_stocks() -> List[Dict[str, str]]:
    """
    코스피/코스닥에 상장된 모든 종목 리스트 가져오기
    1차 시도: FinanceDataReader (안정적)
    2차 시도: pykrx (Fallback)
    
    Returns:
        List[Dict]: [{'name': '삼성전자', 'ticker': '005930', 'market': 'KOSPI'}, ...]
    """
    all_stocks = []
    
    # 1차 시도: FinanceDataReader
    try:
        import FinanceDataReader as fdr
        logger.info("1차 시도: FinanceDataReader로 종목 리스트 수집 중...")
        
        # KRX 전체 상장 종목
        df_krx = fdr.StockListing('KRX')
        
        # 필요한 컬럼만 추출 (Code, Name, Market)
        for _, row in df_krx.iterrows():
            market = row.get('Market', 'Unknown')
            if market not in ['KOSPI', 'KOSDAQ']:
                continue
                
            all_stocks.append({
                'name': row['Name'],
                'ticker': row['Code'],
                'market': market
            })
            
        if all_stocks:
            logger.info(f"FinanceDataReader 수집 성공: 총 {len(all_stocks)}개 종목")
            return all_stocks
        
    except Exception as e:
        logger.error(f"FinanceDataReader 수집 실패 상세: {type(e).__name__}: {e}")
        # 오류 발생 시 잠시 대기 (네트워크 이슈 등)
        import time
        time.sleep(1)

    # 2차 시도: pykrx
    try:
        logger.info("2차 시도: pykrx로 종목 리스트 수집 중...")
        
        # Root logger suppression for pykrx
        root_logger = logging.getLogger()
        orig_level = root_logger.level
        root_logger.setLevel(logging.CRITICAL)
        
        try:
            kospi_tickers = stock.get_market_ticker_list(market="KOSPI")
            kosdaq_tickers = stock.get_market_ticker_list(market="KOSDAQ")
        finally:
            root_logger.setLevel(orig_level)
        
        if kospi_tickers and kosdaq_tickers:
            for ticker in kospi_tickers:
                name = stock.get_market_ticker_name(ticker)
                all_stocks.append({'name': name, 'ticker': ticker, 'market': 'KOSPI'})
                
            for ticker in kosdaq_tickers:
                name = stock.get_market_ticker_name(ticker)
                all_stocks.append({'name': name, 'ticker': ticker, 'market': 'KOSDAQ'})
                
            logger.info(f"pykrx 수집 성공: 총 {len(all_stocks)}개 종목")
            return all_stocks
            
    except Exception as e:
        logger.warning(f"pykrx 수집 실패: {e}")
        
    return all_stocks


def extract_stock_names(text: str, stock_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    텍스트에서 종목명 추출 (Longest Match First 알고리즘)
    
    '삼성전자'와 '삼성전자우'를 구분하기 위해 긴 종목명부터 매칭
    
    Args:
        text (str): 뉴스 제목 또는 공시 제목
        stock_list (List[Dict]): get_all_listed_stocks()로 가져온 종목 리스트
    
    Returns:
        List[Dict]: 매칭된 종목 정보 리스트
        
    Examples:
        >>> text = "삼성전자우 주가 급등, LG전자도 상승"
        >>> extract_stock_names(text, stock_list)
        [{'name': '삼성전자우', 'ticker': '005935', 'market': 'KOSPI'},
         {'name': 'LG전자', 'ticker': '066570', 'market': 'KOSPI'}]
    """
    # 종목명 길이 기준 내림차순 정렬 (긴 것부터 매칭)
    sorted_stocks = sorted(stock_list, key=lambda x: len(x['name']), reverse=True)
    
    matched_stocks = []
    matched_positions = set()  # 이미 매칭된 텍스트 위치 추적
    
    for stock_info in sorted_stocks:
        stock_name = stock_info['name']
        
        # 텍스트에서 종목명 찾기
        start_pos = 0
        while True:
            pos = text.find(stock_name, start_pos)
            if pos == -1:
                break
            
            # 이미 매칭된 위치와 겹치는지 확인
            end_pos = pos + len(stock_name)
            position_range = set(range(pos, end_pos))
            
            if not position_range.intersection(matched_positions):
                # 겹치지 않으면 매칭 성공
                matched_stocks.append(stock_info)
                matched_positions.update(position_range)
                logger.debug(f"매칭 성공: {stock_name} (위치: {pos})")
            
            start_pos = pos + 1
    
    # 중복 제거 (같은 종목이 여러 번 언급된 경우)
    unique_stocks = []
    seen_tickers = set()
    for stock in matched_stocks:
        if stock['ticker'] not in seen_tickers:
            unique_stocks.append(stock)
            seen_tickers.add(stock['ticker'])
    
    if unique_stocks:
        logger.info(f"텍스트에서 {len(unique_stocks)}개 종목 추출: {[s['name'] for s in unique_stocks]}")
    
    return unique_stocks


# 전역 캐시 (프로그램 실행 중 한 번만 로드)
_stock_list_cache = None


def get_stock_list_cached() -> List[Dict[str, str]]:
    """
    종목 리스트를 캐시하여 반복 호출 시 성능 향상
    
    Returns:
        List[Dict]: 캐시된 종목 리스트
    """
    global _stock_list_cache
    
    if _stock_list_cache is None:
        logger.info("종목 리스트 캐시 생성 중...")
        _stock_list_cache = get_all_listed_stocks()
    
    return _stock_list_cache


if __name__ == "__main__":
    # 테스트 실행
    print("=" * 60)
    print("The Beat - 종목명 매칭 테스트")
    print("=" * 60)
    
    # 종목 리스트 가져오기
    stocks = get_all_listed_stocks()
    print(f"\n전체 종목 수: {len(stocks)}")
    print(f"샘플 종목 (처음 5개):")
    for stock in stocks[:5]:
        print(f"  - {stock['name']} ({stock['ticker']}) [{stock['market']}]")
    
    # 종목명 추출 테스트
    test_cases = [
        "삼성전자우 주가 급등, 외국인 순매수",
        "LG전자, SK하이닉스와 공급계약 체결",
        "카카오 단독 보도: 네이버와 협력 논의",
        "현대차 특징주 부각, 기아도 동반 상승"
    ]
    
    print("\n" + "=" * 60)
    print("종목명 추출 테스트 (Longest Match First)")
    print("=" * 60)
    
    for text in test_cases:
        print(f"\n원문: {text}")
        matched = extract_stock_names(text, stocks)
        if matched:
            print(f"추출된 종목:")
            for stock in matched:
                print(f"  ✓ {stock['name']} ({stock['ticker']}) [{stock['market']}]")
        else:
            print("  (종목명 없음)")
    
    print("\n" + "=" * 60)
