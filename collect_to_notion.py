import os
import re
import time
import random
from notion_client import Client as NotionClient
from googleapiclient.discovery import build as build_youtube
from youtube_transcript_api import YouTubeTranscriptApi
import openai

# ───────────────────────────────────────────────
# 환경변수 읽기
YOUTUBE_API_KEY      = os.getenv('YOUTUBE_API_KEY')
NOTION_TOKEN         = os.getenv('NOTION_TOKEN')
NOTION_DATABASE_ID   = os.getenv('NOTION_DATABASE_ID')
OPENAI_API_KEY       = os.getenv('OPENAI_API_KEY')

openai.api_key = OPENAI_API_KEY

# ───────────────────────────────────────────────
# 설정값
SEARCH_QUERY        = "레시피"          # 유튜브 탐색 키워드
MAX_PER_DAY         = 10               # 하루 최대 아이템
DETAILED_CATEGORIES = [
    '한식-볶음', '양식-파스타', '디저트-케이크',
    # ...필요한 카테고리를 더 추가
]

# ───────────────────────────────────────────────
# 유튜브 클라이언트
youtube = build_youtube('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# 노션 클라이언트
notion = NotionClient(auth=NOTION_TOKEN)

# ───────────────────────────────────────────────
def fetch_videos(query, max_results=50):
    resp = youtube.search().list(
        q=query, part='id,snippet',
        type='video', maxResults=max_results,
        order='viewCount'
    ).execute()
    videos = []
    for item in resp['items']:
        videos.append({
            'id': item['id']['videoId'],
            'title': item['snippet']['title'],
            'channel': item['snippet']['channelTitle'],
            'views': 0
        })
    return videos

def get_existing_ids():
    existing = []
    rsp = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=100)
    for p in rsp.get('results', []):
        vid = p['properties']['VideoID']['title'][0]['text']['content']
        existing.append(vid)
    return set(existing)

def is_cooking_video(script_text):
    """GPT에게 이 스크립트가 실제 조리 영상인지 물어봄"""
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"당신은 영상 내용이 요리 조리 과정을 담고 있는지 판단하는 전문가입니다."},
            {"role":"user","content":
                "다음 스크립트가 진짜 ‘요리 조리 과정’을 설명하는지 '예' 또는 '아니오'로만 답해주세요:\n\n"
                + script_text
            }
        ]
    )
    answer = resp.choices[0].message.content.strip()
    return answer.startswith("예")

def classify_category(text, choices):
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"당신은 요리 영상의 카테고리를 분류하는 전문가입니다."},
            {"role":"user","content":
                f"아래 요리 설명을 보고, 가능한 한 상세한 카테고리를 선택하세요:\n\n{text}\n\n목록: {choices}"
            }
        ]
    )
    return resp.choices[0].message.content.strip()

def fetch_transcript(vid):
    segs = YouTubeTranscriptApi.get_transcript(vid)
    raw = " ".join(s['text'] for s in segs)
    resp = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role":"system","content":"영어(또는 기타 언어) 영상을 자연스러운 한국어로 번역하세요."},
            {"role":"user","content": raw}
        ]
    )
    return resp.choices[0].message.content

def parse_cook_time(text):
    m = re.search(r"(\d+)", text or "")
    return int(m.group(1)) if m else None

# ───────────────────────────────────────────────
def main():
    print("▶ 유튜브에서 영상 수집 중...")
    videos = fetch_videos(SEARCH_QUERY, max_results=50)
    existing = get_existing_ids()
    candidates = [v for v in videos if v['id'] not in existing]
    selected = random.sample(candidates, min(MAX_PER_DAY, len(candidates)))

    for v in selected:
        vid = v['id']
        print(f"\n• 처리 중: https://youtu.be/{vid}")

        # 1) 통계 가져오기
        stats = youtube.videos().list(id=vid, part='statistics').execute()['items'][0]['statistics']
        v['views'] = int(stats.get('viewCount', 0))

        # 2) 스크립트 + 번역
        script_ko = fetch_transcript(vid)

        # 3) 요리 영상 여부 확인
        if not is_cooking_video(script_ko):
            print("⏭️ 스킵: 조리 과정 영상이 아님")
            continue

        # 4) 카테고리 분류
        chosen_cat = classify_category(script_ko, DETAILED_CATEGORIES)
        if chosen_cat not in DETAILED_CATEGORIES:
            print(f"⏭️ 스킵: 허용된 카테고리 아님 ({chosen_cat})")
            continue

        # 5) 조리시간 요약
        tm_resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system","content":"이 글에서 ‘조리 시간’을 분 단위 숫자로 요약해서 출력하세요."},
                {"role":"user","content": script_ko}
            ]
        )
        cook_time = parse_cook_time(tm_resp.choices[0].message.content)

        # 6) 노션 속성 매핑
        props = {
            "VideoID":    {"title":[{"text":{"content":vid}}]},
            "Views":      {"number":v['views']},
            "URL":        {"url":f"https://youtu.be/{vid}"},
            "Title":      {"rich_text":[{"text":{"content":v['title']}}]},
            "Category":   {"select":{"name":chosen_cat}},
            "Channel":    {"rich_text":[{"text":{"content":v['channel']}}]},
            "CookTime":   {"number": cook_time or 0},
            "Ingredients":{"rich_text":[{"text":{"content":"재료 정보 생략"}}]}
        }

        # 7) 노션에 새 페이지 생성
        notion.pages.create(
            parent={'database_id': NOTION_DATABASE_ID},
            properties=props
        )
        time.sleep(1)  # rate-limit 방지

    print(f"\n✅ Notion에 {len(selected)}개 업데이트 완료!")

if __name__ == "__main__":
    main()
