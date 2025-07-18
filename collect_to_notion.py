import os
import re
import time

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
MAX_PER_DAY       = 10
SEARCH_QUERY      = "요리 레시피"
DETAILED_CATEGORIES = [
    '한식-볶음', '양식-파스타', '디저트-케이크',
    # 필요시 추가...
]

# ───────────────────────────────────────────────
# 클라이언트 초기화
youtube = build_youtube('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion  = NotionClient(auth=NOTION_TOKEN)

def get_existing_ids():
    """Notion DB에 이미 저장된 VideoID를 조회 (빈 타이틀 스킵)"""
    existing = set()
    resp = notion.databases.query(database_id=NOTION_DB_ID, page_size=100)
    for page in resp.get('results', []):
        titles = page['properties']['VideoID']['title']
        if titles:
            existing.add(titles[0]['text']['content'])
    return existing

def fetch_search_page(query, page_token=None):
    """검색 API 한 페이지(50개) 반환"""
    resp = youtube.search().list(
        q=query,
        part='id,snippet',
        type='video',
        maxResults=50,
        order='viewCount',
        pageToken=page_token
    ).execute()
    items = resp.get('items', [])
    vids  = [item['id']['videoId'] for item in items]
    return vids, resp.get('nextPageToken')

def fetch_transcript_text(vid):
    try:
        segs = YouTubeTranscriptApi.get_transcript(vid, languages=['ko','en'])
        return " ".join(s['text'] for s in segs)
    except:
        return ""

def translate_to_korean(text):
    if not text:
        return ""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"전문 번역가입니다. 텍스트를 자연스러운 한국어로 번역하세요."},
            {"role":"user","content":text}
        ],
        temperature=0.0,
        max_tokens=512
    )
    return resp.choices[0].message.content.strip()

def is_cooking_video(script):
    if not script:
        return False
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"이 텍스트가 실제 조리 과정을 설명하는지 판단하세요. '예' 또는 '아니오'만 답변."},
            {"role":"user","content":script}
        ],
        temperature=0.0,
        max_tokens=5
    )
    return resp.choices[0].message.content.strip().startswith("예")

def classify_category(script):
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"요리 영상의 세부 카테고리를 하나만 한국어로 선택하세요."},
            {"role":"user","content":f"{script}\n\n목록: {DETAILED_CATEGORIES}"}
        ],
        temperature=0.0,
        max_tokens=20
    )
    return resp.choices[0].message.content.strip()

def parse_cook_time(script):
    m = re.search(r"(\d+)\s?분", script or "")
    return int(m.group(1)) if m else 0

def extract_ingredients(script):
    return [line for line in script.splitlines() if re.search(r'\d+(g|ml|개)', line)]

def main():
    existing_ids = get_existing_ids()

    uploaded = 0
    page_token = None

    # 페이지를 돌며 10개 업로드할 때까지 계속
    while uploaded < MAX_PER_DAY:
        vids, page_token = fetch_search_page(SEARCH_QUERY, page_token)
        if not vids:
            print("⚠️ 더 이상 검색 결과가 없습니다.")
            break

        for vid in vids:
            if uploaded >= MAX_PER_DAY:
                break
            if vid in existing_ids:
                continue

            print(f"▶ 처리 중: https://youtu.be/{vid}")

            # 1) 자막 번역
            raw       = fetch_transcript_text(vid)
            ko_script = translate_to_korean(raw)

            # 2) 조리 여부 판단
            if not is_cooking_video(ko_script):
                print("⏭️ 스킵: 조리 과정 아님")
                continue

            # 3) 카테고리 분류
            cat = classify_category(ko_script)
            if cat not in DETAILED_CATEGORIES:
                print(f"⏭️ 스킵: 카테고리 불일치 ({cat})")
                continue

            # 4) 조리시간·재료 추출
            cook_time   = parse_cook_time(ko_script)
            ingredients = extract_ingredients(ko_script)

            # 5) Notion에 업로드
            props = {
                "VideoID":     {"title":[{"text":{"content":vid}}]},
                "URL":         {"url":f"https://youtu.be/{vid}"},
                "Category":    {"select":{"name":cat}},
                "CookTime":    {"number":cook_time},
                "Ingredients": {"rich_text":[{"text":{"content":"\n".join(ingredients)}}]}
            }
            notion.pages.create(parent={"database_id":NOTION_DB_ID}, properties=props)
            uploaded += 1
            existing_ids.add(vid)
            print(f"✅ 업로드 완료 ({uploaded}/{MAX_PER_DAY})")

            time.sleep(1)  # rate-limit 방지

        # 다음 페이지 토큰이 없으면 종료
        if not page_token:
            break

    print(f"\n완료: 총 {uploaded}개 업로드했습니다.")

if __name__ == "__main__":
    main()
