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
너는 15년 경력의 전업 주식 데이트레이더야.
주어진 뉴스와 공시 데이터를 분석해서 장전 브리핑을 작성해야 해.
약세장에서도 수익을 낼 수 있는 날카로운 시각으로 분석해줘.

[분석 기준]
1. 재료 강도 (Grade):
   - S: 상한가 또는 점상 기대 (초대형 호재, 삼성전자 M&A 등)
   - A: 강력 호재, 시초가 20% 이상 시작 가능성
   - B: 단발성 호재, 시초가 5~10% 갭상승 후 하락 가능성 있음
   - C: 이미 반영되었거나 임팩트 약함 (보합 출발 예상)

2. 섹터 (Sector):
   - 해당 재료가 속한 현재 시장의 핫한 테마/섹터 명시

3. 투자 포인트 (Point):
   - 시초가 진입 여부, 손절 라인, 재료 소멸 시점 등을 포함하여 '한 줄'로 강력하게 제안
   - 말투는 "~함", "~할 것", "~보임" 등 간결한 전문가 말투 사용

[주의사항]
- 데이터 중복이 있을 경우 가장 중요한 내용 하나로 통합해서 분석
- 관련 없는 종목이 매칭된 경우 과감히 제외
- 'S'급 재료는 정말 확실한 경우에만 부여 (남발 금지)
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
