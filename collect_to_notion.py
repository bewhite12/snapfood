import os
import random
import time
import json
import re

from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from notion_client import Client
import openai

# ─ 환경변수 읽기 ──────────────────────────────────────────
YOUTUBE_API_KEY    = os.environ['YOUTUBE_API_KEY']
OPENAI_API_KEY     = os.environ['OPENAI_API_KEY']
NOTION_TOKEN       = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID = os.environ['NOTION_DATABASE_ID']

# ─ 클라이언트 초기화 ─────────────────────────────────────
yt     = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion = Client(auth=NOTION_TOKEN)
openai.api_key = OPENAI_API_KEY

# ─ 자동 분류 함수 & 카테고리 리스트 ─────────────────────────
DETAILED_CATEGORIES = [
    "한식-찌개", "한식-볶음", "한식-전골",
    "양식-파스타", "양식-스테이크",
    "일식-초밥", "일식-라멘",
    "중식-탕수육", "중식-마라샹궈",
]

def classify_category(text, categories):
    prompt = (
        "아래 레시피 텍스트에서, 제공된 카테고리 목록 중 가장 적절한 하나를 "
        "한국어로 선택해 알려주세요.\n\n"
        f"카테고리 목록: {categories}\n\n"
        "레시피 텍스트:\n" + text
    )
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"레시피 자동 분류 도우미입니다."},
            {"role":"user",  "content":prompt}
        ],
        temperature=0.0,
        max_tokens=20
    )
    return resp.choices[0].message.content.strip()

def fetch_youtube_text(video_id, description):
    text = description or ""
    try:
        subs = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko','en'])
        text += "\n\n" + "\n".join(item['text'] for item in subs)
    except Exception:
        pass
    return text

def extract_recipe_structured(text):
    prompt = (
        "아래 텍스트에서 재료, 조리시간, 조리방법을 JSON으로 추출해주세요.\n"
        "1) ingredients: ['재료1', '재료2', ...]\n"
        "2) cook_time: 'XX분'\n"
        "3) instructions: ['1. ...', '2. ...']\n\n"
        "반드시 JSON만 출력하고, 키는 ingredients, cook_time, instructions이어야 합니다.\n\n"
        + text
    )
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"구조화된 레시피 데이터를 추출합니다."},
            {"role":"user",  "content":prompt}
        ],
        temperature=0.0,
        max_tokens=512
    )
    return json.loads(resp.choices[0].message.content.strip())

def get_existing_video_ids():
    existing = set()
    query = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=100)
    for page in query['results']:
        title_prop = page['properties']['VideoID']['title']
        if title_prop:
            existing.add(title_prop[0]['text']['content'])
    return existing

def fetch_videos():
    resp = yt.videos().list(
        part="snippet,statistics",
        chart="mostPopular",
        regionCode="KR",
        maxResults=50
    ).execute()
    return resp.get('items', [])

if __name__ == "__main__":
    existing_ids = get_existing_video_ids()
    videos = fetch_videos()
    if not videos:
        print("⚠️ 인기 영상 불러오기 실패")
        exit(1)

    # 하루 최대 10개, 기존 업로드 제외 (테스트 단계)
    candidates = [v for v in videos if v['id'] not in existing_ids]
    selected   = random.sample(candidates, min(10, len(candidates)))

    for v in selected:
        vid   = v['id']
        snip  = v['snippet']
        stats = v.get('statistics', {})

        full_text = fetch_youtube_text(vid, snip.get('description', ""))

        try:
            struct = extract_recipe_structured(full_text)
        except Exception as e:
            print(f"구조화 오류: {e}")
            continue

        chosen_cat = classify_category(full_text, DETAILED_CATEGORIES)

        def translate(text):
            if not text or any('\uAC00' <= c <= '\uD7A3' for c in text):
                return text
            r = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role":"system","content":"한국어 번역 도우미입니다."},
                    {"role":"user",  "content":f"다음을 한국어로 번역해주세요: {text}"}
                ],
                temperature=0.0,
                max_tokens=200
            )
            return r.choices[0].message.content.strip()

        ing_list  = struct.get('ingredients', [])
        ing_ko    = [translate(i) for i in ing_list]

        cook_en   = struct.get('cook_time') or ""
        cook_ko   = translate(cook_en) or ""

        # 숫자만 추출해 Notion number 타입으로
        m = re.search(r"(\d+)", cook_ko)
        cook_num = int(m.group(1)) if m else None

        inst_list = struct.get('instructions', [])
        inst_ko   = [translate(s) for s in inst_list]

        props = {
            'VideoID':      {'title':      [{'text':{'content': vid}}]},
            'Title':        {'rich_text': [{'text':{'content': snip.get('title','')}}]},
            'Views':        {'number':     int(stats.get('viewCount', 0))},
            'URL':          {'url':        f"https://youtu.be/{vid}"},
            'Channel':      {'rich_text': [{'text':{'content': snip.get('channelTitle','')}}]},
            'Category':     {'select':     {'name': chosen_cat}},
            'Ingredients':  {'rich_text': [{'text':{'content': "\n".join(ing_ko)}}]},
            'Instructions': {'rich_text': [{'text':{'content': "\n".join(inst_ko)}}]},
        }
        if cook_num is not None:
            props['CookTime'] = {'number': cook_num}

        created = notion.pages.create(
            parent={'database_id': NOTION_DATABASE_ID},
            properties=props
        )
        pid = created['id'].replace('-', '')
        print(f"👉 업로드 완료: https://www.notion.so/{pid}")

        time.sleep(1)

    print(f"✅ Notion에 {len(selected)}개의 신규 레시피를 업데이트했습니다.")
