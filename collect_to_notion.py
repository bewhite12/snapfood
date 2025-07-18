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
    if not text: return ""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":f"다음 내용을 자연스러운 한국어로 번역하세요.\n\n{text}"}],
        temperature=0.0, max_tokens=2000
    )
    return resp.choices[0].message.content.strip()

def classify_category(script):
    prompt = f"""다음 요리의 카테고리를 아래 형식으로 작성하세요.
1차 카테고리: 한식, 중식, 양식, 일식, 디저트, 그 외 중 하나
2차 카테고리: 음식의 정확한 이름 (예: 비빔국수, 된장찌개 등)

{script}

형식: [1차 카테고리]-[2차 카테고리]
"""
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role":"user","content":prompt}],
        temperature=0.0, max_tokens=20
    )
    cat = resp.choices[0].message.content.strip()
    return cat if '-' in cat else f"그 외-{cat}"

def optimize_for_seo(instructions):
    prompt = f"다음 요리법을 웹 SEO에 맞게 깔끔하고 단계별로 한글로 정리하세요.\n\n{instructions}"
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

def extract_ingredients(script):
    items = re.findall(r'(\d+\s?(?:g|ml|개|스푼|컵|큰술|작은술|tbsp|tsp|oz)\s?\S+)', script, re.I)
    return [item.strip() for item in items]

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
                views = fetch_video_statistics(vid_id)
                full_text = "\n\n".join(filter(None, [desc, fetch_transcript_text(vid_id)]))
                full_text_kr = translate_to_korean(full_text)

                optimized_instructions = optimize_for_seo(full_text_kr)
                hashtags = generate_hashtags(full_text_kr)
                cat = classify_category(full_text_kr)

                ingredients = extract_ingredients(full_text_kr)
                ingredients_formatted = "\n".join(f"{i+1}. {item}" for i, item in enumerate(ingredients))

                props = {
                    "VideoID": {"title":[{"text":{"content":vid_id}}]},
                    "URL": {"url":f"https://youtu.be/{vid_id}"},
                    "Title": {"rich_text":[{"text":{"content":translate_to_korean(title)}}]},
                    "Channel": {"rich_text":[{"text":{"content":channel}}]},
                    "Category": {"select":{"name":cat}},
                    "Ingredients": {"rich_text":[{"text":{"content":ingredients_formatted}}]},
                    "Instructions": {"rich_text":[{"text":{"content":optimized_instructions}}]},
                    "Hashtags": {"rich_text":[{"text":{"content":hashtags}}]},
                    "Views": {"number":views},
                }
                notion.pages.create(parent={"database_id":NOTION_DB_ID}, properties=props)
                uploaded +=1
                existing_ids.add(vid_id)

                print(f"✅ 업로드 완료 ({uploaded}/{MAX_PER_DAY}), 카테고리: {cat}")
                time.sleep(1)
            if not page_token or uploaded >= MAX_PER_DAY: break

    print(f"총 {uploaded}개 업로드 완료")

if __name__ == "__main__":
    main()
