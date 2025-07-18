import os
import re
import time
from notion_client import Client
from googleapiclient.discovery import build
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
DETAILED_CATEGORIES = [
    '한식-볶음', '양식-파스타', '디저트-케이크',
    # 필요시 추가
]

# ───────────────────────────────────────────────
# 클라이언트 초기화
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion  = Client(auth=NOTION_TOKEN)

def get_existing_ids():
    existing = set()
    rsp = notion.databases.query(database_id=NOTION_DB_ID, page_size=100)
    for page in rsp.get('results', []):
        titles = page['properties']['VideoID']['title']
        if titles:
            existing.add(titles[0]['text']['content'])
    return existing

def fetch_trending_videos(max_results=50):
    resp = youtube.videos().list(
        part='snippet,statistics',
        chart='mostPopular',
        regionCode='KR',
        maxResults=max_results
    ).execute()
    return [item['id'] for item in resp.get('items', [])]

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
            {"role":"system","content":"당신은 전문 번역가입니다. 텍스트를 자연스러운 한국어로 번역하세요."},
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
            {"role":"system","content":"당신은 영상이 요리 조리 과정을 다루는지 판별하는 전문가입니다."},
            {"role":"user","content":"다음 내용을 보고, 실제로 ‘조리 과정을 보여주는 영상’인지 '예' 또는 '아니오'로만 답해주세요:\n\n" + script}
        ],
        temperature=0.0,
        max_tokens=5
    )
    return resp.choices[0].message.content.strip().startswith("예")

def classify_category(script):
    resp = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"당신은 요리 영상의 카테고리를 분류하는 전문가입니다."},
            {"role":"user","content":
                "아래 텍스트에서 가장 적절한 세부 카테고리 하나만 한국어로 골라주세요.\n\n"
                + script + "\n\n목록: " + str(DETAILED_CATEGORIES)
            }
        ],
        temperature=0.0,
        max_tokens=20
    )
    return resp.choices[0].message.content.strip()

def parse_cook_time(script):
    m = re.search(r"(\d+)\s?분", script or "")
    return int(m.group(1)) if m else None

def extract_ingredients(script):
    return [line for line in script.splitlines() if re.search(r'\d+(g|ml|개)', line)]

# ───────────────────────────────────────────────
def main():
    existing = get_existing_ids()
    candidates = fetch_trending_videos(50)
    to_process = [vid for vid in candidates if vid not in existing]

    uploaded = 0
    idx = 0

    while uploaded < MAX_PER_DAY and idx < len(to_process):
        vid = to_process[idx]
        idx += 1
        print(f"▶ 처리 중: https://youtu.be/{vid}")

        script_raw = fetch_transcript_text(vid)
        ko_script  = translate_to_korean(script_raw)

        if not is_cooking_video(ko_script):
            print("⏭️ 스킵: 조리 과정 아님")
            continue

        cat = classify_category(ko_script)
        if cat not in DETAILED_CATEGORIES:
            print(f"⏭️ 스킵: 허용되지 않은 카테고리 ({cat})")
            continue

        cook_time = parse_cook_time(ko_script) or 0
        ingredients = extract_ingredients(ko_script)

        props = {
            "VideoID":     {"title":[{"text":{"content":vid}}]},
            "URL":         {"url":f"https://youtu.be/{vid}"},
            "Category":    {"select":{"name":cat}},
            "CookTime":    {"number":cook_time},
            "Ingredients": {"rich_text":[{"text":{"content":"\n".join(ingredients)}}]}
        }
        notion.pages.create(parent={"database_id":NOTION_DB_ID}, properties=props)
        uploaded += 1
        print(f"✅ 업로드 완료 ({uploaded}/{MAX_PER_DAY})")

        time.sleep(1)

    print(f"\n완료: 총 {uploaded}개 업로드했습니다.")

if __name__ == "__main__":
    main()
