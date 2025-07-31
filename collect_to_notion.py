import os
import re
import time

from notion_client import Client as NotionClient
from googleapiclient.discovery import build as build_youtube
from youtube_transcript_api import YouTubeTranscriptApi
import openai

# ───────────────────────────────────────────────────────
# 환경 변수 로드
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
NOTION_TOKEN    = os.getenv('NOTION_TOKEN')
NOTION_DB_ID    = os.getenv('NOTION_DATABASE_ID')
OPENAI_API_KEY  = os.getenv('OPENAI_API_KEY')

openai.api_key = OPENAI_API_KEY

# ───────────────────────────────────────────────────────
# 기본 설정
MAX_PER_DAY       = 10
SEARCH_QUERIES    = ["요리 레시피", "cooking recipe"]
INITIAL_KEYWORDS  = ["레시피", "요리", "만들기", "recipe", "cook", "cooking"]

# ───────────────────────────────────────────────────────
# 클라이언트 초기화
youtube = build_youtube('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion  = NotionClient(auth=NOTION_TOKEN)

# ───────────────────────────────────────────────────────
def get_existing_ids():
    existing = set()
    resp = notion.databases.query(database_id=NOTION_DB_ID, page_size=100)
    for page in resp.get('results', []):
        titles = page['properties']['VideoID']['title']
        if titles:
            existing.add(titles[0]['text']['content'])
    return existing

def fetch_video_statistics(video_id):
    resp = youtube.videos().list(part='statistics', id=video_id).execute()
    stats = resp['items'][0]['statistics']
    return int(stats.get('viewCount', 0))

def fetch_transcript_text(video_id):
    try:
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko','en'])
        return " ".join(s['text'] for s in segs)
    except:
        return ""

def translate_to_korean(text):
    if not text.strip():
        return "정보가 없습니다."
    prompt = (
        "다음 텍스트를 한국어로 번역하세요. 추가 정보를 절대 생성하지 마세요. "
        "불명확하면 '정보가 없습니다.'로만 응답하세요.\n\n"
        + text
    )
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=2000
    )
    return resp.choices[0].message.content.strip()

def classify_category(script):
    prompt = (
        "다음 요리의 카테고리를 다음 형식으로만 작성하세요:\n"
        "한식, 중식, 양식, 일식, 디저트, 그 외 중 하나 - 정확한 음식명\n"
        "정보가 불분명하면 '그 외-기타'라고만 응답.\n\n"
        + script
    )
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=20
    )
    cat = resp.choices[0].message.content.strip()
    return cat if '-' in cat else "그 외-기타"

def optimize_for_seo(instructions):
    if instructions == "정보가 없습니다.":
        return instructions
    prompt = (
        "다음 요리법을 SEO에 맞게 단계별로 정리하세요. "
        "절대 추가 정보 생성 금지. 정보 부족시 '정보가 없습니다.'로만 응답.\n\n"
        + instructions
    )
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=1500
    )
    return resp.choices[0].message.content.strip()

def generate_hashtags(content):
    if content == "정보가 없습니다.":
        return "#정보없음"
    prompt = (
        "다음 콘텐츠의 요리 관련 해시태그 10개만 생성하세요. "
        "요리와 관련 없으면 '#정보없음'으로만 응답.\n\n"
        + content
    )
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=100
    )
    hashtags = resp.choices[0].message.content.strip()
    return hashtags if hashtags.startswith("#") else "#정보없음"

def extract_ingredients(script):
    matches = re.findall(
        r'(\d+\s?(?:g|ml|개|스푼|컵|큰술|작은술|tbsp|tsp|oz)\s?\S+)',
        script, re.I
    )
    if not matches:
        return "정보가 없습니다."
    return "\n".join(f"{i+1}. {m}" for i, m in enumerate(matches))

def is_cooking_channel(channel_id):
    resp = youtube.search().list(
        channelId=channel_id, part='snippet', order='date',
        maxResults=5, type='video'
    ).execute()
    cnt = 0
    for v in resp.get('items', []):
        text = (v['snippet']['title'] + v['snippet']['description']).lower()
        if any(kw in text for kw in INITIAL_KEYWORDS):
            cnt += 1
    return cnt >= 3

# ───────────────────────────────────────────────────────
def main():
    existing_ids = get_existing_ids()
    uploaded = 0

    for query in SEARCH_QUERIES:
        page_token = None
        while uploaded < MAX_PER_DAY:
            resp = youtube.search().list(
                q=query, part='id,snippet', type='video',
                maxResults=50, order='viewCount', pageToken=page_token
            ).execute()
            videos = resp.get('items', [])
