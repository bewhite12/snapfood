import os, random, time, requests
from googleapiclient.discovery import build
from notion_client import Client

# ─ 환경변수
YOUTUBE_API_KEY      = os.environ['YOUTUBE_API_KEY']
NOTION_TOKEN         = os.environ['NOTION_TOKEN']
NOTION_DATABASE_ID   = os.environ['NOTION_DATABASE_ID']
SPOONACULAR_KEY      = os.environ['SPOONACULAR_KEY']
PLACES_API_KEY       = os.environ.get('PLACES_API_KEY')    # 맛집
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')    # 썸네일 생성

# ─ 클라이언트 초기화
yt   = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
notion = Client(auth=NOTION_TOKEN)

def fetch_videos():
    resp = yt.videos().list(
        part="snippet,statistics",
        chart="mostPopular",
        regionCode="KR",
        maxResults=50
    ).execute()
    return resp['items']

def fetch_recipe_detail(title):
    # Spoonacular 예시
    search = requests.get(
        'https://api.spoonacular.com/recipes/complexSearch',
        params={'apiKey': SPOONACULAR_KEY, 'query': title, 'number': 1}
    ).json()
    if not search['results']:
        return {}
    rid = search['results'][0]['id']
    info = requests.get(
        f'https://api.spoonacular.com/recipes/{rid}/information',
        params={'apiKey': SPOONACULAR_KEY, 'includeNutrition': True}
    ).json()
    return {
        'Ingredients': '\n'.join(i['original'] for i in info.get('extendedIngredients', [])),
        'CookTime': info.get('readyInMinutes', 0),
        'Instructions': info.get('instructions', ''),
        'Calories': next((n['amount'] for n in info['nutrition']['nutrients']
                          if n['title']=='Calories'), 0)
    }

def fetch_restaurant(recipe_name):
    # Google Places 예시
    url = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
    res = requests.get(url, params={
        'key': PLACES_API_KEY,
        'query': f'{recipe_name} 맛집 서울'
    }).json()
    if not res.get('results'):
        return {}
    r = res['results'][0]
    return {
        'RestaurantName': r.get('name',''),
        'RestaurantURL': f"https://www.google.com/maps/place/?q=place_id:{r['place_id']}"
    }

def generate_thumbnail(title, video_id):
    # OpenAI Image 생성 예시
    headers = {'Authorization': f'Bearer {OPENAI_API_KEY}'}
    payload = {
        "prompt": f"A high-resolution photo of {title}, focus on the dish only. If a famous chef, include a small photo of them bottom-left.",
        "n": 1,
        "size": "800x450"
    }
    r = requests.post("https://api.openai.com/v1/images/generations", json=payload, headers=headers).json()
    url = r['data'][0]['url']
    # S3나 public 폴더에 저장 로직 추가 필요 (별도 구현)
    return url

if __name__ == "__main__":
    videos = fetch_videos()
    selected = random.sample(videos, min(100, len(videos)))

    for v in selected:
        title = v['snippet']['title']
        detail = fetch_recipe_detail(title)
        rest   = fetch_restaurant(title)
        thumb_url = generate_thumbnail(title, v['id'])

        properties = {
            'VideoID':      {'title':[{'text':{'content': v['id']}}]},
            'Title':        {'rich_text':[{'text':{'content': title}}]},
            'Views':        {'number': int(v['statistics'].get('viewCount',0))},
            'URL':          {'url': f"https://youtu.be/{v['id']}"},
            'Channel':      {'rich_text':[{'text':{'content':v['snippet']['channelTitle']}}]},
            'Category':     {'select':{'name': random.choice(['한식','양식','일식'])}},
            'Ingredients':  {'rich_text':[{'text':{'content': detail.get('Ingredients','')}}]},
            'CookTime':     {'number': detail.get('CookTime',0)},
            'Instructions': {'rich_text':[{'text':{'content': detail.get('Instructions','')}}]},
            'Calories':     {'number': detail.get('Calories',0)},
            'RestaurantName': {'rich_text':[{'text':{'content': rest.get('RestaurantName','')}}]},
            'RestaurantURL':  {'url': rest.get('RestaurantURL','')},
            'ThumbnailURL':   {'url': thumb_url},
        }

        notion.pages.create(
            parent={'database_id': NOTION_DATABASE_ID},
            properties=properties
        )
        time.sleep(1)  # API 페이싱

    print("✅ Notion 업데이트 완료!")
