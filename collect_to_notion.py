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
MAX_PER_DAY         = 10
SEARCH_QUERY        = "요리 레시피"
DETAILED_CATEGORIES = [
    '한식-볶음', '양식-파스타', '디저트-케이크',
    # 필요시 추가...
]
KEYWORD_FILTER      = ["레시피", "요리", "만들기"]
TRUSTED_CHANNELS    = ["백종원의 요리비책", "마이린TV"]  # 신뢰할 채널명 리스트
CONFIDENCE_THRESHOLD = 0.7

# ───────────────────────────────────────────────
# 클라이언트 초기화
youtube = build_youtube('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion  = NotionClient(auth=NOTION_TOKEN)

def get_existing_ids():
    existing = set()
    resp = notion.databases.query(database_id=NOTION_DB_ID, page_size=100)
    for page in resp.get('results', []):
        titles = page['properties']['VideoID']['title']
        if titles:
            existing.add(titles[0]['text']['content'])
    return existing

def fetch_recipe_videos(query=SEARCH_QUERY, max_results=50, page_token=None):
    resp = youtube.search().list(
        q=query,
        part='id,snippet',
        type='video',
        maxResults=max_results,
        order='viewCount',
        pageToken=page_token
    ).execute()
    videos = []
    for item in resp.get('items', []):
        videos.append({
            'id': item['id']['videoId'],
            'title': item['snippet']['title'],
            'description': item['snippet'].get('description', ''),
            'channel': item['snippet']['channelTitle']
        })
    return videos, resp.get('nextPageToken')

def fetch_transcript_text(video_id):
    try:
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko','en'])
        return " ".join(s['text'] for s in segs)
    except:
        return ""

def fetch_top_comments(video_id, max_comments=5):
    try:
        resp = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=max_comments,
            order='relevance',
            textFormat='plainText'
        ).execute()
        comments = [item['snippet']['topLevelComment']['snippet']['textDisplay']
                    for item in resp.get('items', [])]
        return " ".join(comments)
    except:
        return ""

def translate_to_korean(text):
    if not text: return ""
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

def get_cooking_confidence(context):
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"주어진 텍스트가 실제 ‘요리 조리 과정을 설명’하는지 0~1 사이 숫자로 평가하세요."},
            {"role":"user","content":context}
        ],
        temperature=0.0,
        max_tokens=5
    )
    try:
        return float(resp.choices[0].message.content.strip())
    except:
        return 0.0

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

# ───────────────────────────────────────────────
def main():
    existing_ids = get_existing_ids()
    uploaded = 0
    page_token = None

    while uploaded < MAX_PER_DAY:
        videos, page_token = fetch_recipe_videos(SEARCH_QUERY, 50, page_token)
        if not videos:
            print("⚠️ 더 이상 검색 결과가 없습니다.")
            break

        for vid in videos:
            if uploaded >= MAX_PER_DAY:
                break
            vid_id = vid['id']
            if vid_id in existing_ids:
                continue

            title = vid['title']
            desc  = vid['description']
            channel = vid['channel']

            # 1) 제목/설명 키워드 필터
            if not any(kw in (title + desc) for kw in KEYWORD_FILTER):
                print(f"⏭️ 스킵: 키워드 불일치 ({title})")
                continue

            print(f"▶ 처리 중: https://youtu.be/{vid_id}")

            # 2) 스크립트, 댓글, 설명 합치기
            transcript = fetch_transcript_text(vid_id)
            comments   = fetch_top_comments(vid_id)
            full_text  = "\n\n".join(filter(None, [desc, transcript, comments]))

            # 3) 조리 여부 판단 (신뢰 채널은 자동 승인)
            if channel not in TRUSTED_CHANNELS:
                confidence = get_cooking_confidence(full_text)
                if confidence < CONFIDENCE_THRESHOLD:
                    print(f"⏭️ 스킵: 조리 확신도 낮음 ({confidence:.2f})")
                    continue
            else:
                print(f"✅ 신뢰 채널: {channel} 자동 승인")

            # 4) 카테고리 분류
            cat = classify_category(full_text)
            if cat not in DETAILED_CATEGORIES:
                print(f"⏭️ 스킵: 카테고리 불일치 ({cat})")
                continue

            # 5) 조리시간·재료 추출
            cook_time   = parse_cook_time(full_text)
            ingredients = extract_ingredients(full_text)

            # 6) Notion 업로드
            props = {
                "VideoID":     {"title":[{"text":{"content":vid_id}}]},
                "URL":         {"url":f"https://youtu.be/{vid_id}"},
                "Category":    {"select":{"name":cat}},
                "CookTime":    {"number":cook_time},
                "Ingredients": {"rich_text":[{"text":{"content":"\n".join(ingredients)}}]}
            }
            notion.pages.create(parent={"database_id":NOTION_DB_ID}, properties=props)
            uploaded += 1
            existing_ids.add(vid_id)
            print(f"✅ 업로드 완료 ({uploaded}/{MAX_PER_DAY})")

            time.sleep(1)

        if not page_token:
            break

    print(f"\n완료: 총 {uploaded}개 업로드했습니다.")

if __name__ == "__main__":
    main()
