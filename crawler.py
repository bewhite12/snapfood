import os
import json
import urllib.parse
from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client, Client

# 1. 환경 설정 파일(.env) 로드
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
COUPANG_PARTNER_ID = os.environ.get("COUPANG_PARTNER_ID")

# --- 클라이언트 초기화 ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# --- 2. Gemini 요청 JSON 스키마 ---
SCHEMA = {
    # ... (V5와 동일한 JSON 스키마 내용) ...
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "제목 최적화 (예: [백종원] 김치찌개)"},
        "summary": {"type": "string", "description": "15자 이내의 한 줄 요약"},
        "ingredients_json": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "amount": {"type": "string", "description": "g 또는 ml 단위로 표기 (예: 300g)"}
                },
                "required": ["name", "amount"]
            },
            "description": "요리에 필요한 핵심 재료 목록 및 계량"
        },
        "method_text": {"type": "string", "description": "숫자(1, 2, 3...)를 붙인 간결한 조리 순서"},
        "tips": {"type": "string", "description": "쉐프가 강조한 요리 팁"},
        "group_id": {"type": "string", "description": "메뉴 그룹 ID (예: Kimchi_Jjigae)"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "상황별, 재료별 태그 (예: 한식, 찌개, 돼지고기)"},
        "video_url": {"type": "string", "description": "참고한 유튜브 영상 URL 주소"} 
    },
    "required": ["title", "summary", "ingredients_json", "method_text", "tags", "video_url"]
}


# --- 3. 쿠팡 검색 링크 생성 함수 ---
def generate_coupang_search_link(ingredient_name: str, partner_id: str) -> str:
    search_term = urllib.parse.quote_plus(ingredient_name)
    return f"https://www.coupang.com/np/search?q={search_term}&channel=affiliate&affid={partner_id}"


def run_snap_crawler_v6(search_query: str):
    """단일 검색 쿼리를 실행하고 데이터를 수집 및 저장합니다."""
    print(f"--- 🔍 '{search_query}' 검색 시작 ---")
    
    try:
        # 1) Gemini에게 레시피 정보 요청
        prompt = (
            f"유튜브나 신뢰할 수 있는 소스에서 '{search_query}'의 레시피를 분석해. "
            f"결과물에 반드시 이 레시피의 **유튜브 영상 URL**을 포함하고, "
            f"내가 정의한 SCHEMA에 맞춰 JSON 형식으로만 한국어로 출력해줘. "
            f"재료 양은 최대한 'g' 단위로 변환해줘."
        )
        
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SCHEMA
            )
        )
        
        ai_data = json.loads(response.text)
        
        # 2) 재료 JSON에 쿠팡 링크 삽입 (수익화 로직)
        modified_ingredients = []
        for item in ai_data['ingredients_json']:
            ingredient_name = item['name']
            item['purchase_link'] = generate_coupang_search_link(ingredient_name, COUPANG_PARTNER_ID) 
            modified_ingredients.append(item)
        
        # 3) DB에 저장할 최종 데이터 구조
        final_data = {
            "title": ai_data['title'],
            "summary": ai_data['summary'],
            "ingredients_json": modified_ingredients,
            "method_text": ai_data['method_text'],
            "tips": ai_data.get('tips', '별도 팁 없음'),
            "group_id": ai_data['group_id'],
            "tags": ai_data['tags'],
            "video_url": ai_data['video_url'],
            "restaurant_name": None,
            "store_link": None
        }
        
        # 4) Supabase DB에 데이터 삽입
        supabase.table('recipes').insert(final_data).execute()
        
        print(f"--- ✅ '{final_data['title']}' 저장 성공! ---")
        return True # 성공 반환
        
    except Exception as e:
        error_message = str(e)
        print(f"❌ '{search_query}' 데이터 처리 또는 저장 실패: {error_message}")
        return False # 실패 반환


# --- 실행 부분 (chef_list.txt 파일 읽어서 전체 실행) ---
if __name__ == "__main__":
    if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY, COUPANG_PARTNER_ID]):
        print("❌ 오류: .env 파일에 키가 누락되었습니다. 키를 확인해주세요.")
    else:
        try:
            # chef_list.txt 파일에서 쿼리 목록을 읽어옵니다.
            with open('chef_list.txt', 'r', encoding='utf-8') as f:
                search_queries = [line.strip() for line in f if line.strip()]
            
            print(f"\n--- 🤖 Snap Food 로봇 V6 가동: 총 {len(search_queries)}개 쿼리 실행 ---")
            
            success_count = 0
            fail_count = 0
            
            for query in search_queries:
                if run_snap_crawler_v6(query):
                    success_count += 1
                else:
                    fail_count += 1

            print(f"\n=======================================================")
            print(f"🎉 배치 작업 완료: 성공 {success_count}개, 실패 {fail_count}개")
            print(f"=======================================================")

        except FileNotFoundError:
            print("❌ 오류: 'chef_list.txt' 파일을 찾을 수 없습니다. 파일을 생성했는지 확인해주세요.")
        except Exception as e:
            print(f"❌ 심각한 오류 발생: {e}")