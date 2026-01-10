"""
The Beat - 유틸리티 모듈
날짜 및 시간 계산, 종목명 매칭 등 공통 기능 제공
"""

from datetime import datetime, timedelta
from pykrx import stock
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_last_trading_day(base_date=None):
    """
    가장 최근 주식 시장이 열렸던 영업일을 반환
    
    Args:
        base_date (datetime, optional): 기준 날짜. None이면 현재 시간 기준.
    
    Returns:
        str: 영업일 (YYYYMMDD 형식)
    """
    if base_date is None:
        today = datetime.now()
    else:
        today = base_date
    
    # 최대 10일 전까지 확인 (연휴 대비)
    for i in range(10):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%Y%m%d")
        
        if check_date.weekday() >= 5:
            continue
            
        try:
            # pykrx의 내부 로깅(root logger 사용)으로 인한 노이즈/에러 방지
            # 임시로 root logger 레벨을 CRITICAL로 올림
            root_logger = logging.getLogger()
            orig_level = root_logger.level
            root_logger.setLevel(logging.CRITICAL)
            
            try:
                # 데이터 존재 여부로 영업일 판단
                df = stock.get_index_ohlcv(date_str, date_str, "1001")  # KOSPI 지수
            finally:
                root_logger.setLevel(orig_level)
            
            if df is not None and not df.empty:
                logger.info(f"마지막 영업일: {date_str}")
                return date_str
        except Exception as e:
            logger.debug(f"{date_str} 확인 중 오류: {e}")
            continue
    
    # API 실패 시 단순 평일 계산 (fallback)
    logger.warning("pykrx로 영업일을 확인하지 못했습니다. 단순 평일 기준으로 계산합니다.")
    if base_date is None:
        check_date = datetime.now()
    else:
        check_date = base_date
        
    while True:
        # 0=월, 6=일. 주말(5,6)이면 하루 전으로
        if check_date.weekday() >= 5:
            check_date -= timedelta(days=1)
        else:
            # 기준일(base_date)이 주어지고 그게 평일이라면, 
            # "장전 브리핑" 시점(08:20)에서는 "전일" 장 마감을 찾아야 함.
            # 만약 base_date가 오늘(평일) 08:20이라면, 영업일은 어제여야 함.
            # get_last_trading_day의 의미가 "데이터 수집 시작일"을 찾기 위한 것이므로
            # 오늘이 평일이어도 어제로 넘어가야 하는지, 아니면 시간대별로 다른지 로직 필요.
            # 여기서는 단순히 역추적하다 만난 첫 평일을 리턴하도록 유지하되,
            # base_date 자체가 평일이면 base_date를 리턴하는 기존 로직 유지
            # (get_data_collection_timerange에서 하루 빼는 로직 등이 있을 수 있음)
            
            # 개선: 입력된 base_date보다 '이전'의 영업일을 원한다면 logic 변경 필요하지만
            # get_last_trading_day는 "가장 최근"이므로 오늘 포함이 맞음.
            
            # 다만, 시뮬레이션 시 "오늘 아침 8시" 기준이라면 "어제"가 마지막 영업일이어야 함.
            return check_date.strftime("%Y%m%d")


def get_data_collection_timerange(base_date=None):
    """
    데이터 수집 시작/종료 시간을 계산
    
    시작 시간: 마지막 영업일 오후 4시 (16:00)
    종료 시간: 현재 시간 (또는 base_date)
    
    주말/휴장일 고려:
    - 월요일 아침: 금요일 16:00부터 수집
    - 화~금 아침: 전일 16:00부터 수집
    
    Args:
        base_date (datetime, optional): 기준 시간. None이면 현재 시간.
                                      백테스트 시 '2026-01-02 08:20:00' 등으로 설정
    
    Returns:
        tuple: (start_datetime, end_datetime)
    """
    # 기준 시간 (종료 시간)
    if base_date is None:
        end_datetime = datetime.now()
    else:
        end_datetime = base_date
    
    # 마지막 영업일 찾기
    # 오전(9시 이전)에 실행되면 어제 기준으로 영업일 찾기
    search_date = end_datetime
    if end_datetime.hour < 9:
        # 오늘이 월요일이면 금요일, 화~금이면 전일을 찾아야 함
        search_date = end_datetime - timedelta(days=1)
    
    # 마지막 영업일 가져오기 (주말/공휴일 자동 스킵)
    last_trading_day_str = get_last_trading_day(search_date)
    last_trading_day = datetime.strptime(last_trading_day_str, "%Y%m%d")
    
    # 시작 시간: 마지막 영업일 16:00
    start_datetime = last_trading_day.replace(hour=16, minute=0, second=0, microsecond=0)
    
    # 디버그 로그
    logger.debug(f"end_datetime: {end_datetime}")
    logger.debug(f"search_date: {search_date}")
    logger.debug(f"last_trading_day: {last_trading_day}")
    
    logger.info(f"데이터 수집 범위: {start_datetime} ~ {end_datetime}")
    logger.info(f"수집 기간: {(end_datetime - start_datetime).total_seconds() / 3600:.1f}시간")
    
    return (start_datetime, end_datetime)


def format_datetime_for_api(dt):
    """
    datetime 객체를 API 요청용 문자열로 변환
    
    Args:
        dt (datetime): 변환할 datetime 객체
    
    Returns:
        str: YYYYMMDDHHMMSS 형식의 문자열
    """
    return dt.strftime("%Y%m%d%H%M%S")


def format_date_for_api(dt):
    """
    datetime 객체를 날짜 문자열로 변환
    
    Args:
        dt (datetime): 변환할 datetime 객체
    
    Returns:
        str: YYYYMMDD 형식의 문자열
    """
    return dt.strftime("%Y%m%d")


if __name__ == "__main__":
    # 테스트 실행
    print("=" * 60)
    print("The Beat - 시간 계산 테스트")
    print("=" * 60)
    
    # 마지막 영업일 확인
    last_day = get_last_trading_day()
    print(f"\n마지막 영업일: {last_day}")
    
    # 데이터 수집 시간 범위 확인
    start, end = get_data_collection_timerange()
    print(f"\n수집 시작: {start}")
    print(f"수집 종료: {end}")
    print(f"수집 기간: {(end - start).total_seconds() / 3600:.1f}시간")
    
    # API 형식 변환 테스트
    print(f"\nAPI 날짜 형식: {format_date_for_api(start)}")
    print(f"API 시간 형식: {format_datetime_for_api(start)}")
    print("=" * 60)
