import os, random
from notion_client import Client
from googleapiclient.discovery import build

# 환경변수로부터 키/토큰 불러오기
YOUTUBE_API_KEY    = os.environ['YOUTUBE_API_KEY']
NOTION_TOKEN       = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID = os.environ['NOTION_DATABASE_ID']

# YouTube Data API 초기화
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
search_res = youtube.search().list(
    q='레시피',
    part='id',
    type='video',
    order='viewCount',
    maxResults=50
).execute()
video_ids = [i['id']['videoId'] for i in search_res['items']]

stats_res = youtube.videos().list(
    part='snippet,statistics',
    id=','.join(video_ids)
).execute()
qualified = [
    v for v in stats_res['items']
    if int(v['statistics'].get('viewCount', 0)) >= 100000
]

count = min(100, len(qualified))
selected = random.sample(qualified, count)

# Notion 클라이언트 초기화
notion = Client(auth=NOTION_TOKEN)

# (원하면 기존 레코드 삭제)
# pages = notion.databases.query(database_id=NOTION_DATABASE_ID).get('results', [])
# for p in pages:
#     notion.pages.update(page_id=p['id'], archived=True)

# 새 레코드 생성
for v in selected:
    notion.pages.create(
        parent={'database_id': NOTION_DATABASE_ID},
        properties={
            'VideoID': {
                'title': [{'text': {'content': v['id']}}]
            },
            'Title': {
                'rich_text': [{'text': {'content': v['snippet']['title']}}]
            },
            'Views': {
                'number': int(v['statistics']['viewCount'])
            },
            'URL': {
                'url': f"https://youtu.be/{v['id']}"
            },
            'Channel': {
                'rich_text': [{'text': {'content': v['snippet']['channelTitle']}}]
            },
            'Category': {
                'select': {
                    'name': random.choice(['한식','양식','일식'])
                }
            }
        }
    )
print(f"✅ {count}개 레시피를 Notion에 업데이트 완료.")
