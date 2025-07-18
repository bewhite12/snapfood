import os
import random
import time
import json
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from notion_client import Client
import openai

# ─ 환경변수 읽기 ──────────────────────────────────────────
YOUTUBE_API_KEY      = os.environ['YOUTUBE_API_KEY']
OPENAI_API_KEY       = os.environ['OPENAI_API_KEY']
NOTION_TOKEN         = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID   = os.environ['NOTION_DATABASE_ID']

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

