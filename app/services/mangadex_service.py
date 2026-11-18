import logging
import re
import requests
from flask import current_app

logger = logging.getLogger(__name__)

MANGADEX_BASE_URL = 'https://api.mangadex.org'
REQUEST_TIMEOUT = 5  # Segundos para requisição rápida sem travar a navegação


def _clean_markdown_and_links(text):
    """
    Remove formatações residuais de Markdown, links e anotações comuns em sinopses
    (ex.: [Source: ...], markdown links [texto](url), formatações negrito/itálico).
    """
    if not text:
        return ''

    # Remove anotações como [Source: ...] ou [Written by ...] ou --- notas
    cleaned = re.sub(r'\[(?:Source|Written by|Note|Fonte|Origem)[^\]]*\]', '', text, flags=re.IGNORECASE)
    # Transforma links markdown [texto](url) em texto
    cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned)
    # Remove marcações de negrito e itálico markdown
    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)
    cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
    cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
    cleaned = re.sub(r'_([^_]+)_', r'\1', cleaned)
    # Normaliza espaços e quebras de linha
    lines = [line.strip() for line in cleaned.splitlines()]
    result = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                result.append('')
                prev_empty = True
        else:
            result.append(line)
            prev_empty = False
    return '\n'.join(result).strip()


def fetch_portuguese_synopsis(title, fallback_english_synopsis=None):
    """
    Busca sinopse em Português diretamente na MangaDex API.
    1. Consulta GET https://api.mangadex.org/manga com title=<title>, limit=3, order[relevance]=desc.
    2. Percorre os resultados procurando em attributes.description por 'pt-br' ou 'pt'.
    3. Se encontrar, limpa marcações e retorna o texto em português.
    4. Se não encontrar e fallback_english_synopsis tiver sido informado,
       utiliza tradução automática como fallback seguro.
    5. Nunca trava a execução: envolve tudo em try/except e retorna fallback seguro.
    """
    if not title or not str(title).strip():
        return fallback_english_synopsis or ''

    clean_title = str(title).strip()
    headers = {
        'User-Agent': 'MangariTCC/1.0',
        'Accept': 'application/json',
    }

    try:
        # a) Consulta MangaDex API
        search_url = f"{MANGADEX_BASE_URL}/manga"
        params = {
            'title': clean_title,
            'limit': 3,
            'order[relevance]': 'desc',
        }
        res = requests.get(search_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)

        if res.status_code == 200:
            data = res.json().get('data') or []
            # b) Percorre os resultados procurando por 'pt-br' ou 'pt'
            for item in data:
                desc_dict = (item.get('attributes') or {}).get('description') or {}
                for lang_key in ('pt-br', 'pt'):
                    desc_val = desc_dict.get(lang_key)
                    if desc_val and str(desc_val).strip():
                        # c) Limpa formatações Markdown/links residuais
                        cleaned_pt = _clean_markdown_and_links(str(desc_val))
                        if cleaned_pt:
                            logger.info("Found Portuguese synopsis on MangaDex for '%s' (lang: %s)", clean_title, lang_key)
                            return cleaned_pt
    except Exception as exc:
        logger.warning("Failed to fetch Portuguese synopsis from MangaDex for '%s': %s", clean_title, exc)

    # d) Fallback caso MangaDex não possua 'pt-br' / 'pt'
    if fallback_english_synopsis and str(fallback_english_synopsis).strip():
        try:
            from app.services.translation_service import clean_html_tags, translate_text_to_portuguese
            cleaned_html = clean_html_tags(str(fallback_english_synopsis))
            if cleaned_html:
                translated = translate_text_to_portuguese(cleaned_html)
                if translated and translated.strip():
                    return translated.strip()
            return cleaned_html
        except Exception as exc:
            logger.warning("Fallback translation failed for '%s': %s", clean_title, exc)
            return fallback_english_synopsis

    return fallback_english_synopsis or ''



def get_mangadex_chapter_count(title):
    """
    Consulta a API pública do MangaDex para obter o número total/máximo de capítulos
    de uma obra quando a AniList retornar null (típico para obras RELEASING).
    
    Retorna int com o maior número de capítulo inteiro, ou None em caso de falha/inexistência.
    """
    if not title or not title.strip():
        return None

    clean_title = title.strip()
    headers = {
        'User-Agent': 'Mangari-App/1.0 (mangari@local.dev)',
        'Accept': 'application/json',
    }

    try:
        # 1. Buscar a obra pelo título principal
        search_url = f"{MANGADEX_BASE_URL}/manga"
        params = {
            'title': clean_title,
            'limit': 1,
            'order[relevance]': 'desc',
        }
        res = requests.get(search_url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if res.status_code != 200:
            logger.warning("MangaDex search returned status code %s for '%s'", res.status_code, clean_title)
            return None

        search_data = res.json()
        manga_list = search_data.get('data') or []
        if not manga_list:
            return None

        mangadex_id = manga_list[0].get('id')
        if not mangadex_id:
            return None

        # 2. Consultar o aggregate ou feed do mangá para obter o maior capítulo
        # O endpoint aggregate agrupa todos os volumes e capítulos da obra
        aggregate_url = f"{MANGADEX_BASE_URL}/manga/{mangadex_id}/aggregate"
        res_agg = requests.get(aggregate_url, headers=headers, timeout=REQUEST_TIMEOUT)
        
        max_chapter = None
        if res_agg.status_code == 200:
            agg_data = res_agg.json()
            volumes = agg_data.get('volumes') or {}
            chapter_numbers = []
            for vol in volumes.values():
                ch_dict = vol.get('chapters') or {}
                for ch_key in ch_dict.keys():
                    try:
                        num = float(ch_key)
                        chapter_numbers.append(num)
                    except (ValueError, TypeError):
                        continue
            if chapter_numbers:
                max_chapter = int(max(chapter_numbers))

        # Fallback se aggregate não retornar números válidos: feed ordenado por capítulo desc
        if not max_chapter or max_chapter <= 0:
            feed_url = f"{MANGADEX_BASE_URL}/manga/{mangadex_id}/feed"
            feed_params = {
                'order[chapter]': 'desc',
                'limit': 1,
            }
            res_feed = requests.get(feed_url, params=feed_params, headers=headers, timeout=REQUEST_TIMEOUT)
            if res_feed.status_code == 200:
                feed_data = res_feed.json()
                feed_items = feed_data.get('data') or []
                if feed_items:
                    ch_attr = feed_items[0].get('attributes', {}).get('chapter')
                    if ch_attr:
                        try:
                            max_chapter = int(float(ch_attr))
                        except (ValueError, TypeError):
                            pass

        if max_chapter and max_chapter > 0:
            logger.info("MangaDex chapter count for '%s': %d", clean_title, max_chapter)
            return max_chapter

        return None
    except Exception as exc:
        logger.warning("MangaDex API request failed for '%s': %s", clean_title, exc)
        return None
