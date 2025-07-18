import os
import re
import time
import random

from notion_client import Client as NotionClient
from googleapiclient.discovery import build as build_youtube
from youtube_transcript_api import YouTubeTranscriptApi
import openai

# ───────────────────────────────────────────────
# 환경 변수
YOUTUBE_API_KEY    = os.getenv('YOUTUBE_API_KEY')
NOTION_TOKEN       = os.getenv('NOTION_TOKEN')
NOTION_DB_ID       = os.getenv('NOTION_DATABASE_ID')
OPENAI_API_KEY     = os.getenv('OPENAI_API_KEY')

openai.api_key = OPENAI_API_KEY

# ───────────────────────────────────────────────
# 설정
MAX_PER_DAY         = 10
DETAILED_CATEGORIES = [
    '한식-볶음', '양식-파스타', '디저트-케이크',
    # 필요시 추가
]
SEARCH_QUERY        = "요리 레시피"

# ───────────────────────────────────────────────
# 클라이언트 초기화
youtube = build_youtube('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion  = NotionClient(auth=NOTION_TOKEN)

def get_existing_ids():
    """Notion DB에 이미 저장된 VideoID를 조회 (빈 title은 건너뜀)"""
    existing = set()
    resp = notion.databases.query(database_id=NOTION_DB_ID, page_size=100)
    for page in resp.get('results', []):
        titles = page['properties']['VideoID']['title']
        if titles:
            existing.add(titles[0]['text']['content'])
    return existing

def fetch_recipe_videos(query=SEARCH_QUERY, max_results=50):
    """'요리 레시피' 키워드로 검색해서 조리 영상 후보 ID 리스트 반환"""
    resp = youtube.search().list(
        q=query,
        part='id,snippet',
        type='video',
        maxResults=max_results,
        order='viewCount'
    ).execute()
    return [item['id']['videoId'] for item in resp.get('items', [])]

def fetch_transcript_text(vid):
    """자막을 가져와 한 문자열로 반환"""
    try:
        segs = YouTubeTranscriptApi.get_transcript(vid, languages=['ko','en'])
        return " ".join(s['text'] for s in segs)
    except:
        return ""

def translate_to_korean(text):
    """OpenAI로 자연스러운 한국어 번역"""
    if not text:
        return ""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"당신은 전문 번역가입니다. 텍스트를 자연스러운 한국어로 번역하세요."},
            {"role":"user","content":text}
        ],
        temperature=0.0,
        max_tokens=512
    )
    return resp.choices[0].message.content.strip()

def is_cooking_video(script):
    """조리 과정 영상인지 예/아니오로 판단"""
    if not script:
        return False
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"당신은 영상이 요리 조리 과정을 다루는지 판별하는 전문가입니다."},
            {"role":"user","content":"다음 내용을 보고, 실제로 ‘조리 과정을 보여주는 영상’인지 '예' 또는 '아니오'로만 답해주세요:\n\n" + script}
        ],
        temperature=0.0,
        max_tokens=5
    )
    return resp.choices[0].message.content.strip().startswith("예")

def classify_category(script):
    """세부 카테고리 중 하나로 분류"""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"당신은 요리 영상의 카테고리를 분류하는 전문가입니다."},
            {"role":"user","content":
                "아래 텍스트에서 가장 적절한 세부 카테고리 하나만 한국어로 골라주세요.\n\n"
                + script + "\n\n목록: " + str(DETAILED_CATEGORIES)
            }
        ],
        temperature=0.0,
        max_tokens=20
    )
    return resp.choices[0].message.content.strip()

def parse_cook_time(script):
    """텍스트에서 숫자(분 단위) 추출"""
    m = re.search(r"(\d+)\s?분", script or "")
    return int(m.group(1)) if m else None

def extract_ingredients(script):
    """간단히 ‘g’, ‘ml’, ‘개’ 단위의 재료 줄만 추출"""
    return [line for line in script.splitlines() if re.search(r'\d+(g|ml|개)', line)]

# ───────────────────────────────────────────────
def main():
    existing  = get_existing_ids()
    candidates = fetch_recipe_videos(max_results=50)
    # 중복 제외
    to_process = [vid for vid in candidates if vid not in existing]

    uploaded = 0
    idx = 0

    while uploaded < MAX_PER_DAY and idx < len(to_process):
        vid = to_process[idx]
        idx += 1
        print(f"▶ 처리 중: https://youtu.be/{vid}")

        # 1) 스크립트 가져와 번역
        raw       = fetch_transcript_text(vid)
        ko_script = translate_to_korean(raw)

        # 2) 요리 영상 여부 판단
        if not is_cooking_video(ko_script):
            print("⏭️ 스킵: 조리 과정 아님")
            continue

        # 3) 세부 카테고리 분류 및 필터
        cat = classify_category(ko_script)
        if cat not in DETAILED_CATEGORIES:
            print(f"⏭️ 스킵: 허용되지 않은 카테고리 ({cat})")
            continue

        # 4) 조리시간 요약
        tm_resp   = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system","content":"이 텍스트에서 조리 시간을 분 단위 숫자로만 출력하세요."},
                {"role":"user","content": ko_script}
            ],
            temperature=0.0,
            max_tokens=10
        )
        cook_time = parse_cook_time(tm_resp.choices[0].message.content) or 0

        # 5) 재료 추출
        ingredients = extract_ingredients(ko_script)

        # 6) Notion 속성 구성 및 페이지 생성
        props = {
            "VideoID":     {"title":[{"text":{"content":vid}}]},
            "URL":         {"url":f"https://youtu.be/{vid}"},
            "Category":    {"select":{"name":cat}},
            "CookTime":    {"number":cook_time},
            "Ingredients": {"rich_text":[{"text":{"content":"\n".join(ingredients)}}]}
        }
        notion.pages.create(parent={"database_id":NOTION_DB_ID}, properties=props)
        uploaded += 1
        print(f"✅ 업로드 완료 ({uploaded}/{MAX_PER_DAY})")

        time.sleep(1)  # rate-limit 방지

    print(f"\n완료: 총 {uploaded}개 업로드했습니다.")

if __name__ == "__main__":
    main()
