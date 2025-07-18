import os
import re
import time
import random
from notion_client import Client
from youtube_transcript_api import YouTubeTranscriptApi
import openai

# 환경 변수에서 키 가져오기
YOUTUBE_API_KEY      = os.environ['YOUTUBE_API_KEY']
NOTION_TOKEN         = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID   = os.environ['NOTION_DATABASE_ID']
OPENAI_API_KEY       = os.environ['OPENAI_API_KEY']

# 클라이언트 초기화
notion = Client(auth=NOTION_TOKEN)
openai.api_key = OPENAI_API_KEY

def get_existing_ids():
    """노션에 이미 저장된 VideoID 목록을 반환 (빈 타이틀은 건너뜀)"""
    existing = set()
    rsp = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=100)
    for p in rsp.get('results', []):
        titles = p['properties']['VideoID']['title']
        if not titles:
            continue
        existing.add(titles[0]['text']['content'])
    return existing

def fetch_trending_videos(max_results=10):
    """유튜브 API로 조회수 10만↑ 동영상 ID 리스트 반환 (랜덤 추출)"""
    # (여기서는 예시용 더미 리스트)
    all_videos = ['abc123', 'def456', 'ghi789', ...]  # 실제 호출 로직으로 교체
    return random.sample(all_videos, max_results)

def fetch_transcript(video_id):
    """YouTubeTranscriptApi로 자막 텍스트 가져오기"""
    try:
        return YouTubeTranscriptApi.get_transcript(video_id, languages=['ko','en'])
    except:
        return []

def to_text(transcript):
    """자막 리스트를 한 덩어리 텍스트로 합치기"""
    return " ".join([seg['text'] for seg in transcript])

def translate_to_korean(text):
    """OpenAI로 자연스러운 한국어 번역"""
    prompt = f"다음 영어(또는 기타 언어) 레시피 텍스트를 자연스러운 한국어로 번역해 주세요:\n\n{text}"
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.7
    )
    return resp.choices[0].message.content.strip()

def parse_recipe(text):
    """한국어 텍스트에서 재료(Ingredients)와 조리시간(CookTime) 뽑기"""
    lines = text.splitlines()
    ingredients = [l for l in lines if re.search(r'\d+g|\d+ml|\d+개', l)]
    cook_time_match = re.search(r'(\d+)\s?분', text)
    cook_time = int(cook_time_match.group(1)) if cook_time_match else None
    return ingredients, cook_time

def main():
    print("▶ 유튜브에서 영상 수집 중...")
    existing_ids = get_existing_ids()
    candidates = [v for v in fetch_trending_videos(100) if v not in existing_ids]
    selected   = random.sample(candidates, min(10, len(candidates)))

    for vid in selected:
        # 1) 썸네일·제목·조회수·URL 등 기본 메타
        url = f"https://youtu.be/{vid}"
        title = "(제목 조회 로직 필요)"
        views = 0  # 조회수 API로 채워야 함
        category = "(카테고리 자동 분류 로직 필요)"
        channel  = "(채널명 API 로직)"

        # 2) 자막 → 한국어 번역
        raw = to_text(fetch_transcript(vid))
        if not raw:
            print(f"⚠ 자막 없음: {vid}, 스킵")
            continue
        ko_text = translate_to_korean(raw)

        # 3) 재료·조리시간 추출
        ingredients, cook_time = parse_recipe(ko_text)

        # 4) 노션에 새 페이지 생성
        props = {
            "VideoID": {
                "title": [{"text": {"content": vid}}]
            },
            "URL": {
                "url": url
            },
            "Title": {
                "rich_text": [{"text": {"content": title}}]
            },
            "Views": {
                "number": views
            },
            "Category": {
                "multi_select": [{"name": category}]
            },
            "Channel": {
                "rich_text": [{"text": {"content": channel}}]
            },
            "Ingredients": {
                "rich_text": [{"text": {"content": "\n".join(ingredients)}}]
            },
            "CookTime": {
                "number": cook_time or 0
            }
        }
        notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
        time.sleep(1)  # rate limit 방지

    print(f"✅ Notion에 {len(selected)}개의 신규 레시피를 업데이트했습니다.")

if __name__ == "__main__":
    main()
