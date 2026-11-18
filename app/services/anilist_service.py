import html
import re
import requests
from flask import current_app

_MANGA_FIELDS = '''
  id
  title { romaji english native }
  description
  coverImage { large extraLarge }
  bannerImage
  genres
  status
  chapters
  averageScore
  popularity
  startDate { year month day }
  siteUrl
'''


def _api_url():
    try:
        return current_app.config.get('ANILIST_API_URL', 'https://graphql.anilist.co')
    except RuntimeError:
        return 'https://graphql.anilist.co'


def _graphql_request(query, variables=None):
    payload = {'query': query, 'variables': variables or {}}
    try:
        response = requests.post(
            _api_url(),
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if 'errors' in data:
            return None, data.get('errors')
        return data.get('data'), None
    except (requests.RequestException, ValueError):
        return None, 'Unable to contact AniList API. Please try again later.'


def sanitize_html_text(raw_text):
    """
    Remove tags potencialmente perigosas (scripts, iframes, atributos de eventos como onload/onerror)
    e converte <br> em quebras de linha limpas para prevenir XSS.
    """
    if not raw_text:
        return ''
    # Normaliza quebras de linha HTML
    text = re.sub(r'<\s*br\s*/?\s*>', '\n', str(raw_text), flags=re.IGNORECASE)
    # Remove tags perigosas e scripts inteiros
    text = re.sub(r'<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>', '', text, flags=re.IGNORECASE)
    # Remove qualquer tag HTML remanescente
    text = re.sub(r'<[^>]+>', '', text)
    # Desescapa entidades HTML seguras
    text = html.unescape(text)
    return text.strip()


def _sanitize_media_items(items):
    """Sanitiza os campos de descrição de cada item retornado pela API."""
    if not items:
        return items
    for item in items:
        if isinstance(item, dict) and 'description' in item and item['description']:
            item['description'] = sanitize_html_text(item['description'])
    return items


def _get_manga_page(query, variables):
    data, error = _graphql_request(query, variables)
    if error or not data:
        return [], error
    media_list = data.get('Page', {}).get('media', [])
    return _sanitize_media_items(media_list), None



def get_manga_search_results(query_text, page=1, genre=None):
    if genre:
        query = f'''
        query ($search: String, $page: Int, $genre: String) {{
          Page(page: $page, perPage: 10) {{
            media(search: $search, genre: $genre, type: MANGA, sort: POPULARITY_DESC) {{
              {_MANGA_FIELDS}
            }}
          }}
        }}
        '''
        return _get_manga_page(query, {'search': query_text, 'page': page, 'genre': genre})

    query = f'''
    query ($search: String, $page: Int) {{
      Page(page: $page, perPage: 10) {{
        media(search: $search, type: MANGA, sort: POPULARITY_DESC) {{
          {_MANGA_FIELDS}
        }}
      }}
    }}
    '''
    return _get_manga_page(query, {'search': query_text, 'page': page})


def get_popular_manga(page=1, per_page=10, genre=None):
    if genre:
        query = f'''
        query ($page: Int, $perPage: Int, $genre: String) {{
          Page(page: $page, perPage: $perPage) {{
            media(genre: $genre, type: MANGA, sort: POPULARITY_DESC) {{
              {_MANGA_FIELDS}
            }}
          }}
        }}
        '''
        return _get_manga_page(query, {'page': page, 'perPage': per_page, 'genre': genre})

    query = f'''
    query ($page: Int, $perPage: Int) {{
      Page(page: $page, perPage: $perPage) {{
        media(type: MANGA, sort: POPULARITY_DESC) {{
          {_MANGA_FIELDS}
        }}
      }}
    }}
    '''
    return _get_manga_page(query, {'page': page, 'perPage': per_page})


def get_recent_manga(page=1, per_page=10):
    query = f'''
    query ($page: Int, $perPage: Int, $startDateGreater: FuzzyDateInt) {{
      Page(page: $page, perPage: $perPage) {{
        media(
          type: MANGA,
          sort: START_DATE_DESC,
          startDate_greater: $startDateGreater
        ) {{
          {_MANGA_FIELDS}
        }}
      }}
    }}
    '''
    from datetime import datetime, timezone

    start_date_greater = (datetime.now(timezone.utc).year - 3) * 10000
    return _get_manga_page(
        query,
        {
            'page': page,
            'perPage': per_page,
            'startDateGreater': start_date_greater,
        },
    )


def get_manga_by_id(manga_id):
    query = f'''
    query ($id: Int) {{
      Media(id: $id, type: MANGA) {{
        {_MANGA_FIELDS}
        staff {{
          edges {{
            role
            node {{ __typename ... on Staff {{ name {{ full }} }} }}
          }}
        }}
      }}
    }}
    '''
    data, error = _graphql_request(query, {'id': manga_id})
    if error or not data:
        return None, error
    media = data.get('Media')
    if media and isinstance(media, dict) and 'description' in media and media['description']:
        media['description'] = sanitize_html_text(media['description'])
    return media, None


def fetch_portuguese_synopsis(title, fallback_english_synopsis=None):
    """
    Função facilitadora exposta em anilist_service para obter sinopse em português
    via MangaDex API com fallback de tradução.
    """
    from app.services.mangadex_service import fetch_portuguese_synopsis as _fetch_md
    return _fetch_md(title=title, fallback_english_synopsis=fallback_english_synopsis)

