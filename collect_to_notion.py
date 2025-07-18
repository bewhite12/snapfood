import os
import random
import time
import json
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

# ─ 유튜브 설명 + 자막 결합 ─────────────────────────────────
def fetch_youtube_text(video_id, description):
    text = description or ""
    try:
        subs = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko','en'])
        text += "\n\n" + "\n".join(item['text'] for item in subs)
    except Exception:
        pass
    return text

# ─ ChatGPT에 구조화 요청 ──────────────────────────────────
def extract_recipe_structured(text):
    prompt = f"""
아래 텍스트에서 재료, 조리시간, 조리방법을 JSON으로 추출해 주세요.
1) ingredients: ["재료1", "재료2", ...]
2) cook_time: "XX분"
3) instructions: ["1. ...", "2. ...", ...]

출력은 JSON만, keys는 ingredients, cook_time, instructions 로 해주세요.

    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that extracts structured recipe data."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=512
    )
    return json.loads(resp.choices[0].message.content.strip())

# ─ ChatGPT에 한글 번역 요청 ─────────────────────────────────
def translate_to_korean(text):
    """주어진 텍스트를 자연스럽고 간결한 한국어로 번역합니다."""
    if not text.strip():
        return ""
    prompt = f"다음 텍스트를 자연스럽고 간결한 한국어로 번역해 주세요:\n\n'''{text}'''"
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a professional translator to Korean."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=512
    )
    return resp.choices[0].message.content.strip()

# ─ 이미 업로드된 VideoID 조회 ─────────────────────────────────
def get_existing_video_ids():
    existing = set()
    resp = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=100)
    for page in resp.get('results', []):
        title_prop = page['properties']['VideoID']['title']
        if title_prop:
            existing.add(title_prop[0]['text']['content'])
    return existing

# ─ 인기 영상 목록 불러오기 ─────────────────────────────────
def fetch_videos():
    res = yt.videos().list(
        part="snippet,statistics",
        chart="mostPopular",
        regionCode="KR",
        maxResults=50
    ).execute()
    return res.get('items', [])

# ─ 메인 실행 ────────────────────────────────────────────
if __name__ == "__main__":
    existing_ids = get_existing_video_ids()
    videos = fetch_videos()
    if not videos:
        print("⚠️ 인기 영상 불러오기 실패")
        exit(1)

    # 하루 최대 75개, 중복 제외
    candidates = [v for v in videos if v['id'] not in existing_ids]
    selected = random.sample(candidates, min(75, len(candidates)))

    for v in selected:
        vid   = v['id']
        snip  = v['snippet']
        stats = v.get('statistics', {})

        # 1) YouTube 설명 + 자막
        full_text = fetch_youtube_text(vid, snip.get('description', ""))

        # 2) ChatGPT로 구조화 정보 추출
        try:
            struct = extract_recipe_structured(full_text)
        except Exception as e:
            print(f"GPT 구조화 오류: {e}")
            continue

        # 3) 번역
        ing_list = struct.get('ingredients', [])
        ing_ko   = [translate_to_korean(i) for i in ing_list]
        cook_en  = struct.get('cook_time', '')
        cook_ko  = translate_to_korean(cook_en)
        inst_list = struct.get('instructions', [])
        inst_ko  = [translate_to_korean(step) for step in inst_list]

        # 4) Notion 속성 구성
        props = {
            'VideoID':     {'title':      [{'text':{'content': vid}}]},
            'Title':       {'rich_text': [{'text':{'content': snip.get('title','')}}]},
            'Views':       {'number':     int(stats.get('viewCount', 0))},
            'URL':         {'url':        f"https://youtu.be/{vid}"},
            'Channel':     {'rich_text': [{'text':{'content': snip.get('channelTitle','')}}]},
            'Category':    {'select':     {'name': random.choice(['한식','양식','일식'])}},
            'Ingredients': {'rich_text': [{'text':{'content': "\n".join(ing_ko)}}]},
            'CookTime':    {'rich_text': [{'text':{'content': cook_ko}}]},
            'Instructions':{'rich_text': [{'text':{'content': "\n".join(inst_ko)}}]},
        }

        notion.pages.create(
            parent={'database_id': NOTION_DATABASE_ID},
            properties=props
        )
        time.sleep(1)

    print(f"✅ Notion에 {len(selected)}개의 신규 레시피를 업데이트했습니다.")
