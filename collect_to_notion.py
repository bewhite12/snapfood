import os
import re
import time

from notion_client import Client as NotionClient
from googleapiclient.discovery import build as build_youtube
from youtube_transcript_api import YouTubeTranscriptApi
import openai

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
    prompt = f"다음 텍스트를 한국어로 번역하세요. 추가 정보를 절대 생성하지 마세요. 불명확하면 '정보가 없습니다.'로만 응답하세요.\n\n{text}"
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=2000
    )
    return resp.choices[0].message.content.strip()

def classify_category(script):
    prompt = f"""다음 요리의 카테고리를 다음 형식으로만 작성하세요:
한식, 중식, 양식, 일식, 디저트, 그 외 중 하나 - 정확한 음식명
정보가 불분명하면 '그 외-기타'라고만 응답.

{script}
"""
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
    prompt = f"다음 요리법을 SEO에 맞게 단계별로 정리하세요. 절대 추가 정보 생성 금지. 정보 부족시 '정보가 없습니다.'로만 응답.\n\n{instructions}"
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=1500
    )
    return resp.choices[0].message.content.strip()

def generate_hashtags(content):
    if content == "정보가 없습니다.":
        return "#정보없음"
    prompt = f"다음 콘텐츠의 요리 관련 해시태그 10개만 생성하세요. 요리와 관련 없으면 '#정보없음'으로만 응답.\n\n{content}"
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=100
    )
    hashtags = resp.choices[0].message.content.strip()
    return hashtags if hashtags.startswith("#") else "#정보없음"

def extract_ingredients(script):
    matches = re.findall(r'(\d+\s?(?:g|ml|개|스푼|컵|큰술|작은술|tbsp|tsp|oz)\s?\S+)', script, re.I)
    return "\n".join(f"{i+1}. {match}" for i, match in enumerate(matches)) if matches else "정보가 없습니다."

def is_cooking_channel(channel_id):
    resp = youtube.search().list(
        channelId=channel_id, part='snippet', order='date', maxResults=5, type='video'
    ).execute()
    videos = resp.get('items', [])
    cooking_count = 0
    for vid in videos:
        text = vid['snippet']['title'] + vid['snippet']['description']
        if any(kw.lower() in text.lower() for kw in INITIAL_KEYWORDS):
            cooking_count += 1
    return cooking_count >= 3

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

                title = vid['snippet']['title']
                desc = vid['snippet']['description']
                channel = vid['snippet']['channelTitle']
                channel_id = vid['snippet']['channelId']

                if not is_cooking_channel(channel_id):
                    print(f"⏭️ 스킵: 채널에 요리영상 부족 ({channel})")
                    continue

                views = fetch_video_statistics(vid_id)
                full_text = "\n\n".join(filter(None, [desc, fetch_transcript_text(vid_id)]))

                if len(full_text.strip()) < 50:
                    print(f"⏭️ 스킵: 정보 부족 ({vid_id})")
                    continue

                full_text_kr = translate_to_korean(full_text)
                if full_text_kr == "정보가 없습니다.":
                    print(f"⏭️ 스킵: 번역 정보 부족 ({vid_id})")
                    continue

                optimized_instructions = optimize_for_seo(full_text_kr)
                if optimized_instructions == "정보가 없습니다.":
                    print(f"⏭️ 스킵: 조리법 정보 부족 ({vid_id})")
                    continue

                hashtags = generate_hashtags(full_text_kr)
                if hashtags == "#정보없음":
                    print(f"⏭️ 스킵: 해시태그 정보 부족 ({vid_id})")
                    continue

                category = classify_category(full_text_kr)
                ingredients = extract_ingredients(full_text_kr)
                if ingredients == "정보가 없습니다.":
                    print(f"⏭️ 스킵: 재료 정보 부족 ({vid_id})")
                    continue

                props = {
                    "VideoID": {"title":[{"text":{"content":vid_id}}]},
                    "URL": {"url":f"https://youtu.be/{vid_id}"},
                    "Title": {"rich_text":[{"text":{"content":translate_to_korean(title)}}]},
                    "Channel": {"rich_text":[{"text":{"content":channel}}]},
                    "Category": {"select":{"name":category}},
                    "Ingredients": {"rich_text":[{"text":{"content":ingredients}}]},
                    "Instructions": {"rich_text":[{"text":{"content":optimized_instructions}}]},
                    "Hashtags": {"rich_text":[{"text":{"content":hashtags}}]},
                    "Views": {"number":views},
                }
                notion.pages.create(parent={"database_id":NOTION_DB_ID}, properties=props)
                uploaded +=1
                existing_ids.add(vid_id)

                print(f"✅ 업로드 완료 ({uploaded}/{MAX_PER_DAY}), 카테고리: {category}")
                time.sleep(1)
            if not page_token or uploaded >= MAX_PER_DAY: break

    print(f"총 {uplo
