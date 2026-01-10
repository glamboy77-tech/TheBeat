"""
The Beat - Redis 송신 모듈
분석된 뉴스를 Redis 리스트로 전송하고 중복 방지
"""

import os
import json
import hashlib
import logging
from typing import Dict, List, Optional
from datetime import datetime
import redis
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class TheBeatSender:
    """Redis 뉴스 송신 및 중복 방지"""
    
    def __init__(self):
        """Redis 클라이언트 초기화"""
        load_dotenv()
        
        host = os.getenv('REDIS_HOST', 'localhost')
        port = int(os.getenv('REDIS_PORT', 6379))
        password = os.getenv('REDIS_PASSWORD', None)
        
        # 비밀번호가 빈 문자열이면 None으로 처리
        if password == '':
            password = None
        
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                password=password,
                decode_responses=True,  # 문자열로 자동 디코딩
                socket_connect_timeout=5
            )
            
            # 연결 테스트
            self.redis_client.ping()
            logger.info(f"Redis 연결 성공: {host}:{port}")
            
        except redis.ConnectionError as e:
            logger.error(f"Redis 연결 실패: {e}")
            raise
        except Exception as e:
            logger.error(f"Redis 초기화 오류: {e}")
            raise
    
    def _generate_hash(self, title: str) -> str:
        """
        뉴스 제목으로 고유 해시 생성
        
        Args:
            title: 뉴스 제목
            
        Returns:
            SHA256 해시 문자열
        """
        return hashlib.sha256(title.encode('utf-8')).hexdigest()
    
    def _is_duplicate(self, news_hash: str) -> bool:
        """
        중복 뉴스 체크
        
        Args:
            news_hash: 뉴스 해시
            
        Returns:
            중복이면 True, 아니면 False
        """
        return self.redis_client.sismember('thebeat:sent_news_hashes', news_hash)
    
    def _mark_as_sent(self, news_hash: str, ttl_days: int = 7):
        """
        뉴스를 전송 완료로 표시 (TTL 설정)
        
        Args:
            news_hash: 뉴스 해시
            ttl_days: 중복 방지 기간 (일)
        """
        # SET에 추가
        self.redis_client.sadd('thebeat:sent_news_hashes', news_hash)
        
        # TTL 설정 (초 단위)
        ttl_seconds = ttl_days * 24 * 60 * 60
        self.redis_client.expire('thebeat:sent_news_hashes', ttl_seconds)
    
    def blast_news(self, title: str, grade: str, stock: str = "", reference_url: str = "") -> bool:
        """
        뉴스를 Redis 리스트로 전송
        
        Args:
            title: 뉴스 제목
            grade: 등급 (S, A, B, C)
            stock: 종목명 (선택)
            reference_url: 원문 링크 (선택)
            
        Returns:
            전송 성공 시 True, 중복이거나 실패 시 False
        """
        # S, A 등급만 전송
        if grade not in ['S', 'A']:
            logger.debug(f"등급 필터링: {grade} 등급은 전송하지 않음 (제목: {title[:30]}...)")
            return False
        
        # 중복 체크
        news_hash = self._generate_hash(title)
        if self._is_duplicate(news_hash):
            logger.info(f"중복 뉴스 감지: {title[:50]}...")
            return False
        
        # Redis 리스트에 푸시
        news_data = {
            "title": title,
            "grade": grade,
            "stock": stock,
            "reference_url": reference_url,
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # JSON 문자열로 변환하여 리스트에 푸시
            self.redis_client.lpush('thebeat:news', json.dumps(news_data, ensure_ascii=False))
            
            # 중복 방지 해시 저장
            self._mark_as_sent(news_hash)
            
            logger.info(f"[{grade}] 뉴스 전송 완료: {stock} - {title[:40]}...")
            return True
            
        except Exception as e:
            logger.error(f"Redis 전송 실패: {e}")
            return False
    
    def blast_news_batch(self, analysis_results: List[Dict]) -> Dict[str, int]:
        """
        분석 결과를 일괄 전송
        
        Args:
            analysis_results: analyzer.py의 분석 결과 리스트
            
        Returns:
            전송 통계 {"sent": 전송 성공 건수, "filtered": 필터링 건수, "duplicated": 중복 건수}
        """
        stats = {"sent": 0, "filtered": 0, "duplicated": 0}
        
        for result in analysis_results:
            title = result.get('point', '')  # 투자 포인트를 제목으로 사용
            grade = result.get('grade', 'C')
            stock = result.get('stock', '')
            reference_url = result.get('reference_url', '')
            
            # 제목이 비어있으면 스킵
            if not title:
                logger.warning(f"제목이 없는 뉴스 스킵: {result}")
                stats['filtered'] += 1
                continue
            
            # 등급 필터링
            if grade not in ['S', 'A']:
                stats['filtered'] += 1
                continue
            
            # 중복 체크
            news_hash = self._generate_hash(title)
            if self._is_duplicate(news_hash):
                stats['duplicated'] += 1
                continue
            
            # 전송
            if self.blast_news(title, grade, stock, reference_url):
                stats['sent'] += 1
        
        logger.info(f"일괄 전송 완료: {stats}")
        return stats
    
    def get_recent_news(self, count: int = 10) -> List[Dict]:
        """
        최근 전송된 뉴스 조회
        
        Args:
            count: 조회할 뉴스 개수
            
        Returns:
            뉴스 리스트
        """
        try:
            news_list = self.redis_client.lrange('thebeat:news', 0, count - 1)
            return [json.loads(news) for news in news_list]
        except Exception as e:
            logger.error(f"뉴스 조회 실패: {e}")
            return []
    
    def clear_sent_hashes(self):
        """전송 이력 초기화 (테스트용)"""
        self.redis_client.delete('thebeat:sent_news_hashes')
        logger.warning("전송 이력이 초기화되었습니다.")
    
    def get_stats(self) -> Dict[str, int]:
        """
        Redis 통계 조회
        
        Returns:
            {"total_news": 전체 뉴스 수, "total_hashes": 중복 방지 해시 수}
        """
        return {
            "total_news": self.redis_client.llen('thebeat:news'),
            "total_hashes": self.redis_client.scard('thebeat:sent_news_hashes')
        }


if __name__ == "__main__":
    # 테스트 코드
    print("=" * 60)
    print("The Beat - Redis 송신 테스트")
    print("=" * 60)
    
    try:
        sender = TheBeatSender()
        
        # 더미 뉴스 전송 테스트
        test_cases = [
            {"title": "[단독] 삼성전자, 레인보우로보틱스 100% 인수", "grade": "S", "stock": "레인보우로보틱스"},
            {"title": "카카오, 2분기 실적 서프라이즈", "grade": "A", "stock": "카카오"},
            {"title": "일반 IR 뉴스", "grade": "C", "stock": "테스트"},  # 필터링됨
            {"title": "[단독] 삼성전자, 레인보우로보틱스 100% 인수", "grade": "S", "stock": "레인보우로보틱스"},  # 중복
        ]
        
        print("\n[테스트 1] 개별 전송")
        for i, case in enumerate(test_cases, 1):
            result = sender.blast_news(
                title=case['title'],
                grade=case['grade'],
                stock=case['stock']
            )
            print(f"{i}. {'✓' if result else '✗'} {case['title'][:30]}... [{case['grade']}]")
        
        print("\n[테스트 2] 통계 조회")
        stats = sender.get_stats()
        print(f"총 뉴스: {stats['total_news']}건")
        print(f"중복 방지 해시: {stats['total_hashes']}개")
        
        print("\n[테스트 3] 최근 뉴스 조회")
        recent = sender.get_recent_news(3)
        for news in recent:
            print(f"- [{news['grade']}] {news['stock']}: {news['title'][:40]}...")
        
        print("\n✓ 테스트 완료")
        
    except redis.ConnectionError:
        print("\n⚠️ Redis 서버에 연결할 수 없습니다.")
        print("해결 방법:")
        print("  1. Redis 설치: https://redis.io/download")
        print("  2. Windows: https://github.com/microsoftarchive/redis/releases")
        print("  3. 서버 시작: redis-server")
        print("  4. .env 파일의 REDIS_HOST, REDIS_PORT 확인")
    except Exception as e:
        print(f"\n⚠️ 오류 발생: {e}")
