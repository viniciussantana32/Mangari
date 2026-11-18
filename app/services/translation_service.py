import html
import re
import requests
from flask import current_app

_HTML_TAG_REGEX = re.compile(r'<[^>]+>')
_EXTRA_SPACES = re.compile(r'\s{2,}')


def clean_html_tags(text):
    """
    Remove tags HTML (como <br>, <i>, <b>) e desescapa entidades HTML (&amp;, &#039;, etc.).
    """
    if not text:
        return ''
    # Converte <br> e variações em quebras de linha
    normalized = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
    # Remove as demais tags HTML
    stripped = _HTML_TAG_REGEX.sub('', normalized)
    # Converte entidades HTML (&quot;, etc.)
    unescaped = html.unescape(stripped)
    # Limpa espaços excessivos nas linhas preservando quebras
    lines = [line.strip() for line in unescaped.splitlines()]
    # Remove linhas vazias consecutivas
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


def translate_text_to_portuguese(text, timeout=5):
    """
    Traduz texto (ex: sinopse em inglês) para Português (pt-BR / pt) de forma segura.
    1. Tenta MyMemory API (rápida, pública e sem rate-limit estrito do Google)
    2. Fallback via deep_translator (GoogleTranslator)
    3. Fallback via translate.googleapis.com
    4. Em caso de falha/timeout, preserva o texto original higienizado.
    """
    if not text or not str(text).strip():
        return ''

    cleaned = clean_html_tags(str(text))
    if not cleaned:
        return ''

    # 1. Tentar MyMemory API com segmentação de sentenças/pedaços (< 450 caracteres)
    try:
        # Divide o texto mantendo as quebras de linha estruturais
        lines = cleaned.split('\n')
        translated_lines = []

        for line in lines:
            line_str = line.strip()
            if not line_str:
                translated_lines.append('')
                continue

            # Quebra a linha em sentenças para respeitar o limite de 500 caracteres da API MyMemory
            sentences = re.split(r'(?<=[.!?])\s+', line_str)
            chunks = []
            current = ''
            for s in sentences:
                if len(current) + len(s) + 1 < 450:
                    current = f'{current} {s}'.strip() if current else s
                else:
                    if current:
                        chunks.append(current)
                    current = s
            if current:
                chunks.append(current)

            translated_chunks = []
            for chunk in chunks:
                if not chunk.strip():
                    continue
                resp = requests.get(
                    'https://api.mymemory.translated.net/get',
                    params={'q': chunk, 'langpair': 'en|pt'},
                    headers={'User-Agent': 'MangariApp/1.0'},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    res_text = (data.get('responseData') or {}).get('translatedText')
                    if res_text and not str(res_text).startswith('MYMEMORY WARNING'):
                        translated_chunks.append(res_text)
                    else:
                        raise ValueError('MyMemory returned limit or warning')
                else:
                    raise ValueError(f'MyMemory HTTP {resp.status_code}')

            translated_lines.append(' '.join(translated_chunks))

        if translated_lines:
            result = '\n'.join(translated_lines).strip()
            if result:
                return clean_html_tags(result)
    except Exception as exc:
        if current_app:
            current_app.logger.warning(f'MyMemory translation fallback: {exc}')

    # 2. Tentar deep_translator se disponível
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='auto', target='pt').translate(cleaned)
        if translated and str(translated).strip():
            return clean_html_tags(str(translated))
    except Exception as exc:
        if current_app:
            current_app.logger.warning(f'deep_translator fallback to direct endpoint: {exc}')

    # 3. Fallback direto via API do Google Translate (gtx)
    try:
        url = 'https://translate.googleapis.com/translate_a/single'
        params = {
            'client': 'gtx',
            'sl': 'auto',
            'tl': 'pt',
            'dt': 't',
            'q': cleaned,
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) MangariApp/1.0',
        }
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                translated_parts = [segment[0] for segment in data[0] if segment and segment[0]]
                translated_text = ''.join(translated_parts)
                if translated_text.strip():
                    return clean_html_tags(translated_text)
    except Exception as exc:
        if current_app:
            current_app.logger.warning(f'Fallback translation error: {exc}')

    # 4. Retorno de fallback: texto original limpo
    return cleaned
