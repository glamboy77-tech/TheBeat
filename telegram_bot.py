"""
The Beat - 텔레그램 전송 모듈
분석 결과를 마크다운 형식으로 변환하여 텔레그램으로 전송
"""

import asyncio
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class TelegramSender:
    """텔레그램 메시지 전송 클래스"""
    
    # 등급별 이모지
    GRADE_EMOJI = {
        'S': '🚀',
        'A': '🔥',
        'B': '✅',
        'C': '💤'
    }
    
    def __init__(self):
        load_dotenv()
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.token or not self.chat_id:
            logger.warning("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.")
        
    def _escape_markdown(self, text: str) -> str:
        """MarkdownV2 특수문자 이스케이프"""
        # MarkdownV2에서 이스케이프해야 할 문자들
        chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars:
            text = text.replace(char, f"\\{char}")
        return text

    def _format_report(self, analysis_results: list, report_date: datetime = None, market_open_time: str = "9시") -> str:
        """분석 결과를 마크다운 메시지로 변환
        
        Args:
            analysis_results: 분석 결과 리스트
            report_date: 브리핑 기준 날짜 (마지막 영업일). None이면 현재 날짜 사용
            market_open_time: 개장 시간 (예: "9시", "10시")
        """
        if not analysis_results:
            return "☕ *오늘 아침은 조용하네요\\.*\n무리한 매매는 금물입니다\\! 관망하며 기회를 노려보세요\\."
            
        # 브리핑 기준 날짜 사용 (마지막 영업일)
        if report_date is None:
            report_date = datetime.now()
        date_str = self._escape_markdown(report_date.strftime("%Y년 %m월 %d일"))
        safe_open_time = self._escape_markdown(market_open_time)
        
        message = f"📢 *The Beat 장전 브리핑* \\({date_str}\\)\n"
        message += f"🕐 오늘 개장 시간: *{safe_open_time}*\n\n"
        
        # 등급순 정렬 (S -> A -> B -> C)
        grade_order = {'S': 0, 'A': 1, 'B': 2, 'C': 3}
        sorted_results = sorted(analysis_results, key=lambda x: grade_order.get(x.get('grade', 'C'), 3))
        
        for item in sorted_results:
            stock = item.get('stock', '알수없음')
            grade = item.get('grade', 'C')
            sector = item.get('sector', '미분류')
            point = item.get('point', '-')
            url = item.get('reference_url', '')
            
            emoji = self.GRADE_EMOJI.get(grade, '💤')
            
            # 이스케이프 처리
            safe_stock = self._escape_markdown(stock)
            safe_grade = self._escape_markdown(grade)
            safe_sector = self._escape_markdown(sector)
            safe_point = self._escape_markdown(point)
            
            # 링크가 있는 경우 종목명에 링크 걸기
            if url:
                stock_line = f"{emoji} *[{safe_stock}]({url})* \\- *{safe_grade}등급*"
            else:
                stock_line = f"{emoji} *{safe_stock}* \\- *{safe_grade}등급*"
                
            message += f"{stock_line}\n"
            message += f"└ 🏷️ {safe_sector}\n"
            message += f"└ 💡 {safe_point}\n\n"
            
        message += "\\-\\-\\-\n"
        message += "⚠️ _이 정보는 투자 참고용이며, 투자의 책임은 본인에게 있습니다\\._"
        
        return message

    async def send_report(self, analysis_results: list, report_date: datetime = None, market_open_time: str = "9시"):
        """리포트 생성 및 전송
        
        Args:
            analysis_results: 분석 결과 리스트
            report_date: 브리핑 기준 날짜 (마지막 영업일). None이면 현재 날짜 사용
            market_open_time: 개장 시간 (예: "9시", "10시")
        """
        if not self.token or not self.chat_id:
            logger.error("텔레그램 토큰이 없어 메시지를 보낼 수 없습니다.")
            return

        message = self._format_report(analysis_results, report_date, market_open_time)
        
        try:
            bot = Bot(token=self.token)
            await bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
            logger.info("텔레그램 메시지 전송 완료")
            
        except TelegramError as e:
            logger.error(f"텔레그램 전송 실패: {e}")
    
    async def send_holiday_message(self, holiday_date: datetime):
        """휴장일 알림 메시지 전송
        
        Args:
            holiday_date: 휴장일 날짜
        """
        if not self.token or not self.chat_id:
            logger.error("텔레그램 토큰이 없어 메시지를 보낼 수 없습니다.")
            return
        
        day_name = ['월','화','수','목','금','토','일'][holiday_date.weekday()]
        date_str = self._escape_markdown(holiday_date.strftime("%Y년 %m월 %d일"))
        safe_day = self._escape_markdown(day_name)
        
        message = f"🌙 *휴장일 알림*\\n\\n"
        message += f"오늘 {date_str} \\({safe_day}\\)은 한국 거래소 *휴장일*입니다\\.\\n\\n"
        message += f"푹 쉬시고 다음 개장일에 만나요\\! 😊\\n\\n"
        message += f"\\-\\-\\-\\n"
        message += f"💤 _휴식도 투자의 일부입니다\\._"
        
        try:
            bot = Bot(token=self.token)
            await bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
            logger.info("휴장일 메시지 전송 완료")
            
        except TelegramError as e:
            logger.error(f"텔레그램 전송 실패: {e}")

if __name__ == "__main__":
    # 테스트
    dummy_data = [
        {
            'stock': '삼성전자',
            'grade': 'S',
            'sector': '반도체/M&A',
            'point': '초대형 M&A 공시로 점상 예상, 무조건 홀딩',
            'reference_url': 'https://n.news.naver.com/article/001/0000000001'
        },
        {
            'stock': '카카오',
            'grade': 'B',
            'sector': '플랫폼',
            'point': '실적 호조로 갭상승 출발 예상되나 차익실현 매물 주의',
            'reference_url': ''
        }
    ]
    
    sender = TelegramSender()
    
    # 비동기 실행을 위한 헬퍼
    async def test_run():
        print(f"메시지 미리보기:\n{'-'*40}\n{sender._format_report(dummy_data)}\n{'-'*40}")
        if sender.token:
            await sender.send_report(dummy_data)
        else:
            print("토큰이 없어 실제 전송은 생략합니다.")
            
    asyncio.run(test_run())
