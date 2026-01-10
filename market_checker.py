"""
The Beat - 장 상태 확인 모듈
키움 REST API 웹소켓을 통해 장 운영 상태 및 개장 시간 확인
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from websockets import connect
from websockets.exceptions import WebSocketException

logger = logging.getLogger(__name__)

# =============================================================================
# 설정: 모의투자 / 실전투자 전환
# =============================================================================
# 실전투자로 진행할 시 True를 False로 변경
IS_PAPER_TRADING = True
# =============================================================================

class MarketStatusChecker:
    """키움 REST API 웹소켓을 사용한 장 상태 확인 클래스"""
    
    # 키움 REST API 웹소켓 URL
    # 운영: wss://api.kiwoom.com:10000/api/dostk/websocket
    # 모의투자: wss://mockapi.kiwoom.com:10000/api/dostk/websocket
    WEBSOCKET_URL_PROD = "wss://api.kiwoom.com:10000/api/dostk/websocket"
    WEBSOCKET_URL_MOCK = "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"
    
    # 장운영구분 코드 (215번 필드)
    MARKET_STATUS = {
        '0': '장시작전 알림(8:40~)',
        '3': '장시작(09:00)',
        '2': '장마감 알림(15:20~)',
        '4': '장마감(15:30)',
        '8': '정규장마감(15:30 이후)',
        '9': '전체장마감(18:00 이후)',
        'a': '시간외 종가매매 시작(15:40)',
        'b': '시간외 종가매매 종료(16:00)',
        'c': '시간외 단일가 시작(16:00)',
        'd': '시간외 단일가 종료(18:00)',
        'e': '선옵 장마감전 동시호가 종료',
        'f': '선물옵션 장운영시간 알림',
        'o': '선옵 장시작',
        's': '선옵 장마감전 동시호가 시작',
        'P': 'NXT 프리마켓 시작',
        'Q': 'NXT 프리마켓 종료',
        'R': 'NXT 메인마켓 시작',
        'S': 'NXT 메인마켓 종료',
        'T': 'NXT 에프터마켓 단일가 시작',
        'U': 'NXT 에프터마켓 시작',
        'V': 'NXT 에프터마켓 종료'
    }
    
    def __init__(self, is_paper_trading=True):
        """
        Args:
            is_paper_trading (bool): True=모의투자, False=실전투자 (디폴트: True)
        """
        load_dotenv()
        
        # 모의투자 / 실전투자 선택
        # 1순위: 파라미터, 2순위: 환경변수, 3순위: 디폴트(모의투자)
        if 'KIWOOM_USE_MOCK' in os.environ:
            self.is_paper_trading = os.getenv('KIWOOM_USE_MOCK', 'true').lower() == 'true'
        else:
            self.is_paper_trading = is_paper_trading
        
        # 웹소켓 URL 설정
        self.websocket_url = self.WEBSOCKET_URL_MOCK if self.is_paper_trading else self.WEBSOCKET_URL_PROD
        
        # 키움 API 인증 정보 (실전/모의투자 분리)
        if self.is_paper_trading:
            # 모의투자
            self.app_key = os.getenv('KIWOOM_PAPER_APP_KEY', '')
            self.app_secret = os.getenv('KIWOOM_PAPER_APP_SECRET', '')
        else:
            # 실전투자
            self.app_key = os.getenv('KIWOOM_REAL_APP_KEY', '')
            self.app_secret = os.getenv('KIWOOM_REAL_APP_SECRET', '')
        
        # Access Token (필요시 환경변수에서 로드)
        token_key = 'KIWOOM_PAPER_ACCESS_TOKEN' if self.is_paper_trading else 'KIWOOM_REAL_ACCESS_TOKEN'
        self.access_token = os.getenv(token_key, '')
        
        self.market_open = None  # 장 개장 여부
        self.market_time = None  # 장 시작 시간 (090000 or 100000)
        self.market_status_code = None  # 장운영구분 코드
        
        logger.info(f"키움 WebSocket 모드: {'🎓 모의투자' if self.is_paper_trading else '💰 실전투자'}")
        logger.info(f"WebSocket URL: {self.websocket_url}")
        logger.info(f"APP KEY: {self.app_key[:20]}...")
        
    async def _wait_for_market_data(self, websocket, timeout=10):
        """웹소켓에서 0s 데이터 수신 대기"""
        try:
            async with asyncio.timeout(timeout):
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        # trnm이 'REAL'이고 data 리스트가 있는 경우
                        if data.get('trnm') == 'REAL' and 'data' in data:
                            for item_data in data['data']:
                                # type이 '0s'인 데이터만 처리
                                if item_data.get('type') == '0s':
                                    values = item_data.get('values', {})
                                    
                                    # 215: 장운영구분, 20: 체결시간, 214: 장시작예상잔여시간
                                    status_code = values.get('215', '')
                                    current_time = values.get('20', '')
                                    remaining_time = values.get('214', '')
                                    
                                    if status_code:
                                        logger.info(f"장운영구분 수신: {status_code} ({self.MARKET_STATUS.get(status_code, '알수없음')})")
                                        logger.info(f"체결시간: {current_time}")
                                        logger.info(f"장시작예상잔여시간: {remaining_time}")
                                        
                                        self.market_status_code = status_code
                                        self.market_time = current_time
                                        
                                        # 장 개장 여부 판단
                                        # 0, 3 = 장 개장 관련, 8, 9, b, d = 장 종료 관련
                                        if status_code in ['0', '3', 'f', 'o', 'P', 'R', 'U']:
                                            self.market_open = True
                                        elif status_code in ['8', '9', 'b', 'd', 'Q', 'S', 'V']:
                                            self.market_open = False
                                        else:
                                            # 기타 상태는 장중으로 간주
                                            self.market_open = True
                                        
                                        # 데이터 수신 완료, 루프 종료
                                        return True
                                
                    except json.JSONDecodeError:
                        logger.debug(f"JSON 파싱 실패: {message}")
                        continue
                    except Exception as e:
                        logger.error(f"메시지 처리 중 오류: {e}")
                        continue
                        
        except asyncio.TimeoutError:
            logger.warning(f"{timeout}초 동안 응답 없음. 타임아웃 발생")
            return False
        except Exception as e:
            logger.error(f"데이터 수신 중 오류: {e}")
            return False
            
        return False
    
    async def check_market_status(self):
        """
        장 상태 확인 (단발성 웹소켓 연결)
        
        Returns:
            tuple: (장개장여부: bool, 개장시간: str, 상태코드: str)
                   실패 시 (None, None, None)
        """
        try:
            logger.info("키움 REST API 웹소켓 연결 중...")
            logger.info(f"URL: {self.websocket_url}")
            
            # 헤더 설정 (인증 토큰이 있는 경우)
            extra_headers = {}
            if self.access_token:
                extra_headers['Authorization'] = f'Bearer {self.access_token}'
            if self.app_key:
                extra_headers['appkey'] = self.app_key
            if self.app_secret:
                extra_headers['appsecret'] = self.app_secret
            
            async with connect(
                self.websocket_url,
                extra_headers=extra_headers if extra_headers else None
            ) as websocket:
                logger.info("웹소켓 연결 성공")
                
                # 0s (장시작시간) 구독 요청
                subscribe_message = {
                    "trnm": "REG",  # 등록
                    "grp_no": "1",
                    "refresh": "1",  # 기존 등록 유지
                    "data": [{
                        "item": [""],  # 빈 문자열 (시장 전체)
                        "type": ["0s"]  # 장시작시간 TR
                    }]
                }
                
                await websocket.send(json.dumps(subscribe_message))
                logger.info("0s 타입 구독 요청 전송 (장시작시간)")
                
                # 데이터 수신 대기
                success = await self._wait_for_market_data(websocket, timeout=10)
                
                if success:
                    logger.info(f"장 상태 확인 완료 - 개장: {self.market_open}, 시간: {self.market_time}")
                else:
                    logger.warning("장 상태 확인 실패 - 기본값 사용")
                    
        except WebSocketException as e:
            logger.error(f"웹소켓 연결 오류: {e}")
        except Exception as e:
            logger.error(f"장 상태 확인 중 예외 발생: {e}", exc_info=True)
        
        # 결과 반환
        return (self.market_open, self.market_time, self.market_status_code)
    
    def get_market_open_time_formatted(self):
        """개장 시간을 사람이 읽기 편한 형식으로 반환"""
        # 장운영구분에 따라 개장 시간 추론
        if self.market_status_code:
            if self.market_status_code in ['3', 'o']:  # 장시작
                return "9시"  # 일반적으로 9시
            elif self.market_status_code == 'f':  # 선물옵션 조기개장
                return "10시"  # 또는 필요시 market_time에서 파싱
        
        # market_time에서 파싱 시도 (HHMMSS 형식)
        if self.market_time and len(self.market_time) >= 6:
            try:
                hour = int(self.market_time[:2])
                if 8 <= hour <= 18:  # 정상 범위 확인
                    return f"{hour}시"
            except:
                pass
        
        return "9시"  # 기본값


async def check_market_status_once(is_paper_trading=None):
    """
    장 상태를 한 번만 확인하는 헬퍼 함수
    
    Args:
        is_paper_trading (bool, optional): True=모의투자, False=실전투자
                                          None이면 IS_PAPER_TRADING 상수 사용
    
    Returns:
        dict: {
            'is_open': bool,  # 장 개장 여부
            'open_time': str,  # 개장 시간 (예: "9시", "10시")
            'status_code': str,  # 장운영구분 코드
            'status_name': str  # 장운영구분 명칭
        }
    """
    # is_paper_trading이 None이면 상수 사용
    if is_paper_trading is None:
        is_paper_trading = IS_PAPER_TRADING
    
    checker = MarketStatusChecker(is_paper_trading=is_paper_trading)
    is_open, market_time, status_code = await checker.check_market_status()
    
    # 실패 시 기본값 (평일 9시 개장으로 가정)
    if is_open is None:
        logger.warning("장 상태 확인 불가. 기본값(9시 개장)으로 진행합니다.")
        return {
            'is_open': True,
            'open_time': '9시',
            'status_code': '0',
            'status_name': '장 시작 전 (기본값)'
        }
    
    return {
        'is_open': is_open,
        'open_time': checker.get_market_open_time_formatted(),
        'status_code': status_code or '0',
        'status_name': MarketStatusChecker.MARKET_STATUS.get(status_code, '알수없음')
    }


if __name__ == "__main__":
    # 테스트 실행
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("장 상태 확인 테스트")
    print("=" * 60)
    
    result = asyncio.run(check_market_status_once())
    
    print(f"\n개장 여부: {result['is_open']}")
    print(f"개장 시간: {result['open_time']}")
    print(f"상태 코드: {result['status_code']}")
    print(f"상태 명칭: {result['status_name']}")
    print("=" * 60)
