import os
import json
import urllib.parse
# 썸네일 파일 처리 및 Base64 디코딩을 위한 라이브러리 추가
import base64
from datetime import datetime 
import io 
# ---

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

# --- 상수 정의 ---
STORAGE_BUCKET_NAME = "snapfood-images" # Supabase Storage 버킷 이름

# --- 클라이언트 초기화 ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# --- 2. Gemini 요청 JSON 스키마 (image_prompt 사용) ---
SCHEMA = {
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
        "video_url": {"type": "string", "description": "참고한 유튜브 영상 URL 주소"},
        "image_prompt": {"type": "string", "description": "요리 제목과 분위기에 맞는, 디자인팀이 사용할 고화질 썸네일 이미지 생성 프롬프트"}
    },
    "required": ["title", "summary", "ingredients_json", "method_text", "tags", "video_url", "image_prompt"] 
}


# --- 3. 쿠팡 검색 링크 생성 함수 ---
def generate_coupang_search_link(ingredient_name: str, partner_id: str) -> str:
    search_term = urllib.parse.quote_plus(ingredient_name)
    return f"https://www.coupang.com/np/search?q={search_term}&channel=affiliate&affid={partner_id}"

# --- 4. (가상) 이미지 생성 및 더미 데이터 반환 함수 ---
def generate_dummy_image_data(title: str):
    """(가상) Gemini 이미지 생성 API를 대체하는 더미 데이터 생성 함수"""
    # 1x1 투명 PNG의 Base64 데이터를 디코딩하여 바이너리 데이터를 반환합니다.
    dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQYV2P4//8/AwAI/gM6G/yWAAAAAElFTkSuQmCC"
    return base64.b64decode(dummy_b64)


def run_snap_crawler_v9_1(search_query: str):
    """단일 검색 쿼리를 실행하고 데이터를 수집 및 저장합니다."""
    print(f"--- 🔍 '{search_query}' 검색 시작 ---")
    
    # 최종 데이터 구조 초기화
    final_data = {
        "title": None,
        "summary": None,
        "ingredients_json": [],
        "method_text": None,
        "tips": None,
        "group_id": None,
        "tags": None,
        "video_url": None,
        "image_prompt": None,
        "restaurant_name": None,
        "store_link": None,
        "thumbnail_url": None # 최종 이미지 URL이 들어갈 곳
    }

    try:
        # 1) Gemini에게 레시피 정보 및 이미지 프롬프트 요청
        prompt = (
            f"유튜브나 신뢰할 수 있는 소스에서 '{search_query}'의 레시피를 분석해. "
            f"결과물에 반드시 이 레시피의 **유튜브 영상 URL**을 포함하고, "
            f"이 요리에 대한 **상세하고 예술적인 썸네일 이미지 생성 프롬프트**를 추가해줘. "
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
        
        # 3) DB에 저장할 데이터 매핑
        final_data.update({
            "title": ai_data['title'],
            "summary": ai_data['summary'],
            "ingredients_json": modified_ingredients,
            "method_text": ai_data['method_text'],
            "tips": ai_data.get('tips', '별도 팁 없음'),
            "group_id": ai_data['group_id'],
            "tags": ai_data['tags'],
            "video_url": ai_data['video_url'],
            "image_prompt": ai_data['image_prompt'],
        })

        # 4) 썸네일 생성 및 Supabase Storage에 업로드 (자동화 핵심)
        try:
            # 4-1. 이미지 바이너리 데이터 획득 (더미 데이터 사용)
            image_binary_data = generate_dummy_image_data(final_data['title'])

            # 4-2. Storage 파일 이름 설정 (고유성을 위해 group_id + 현재 시간 사용)
            file_name = f"{final_data['group_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"

            # 4-3. Supabase Storage에 업로드. 성공하면 예외 없이 완료됨.
            supabase.storage.from_(STORAGE_BUCKET_NAME).upload(
                file_name, 
                image_binary_data, 
                file_options={"content-type": "image/png"}
            )
            
            # 4-4. 업로드 성공 시 Public URL 획득 및 DB에 반영 (V9.1 수정 부분)
            print(f"--- ✅ Storage 업로드 성공: {file_name} ---")
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{STORAGE_BUCKET_NAME}/{file_name}"
            final_data['thumbnail_url'] = public_url # 최종 이미지 URL 저장

        except Exception as e:
            # Storage 처리 오류를 명확히 출력
            print(f"--- ❌ Storage 처리 중 오류 발생: {e} ---")
            # Storage 실패 시 thumbnail_url은 None 상태로 유지되며, DB 삽입 시도
        
        # 5) Supabase DB에 최종 데이터 삽입
        supabase.table('recipes').insert(final_data).execute()
        
        print(f"--- 🎉 '{final_data['title']}' 최종 저장 성공! ---")
        return True # 성공 반환
        
    except Exception as e:
        error_message = str(e)
        # DB 컬럼 누락 오류 발생 시 명확하게 안내하기 위해 에러 메시지를 다르게 출력
        if "Could not find the 'image_prompt' column" in error_message:
            print(f"❌ DB 오류: 'image_prompt' 컬럼이 Supabase에 없습니다. 먼저 컬럼을 추가해주세요.")
        
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
            
            print(f"\n--- 🤖 Snap Food 로봇 V9.1 가동: 총 {len(search_queries)}개 쿼리 실행 ---")
            
            success_count = 0
            fail_count = 0
            
            for query in search_queries:
                if run_snap_crawler_v9_1(query): # V9.1 함수 호출
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