import logging
import requests
from typing import Optional, Dict

logger = logging.getLogger(__name__)

session = requests.Session()
session.headers.update({
    'User-Agent': 'LyricsMasterBot/1.0 (Telegram music bot; educational project)'
})


def _search_wikipedia(query: str) -> Optional[Dict]:
    try:
        sr = session.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'list': 'search', 'srsearch': query,
            'srlimit': 3, 'format': 'json'
        }, timeout=8)

        if sr.status_code != 200:
            return None

        results = sr.json().get('query', {}).get('search', [])
        if not results:
            return None

        music_keywords = ['singer', 'musician', 'rapper', 'band', 'artist', 'songwriter',
                         'album', 'song', 'music', 'record', 'hip hop', 'pop', 'rock',
                         'r&b', 'genre', 'grammy', 'chart', 'single', 'vocalist']

        best = results[0]
        for r in results:
            snippet_lower = r.get('snippet', '').lower()
            if any(k in snippet_lower for k in music_keywords):
                best = r
                break

        return best

    except Exception as e:
        logger.debug(f"Wikipedia search error: {e}")
        return None


def _get_wikipedia_extract(title: str) -> Optional[str]:
    try:
        r = session.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'titles': title, 'prop': 'extracts',
            'exintro': True, 'explaintext': True, 'format': 'json'
        }, timeout=8)

        if r.status_code != 200:
            return None

        pages = r.json().get('query', {}).get('pages', {})
        for pid, page in pages.items():
            if pid == '-1':
                return None
            extract = page.get('extract', '')
            if extract:
                return extract

        return None

    except Exception as e:
        logger.debug(f"Wikipedia extract error: {e}")
        return None


def _get_wikipedia_url(title: str) -> str:
    return f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"


def _format_extract(extract: str, max_length: int = 1500) -> str:
    if len(extract) <= max_length:
        return extract

    sentences = extract.split('. ')
    result = []
    current_length = 0

    for sentence in sentences:
        if current_length + len(sentence) > max_length:
            break
        result.append(sentence)
        current_length += len(sentence) + 2

    text = '. '.join(result)
    if not text.endswith('.'):
        text += '.'
    return text


_DISAMBIGUATION_MARKERS = [
    'may refer to:', 'can refer to:', 'may also refer to:',
    'commonly refers to:', 'is a disambiguation',
    'most commonly refers to',
]


def _is_disambiguation(extract: str) -> bool:
    if not extract:
        return False
    first_lines = extract[:500].lower()
    return any(marker in first_lines for marker in _DISAMBIGUATION_MARKERS)


def _try_exact_page(query: str) -> Optional[str]:
    try:
        r = session.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'titles': query, 'prop': 'extracts',
            'exintro': True, 'explaintext': True, 'format': 'json',
            'redirects': 1
        }, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json().get('query', {})
        pages = data.get('pages', {})
        for pid, page in pages.items():
            if pid == '-1':
                return None
            extract = page.get('extract', '').strip()
            if extract and not _is_disambiguation(extract):
                return page['title']
        return None
    except Exception:
        return None


def get_person_info(name: str) -> Optional[Dict[str, str]]:
    try:
        name = name.strip()
        if not name:
            return None

        title = None
        extract = None

        exact_title = _try_exact_page(name)
        if exact_title:
            title = exact_title
            extract = _get_wikipedia_extract(title)
            if extract and _is_disambiguation(extract):
                title = None
                extract = None

        if not title:
            search_result = _search_wikipedia(f"{name} musician singer")
            if not search_result:
                search_result = _search_wikipedia(name)
            if not search_result:
                return None
            title = search_result['title']
            extract = _get_wikipedia_extract(title)

        if not extract or _is_disambiguation(extract):
            return None

        formatted = _format_extract(extract)
        wiki_url = _get_wikipedia_url(title)

        paragraphs = formatted.split('\n')
        clean_paragraphs = [p.strip() for p in paragraphs if p.strip()]
        formatted = '\n\n'.join(clean_paragraphs)

        info = (
            f"{formatted}\n\n"
            f"🔗 Read more: {wiki_url}"
        )

        return {
            "title": title,
            "info": info
        }

    except Exception as e:
        logger.error(f"Error getting person info: {e}")
        return None
