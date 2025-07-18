import os
import re
import time

from notion_client import Client as NotionClient
from googleapiclient.discovery import build as build_youtube
from youtube_transcript_api import YouTubeTranscriptApi
import openai

# 환경 변수
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
NOTION_TOKEN = os.getenv('NOTION_TOKEN')
NOTION_DB_ID = os.getenv('NOTION_DATABASE_ID')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

openai.api_key = OPENAI_API_KEY

MAX_PER_DAY = 10
SEARCH_QUERIES = ["요리 레시피", "cooking recipe"]
INITIAL_KEYWORDS = ["레시피", "요리", "만들기", "recipe", "cook", "cooking"]

youtube = build_youtube('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion = NotionClient(auth=NOTION_TOKEN)

trusted_channels = set()
dynamic_categories = set()

def get_existing_ids():
    existing = set()
    resp = notion.databases.query(database_id=NOTION_DB_ID, page_size=100)
    for page in resp.get('results', []):
        titles = page['properties']['VideoID']['title']
        if titles:
            existing.add(titles[0]['text']['content'])
    return existing

def get_channel_id(channel_name):
    resp = youtube.search().list(q=channel_name, type='channel', part='snippet', maxResults=1).execute()
    return resp['items'][0]['snippet']['channelId'] if resp['items'] else ""

def is_trusted_channel(channel):
    if channel in trusted_channels:
        return True
    resp = youtube.search().list(
        channelId=get_channel_id(channel), part='snippet', order='date', maxResults=10, type='video'
    ).execute()
    count = sum(
        1 for item in resp.get('items', [])
        if any(kw.lower() in (item['snippet']['title'] + item['snippet']['description']).lower()
               for kw in INITIAL_KEYWORDS)
    )
    if count >= 7:
        trusted_channels.add(channel)
        print(f"✅ 신뢰 채널 추가됨: {channel}")
        return True
    return False

def fetch_transcript_text(video_id):
    try:
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko','en'])
        return " ".join(s['text'] for s in segs)
    except:
        return ""

def fetch_top_comments(video_id, max_comments=5):
    try:
        resp = youtube.commentThreads().list(
            part='snippet', videoId=video_id, maxResults=max_comments,
            order='relevance', textFormat='plainText'
        ).execute()
        return " ".join(item['snippet']['topLevelComment']['snippet']['textDisplay'] for item in resp.get('items', []))
    except:
        return ""

def translate_to_korean(text):
    if not text: return ""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":f"다음 내용을 자연스러운 한국어로 번역하세요.\n\n{text}"}],
        temperature=0.0, max_tokens=2000
    )
    return resp.choices[0].message.content.strip()

def classify_category(script):
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":f"다음 요리 영상의 카테고리를 '음식종류-요리방식' 형태로 한국어로 작성하세요.\n\n{script}"}],
        temperature=0.0, max_tokens=20
    )
    cat = resp.choices[0].message.content.strip()
    dynamic_categories.add(cat)
    return cat

def parse_cook_time(script):
    m = re.search(r"(\d+)\s?(분|min|minutes)", script or "", re.I)
    return int(m.group(1)) if m else 0

def extract_ingredients(script):
    return [line for line in script.splitlines() if re.search(r'\d+(g|ml|개|스푼|컵|tbsp|tsp|oz)', line, re.I)]

def update_keywords(script):
    global INITIAL_KEYWORDS
    prompt = f"다음 텍스트에서 핵심 키워드를 5개만 뽑아 기존 {INITIAL_KEYWORDS}와 중복없이 제공해주세요:\n\n{script}"
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=50
    )
    new_keywords = [kw.strip() for kw in resp.choices[0].message.content.strip().split(",")]
    INITIAL_KEYWORDS = list(set(INITIAL_KEYWORDS + new_keywords))

def optimize_for_seo(instructions):
    prompt = f"다음 요리 조리법을 웹 검색 최적화(SEO)에 맞게 깔끔하고 단계별로 정리해주세요.\n\n{instructions}"
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=1500
    )
    return resp.choices[0].message.content.strip()

def generate_hashtags(content):
    prompt = f"다음 요리 콘텐츠에서 인스타그램 등에 적합한 해시태그 10개 생성해주세요. (# 포함)\n\n{content}"
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=100
    )
    return resp.choices[0].message.content.strip()

def main():
    existing_ids = get_existing_ids()
    uploaded = 0

    for query in SEARCH_QUERIES:
        page_token = None
        while uploaded < MAX_PER_DAY:
            videos, page_token = youtube.search().list(
                q=query, part='id,snippet', type='video', maxResults=50, order='viewCount', pageToken=page_token
            ).execute().get('items', []), None
            if not videos: break

            for vid in videos:
                if uploaded >= MAX_PER_DAY: break
                vid_id = vid['id']['videoId']
                if vid_id in existing_ids: continue

                title, desc, channel = vid['snippet']['title'], vid['snippet']['description'], vid['snippet']['channelTitle']
                full_text = "\n\n".join(filter(None, [desc, fetch_transcript_text(vid_id), fetch_top_comments(vid_id)]))
                full_text_kr = translate_to_korean(full_text)

                if not is_trusted_channel(channel):
                    if not any(kw.lower() in (title+desc).lower() for kw in INITIAL_KEYWORDS): continue

                optimized_instructions = optimize_for_seo(full_text_kr)
                hashtags = generate_hashtags(full_text_kr)
                cat = classify_category(full_text_kr)

                props = {
                    "VideoID": {"title":[{"text":{"content":vid_id}}]},
                    "URL": {"url":f"https://youtu.be/{vid_id}"},
                    "Title": {"rich_text":[{"text":{"content":translate_to_korean(title)}}]},
                    "Channel": {"rich_text":[{"text":{"content":channel}}]},
                    "Category": {"select":{"name":cat}},
                    "CookTime": {"number":parse_cook_time(full_text)},
                    "Ingredients": {"rich_text":[{"text":{"content":"\n".join(extract_ingredients(full_text))}}]},
                    "Instructions": {"rich_text":[{"text":{"content":optimized_instructions}}]},
                    "Hashtags": {"rich_text":[{"text":{"content":hashtags}}]},
                    "Views": {"number":0},
                }
                notion.pages.create(parent={"database_id":NOTION_DB_ID}, properties=props)
                uploaded +=1
                existing_ids.add(vid_id)

                print(f"✅ 업로드 완료 ({uploaded}/{MAX_PER_DAY}), 카테고리: {cat}")
                time.sleep(1)
            if not page_token or uploaded >= MAX_PER_DAY: break

    print(f"총 {uploaded}개 업로드 완료\n자동생성 카테고리: {dynamic_categories}\n확장된 키워드: {INITIAL_KEYWORDS}\n신뢰 채널: {trusted_channels}")

if __name__ == "__main__":
    main()
