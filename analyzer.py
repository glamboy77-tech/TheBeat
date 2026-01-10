"""
The Beat - AI 분석 모듈
Gemini 2.5 Flash API를 사용하여 뉴스/공시 호재/악재 분석
"""

import os
import logging
import json
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Pydantic 모델 정의
class StockAnalysis(BaseModel):
    stock: str = Field(description="종목명")
    grade: str = Field(description="재료 강도 (S, A, B, C)")
    sector: str = Field(description="관련 테마/섹터")
    point: str = Field(description="투자 포인트 및 대응 전략 (한 줄 요약)")
    reason: str = Field(description="등급 판단 근거 (왜 이 등급을 부여했는지)")
    reference_url: str = Field(description="관련 뉴스 또는 공시의 원문 링크 (반드시 제공된 데이터 내의 링크를 사용할 것)")

class AnalysisResult(BaseModel):
    analysis_list: List[StockAnalysis]

class GeminiAnalyzer:
    """Gemini AI 분석기"""
    
    def __init__(self):
        load_dotenv()
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
            
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"
        
        logger.info(f"GeminiAnalyzer 초기화 완료 (모델: {self.model_name})")

    def _create_prompt(self, news_list: List[Dict], disclosure_list: List[Dict]) -> str:
        """분석용 프롬프트 생성"""
        
        data_text = "### 1. 뉴스 데이터 ###\n"
        if news_list:
            for item in news_list:
                stocks = ", ".join([s['name'] for s in item.get('stocks', [])])
                data_text += f"- 제목: {item['title']}\n  관련종목: {stocks}\n  링크: {item['link']}\n  내용: {item['description']}\n\n"
        else:
            data_text += "(뉴스 데이터 없음)\n\n"
            
        data_text += "### 2. 공시 데이터 ###\n"
        if disclosure_list:
            for item in disclosure_list:
                stock_name = item['stock']['name']
                # DART 링크 생성
                rcept_no = item.get('rcept_no', '')
                dart_link = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else ""
                
                data_text += f"- 기업: {item['corp_name']}\n  종목: {stock_name}\n  보고서: {item['report_nm']}\n  링크: {dart_link}\n  키워드: {item['matched_keyword']}\n\n"
        else:
            data_text += "(공시 데이터 없음)\n"
            
        return data_text

    def analyze(self, news_list: List[Dict], disclosure_list: List[Dict]) -> List[Dict]:
        """
        뉴스 및 공시 데이터 분석
        
        Returns:
            List[Dict]: 분석 결과 리스트
        """
        if not news_list and not disclosure_list:
            logger.warning("분석할 데이터가 없습니다.")
            return []
            
        prompt_content = self._create_prompt(news_list, disclosure_list)
        
        system_instruction = """
너는 15년 경력의 대한민국 전업 주식 데이트레이더이자, 공시 해석 전문가야.
주어진 뉴스와 공시를 분석해 장전/장중 브리핑을 작성하라.
한국 시장 특유의 '세력 매집', '재료 소멸', '재탕 뉴스'를 날카롭게 파악해 분석해줘.

[등급 분류 세부 기준]
- S (초대형): 다음 키워드가 포함된 초대형 재료만 S 등급 부여
  * '단독' 보도 (타 언론사 미보도)
  * '세계 최초' 기술 개발/상용화
  * '공급계약 체결' + 계약 규모가 전년 매출액 대비 50% 이상
  * '삼성전자', 'LG', '현대차', '애플', 'NVIDIA'와 직접 협업/공급 계약
  * 대기업 대상 제3자 배정 유상증자, 지분 매각(M&A)
  * 상한가 안착 가능성 90% 이상

- A (강력): 다음 키워드가 포함된 강력 재료는 A 등급 부여
  * '특징주' 선정 (언론사/증권사 명시)
  * '상한가 근접', '급등'
  * '정부 정책 발표' (국책과제, 정부 지원 사업)
  * '실적 어닝 서프라이즈' (컨센서스 대비 20% 이상 초과)
  * 대규모 공급계약 (전년 매출 30% 이상)
  * 시초가 갭 15~20% 형성 가능

- B (단발): 단순 MOU, 일반 국책과제 선정, 찌라시성 특징주 기사, 이미 알려진 재료의 재부각. 갭상승 후 윗꼬리 달 확률 높음.

- C (약함): 실적 발표(예상치 부합), 단순 IR, 장종료 후 이미 반영된 공시.

[분석 프로세스] - 반드시 이 순서대로 생각하고 출력해:
1. Re-check: 이 뉴스가 오늘 처음 나온 것인가? 아니면 어제나 며칠 전 뉴스의 재탕인가? (재탕이면 무조건 C등급)
2. Keyword Match: S/A 등급 키워드가 포함되어 있는가? (없으면 B 이하)
3. Reasoning: 재료가 해당 종목의 시가총액 대비 얼마나 큰 돈이 되는가? (시총 대비 계약규모 등 고려)
4. Result: 위 기준에 따른 등급(S~C), 섹터, 투자 포인트 작성.

[출력 요구사항]
- stock: 종목명
- grade: S/A/B/C 등급
- sector: 세부 테마명
- point: 간결하고 강력한 매매 전략 ("~함", "~할 것" 형식)
- reason: 왜 이 등급을 부여했는지 판단 근거 요약 (키워드 매칭 결과 포함)
- reference_url: 원문 링크 (반드시 제공된 데이터 내의 링크 사용)

[주의사항]
- S/A 등급은 반드시 위의 키워드 기준을 충족해야 함. (남발 시 봇의 신뢰도 하락)
- 종목과 관련 없는 뉴스는 분석 결과에서 제외해.
- 데이터 중복 시 가장 중요한 내용으로 통합.
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=AnalysisResult,
                    temperature=0.3, # 분석의 일관성을 위해 낮게 설정
                )
            )
            
            # Pydantic 모델을 딕셔너리로 변환
            if response.parsed:
                result = response.parsed.model_dump()
                return result.get('analysis_list', [])
            else:
                logger.error("응답 파싱 실패: 파싱된 결과가 없습니다.")
                return []

        except Exception as e:
            logger.error(f"Gemini 분석 중 오류 발생: {e}")
            return []

if __name__ == "__main__":
    # 테스트 코드
    print("=" * 60)
    print("The Beat - AI 분석 테스트")
    print("=" * 60)
    
    # 더미 데이터 생성
    dummy_news = [
        {
            'title': '삼성전자, 레인보우로보틱스 지분 100% 인수 검토',
            'description': '삼성전자가 로봇 사업 강화를 위해 레인보우로보틱스를 완전 자회사화 할 것이라는 보도.',
            'stocks': [{'name': '레인보우로보틱스'}, {'name': '삼성전자'}]
        },
        {
            'title': '[단독] 카카오, 2분기 영업익 3000억... 서프라이즈',
            'description': '카카오가 광고 매출 회복으로 시장 컨센서스를 상회하는 실적을 기록했다.',
            'stocks': [{'name': '카카오'}]
        }
    ]
    
    dummy_disclosure = [
        {
            'corp_name': '에코프로비엠',
            'report_nm': '주요사항보고서(유상증자결정)',
            'matched_keyword': '유상증자',
            'stock': {'name': '에코프로비엠'}
        }
    ]
    
    try:
        analyzer = GeminiAnalyzer()
        results = analyzer.analyze(dummy_news, dummy_disclosure)
        
        print(f"\n분석 결과: {len(results)}건")
        for item in results:
            print("-" * 40)
            print(f"[{item['grade']}] {item['stock']}")
            print(f"섹터: {item['sector']}")
            print(f"포인트: {item['point']}")
            
    except Exception as e:
        print(f"\n⚠️ 오류 발생: {e}")
        print("GEMINI_API_KEY가 .env 파일에 올바르게 설정되었는지 확인하세요.")
