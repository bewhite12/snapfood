import os
import re
import time

from notion_client import Client as NotionClient
from googleapiclient.discovery import build as build_youtube
from youtube_transcript_api import YouTubeTranscriptApi
import openai

# ───────────────────────────────────────────────────────
# 환경 변수 로드
YOUTUBE_API_KEY    = os.getenv('YOUTUBE_API_KEY')
NOTION_TOKEN       = os.getenv('NOTION_TOKEN')
NOTION_DATABASE_ID = os.getenv('NOTION_DATABASE_ID')
OPENAI_API_KEY     = os.getenv('OPENAI_API_KEY')

openai.api_key = OPENAI_API_KEY

# ───────────────────────────────────────────────────────
# 설정: Test 단계에서는 5개만 업로드
MAX_UPLOADS      = 5
SEARCH_QUERY     = "cooking recipe"

# ───────────────────────────────────────────────────────
# 클라이언트 초기화
youtube = build_youtube('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion  = NotionClient(auth=NOTION_TOKEN)

# ───────────────────────────────────────────────────────
def get_existing_ids():
    """Notion DB 에 이미 들어간 VideoID 집합을 반환."""
    existing = set()
    resp = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=100)
    for page in resp.get('results', []):
        title = page['properties']['VideoID']['title']
        if title:
            existing.add(title[0]['text']['content'])
    return existing

def fetch_transcript(video_id):
    """YouTube 자막(API) → 텍스트. 실패 시 빈 문자열."""
    try:
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko','en'])
        return " ".join(s['text'] for s in segs)
    except:
        return ""

def translate_to_korean(text):
    """GPT로 한글 번역. 빈 입력 or 실패 시 '정보가 없습니다.' 반환."""
    if not text.strip():
        return "정보가 없습니다."
    prompt = (
        "다음 텍스트를 한국어로 번역하세요. "
        "추가 정보를 생성하지 말고, 원본에 없는 내용은 절대 넣지 마세요. "
        "내용이 부족하면 '정보가 없습니다.'라고만 응답하세요.\n\n"
        + text
    )
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0,
        max_tokens=2000
    )
    return resp.choices[0].message.content.strip()

def extract_ingredients(script):
    """스크립트에서 '숫자+단위+재료' 패턴을 찾아 1,2,3... 형식의 리스트로 반환."""
    pattern = r'(\d+\s?(?:g|ml|개|스푼|컵|큰술|작은술|tbsp|tsp|oz)\s?\S+)'
    matches = re.findall(pattern, script, re.I)
    if not matches:
        return "정보가 없습니다."
    return "\n".join(f"{i+1}. {m.strip()}" for i, m in enumerate(matches))

# ───────────────────────────────────────────────────────
def main():
    existing_ids = get_existing_ids()
    uploaded = 0

    # 1) 한 번만 검색해서 최대 5개 업로드
    resp = youtube.search().list(
        q=SEARCH_QUERY,
        part='id,snippet',
        type='video',
        maxResults=20,        # 20개 중에서
        order='viewCount'
    ).execute()

    for item in resp.get('items', []):
        if uploaded >= MAX_UPLOADS:
            break

        vid_id = item['id']['videoId']
        if vid_id in existing_ids:
            continue

        title       = item['snippet']['title']
        description = item['snippet'].get('description', "")

        # 2) 스크립트 입수: 자막 우선, 없으면 설명
        transcript = fetch_transcript(vid_id)
        source     = transcript or description
        if len(source.strip()) < 20:
            print(f"⏭️ 스킵: 정보량 부족 ({vid_id})")
            continue

        # 3) 재료 추출
        ingredients = extract_ingredients(source)
        if ingredients == "정보가 없습니다.":
            print(f"⏭️ 스킵: 재료 정보 부족 ({vid_id})")
            continue

        # 4) 만드는 방법: 원본 스크립트 그대로 한글 번역
        instructions_kr = translate_to_korean(source)
        if instructions_kr == "정보가 없습니다.":
            print(f"⏭️ 스킵: 조리법 번역 실패 ({vid_id})")
            continue

        # 5) Notion 업로드
        props = {
            "VideoID":     {"title":[{"text":{"content":vid_id}}]},
            "URL":         {"url":f"https://youtu.be/{vid_id}"},
            "Title":       {"rich_text":[{"text":{"content":title}}]},
            "Ingredients": {"rich_text":[{"text":{"content":ingredients}}]},
            "Instructions":{"rich_text":[{"text":{"content":instructions_kr}}]},
        }
        notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)

        uploaded += 1
        existing_ids.add(vid_id)
        print(f"✅ 업로드 완료 ({uploaded}/{MAX_UPLOADS})")
        time.sleep(1)  # API Rate-limit 방지

    print(f"총 {uploaded}개 업로드 완료")

# ───────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
