import logging
import requests
from typing import Optional, Dict
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Configure retries for requests
retry_strategy = Retry(
    total=5,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

adapter = HTTPAdapter(
    max_retries=retry_strategy,
    pool_connections=10,
    pool_maxsize=10,
    pool_block=False
)
session = requests.Session()
session.mount('http://', adapter)
session.mount('https://', adapter)

def get_wikipedia_info(person_name: str) -> Optional[Dict[str, str]]:
    """
    Get Wikipedia information about a person using the OpenSearch API.

    Args:
        person_name (str): Name of the person to search

    Returns:
        Optional[Dict[str, str]]: Dictionary containing link and extract if found
    """
    try:
        # Clean up search terms
        person_name = person_name.strip()
        logger.info(f"Searching Wikipedia for: {person_name}")

        # Use opensearch API to find the exact page
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            'action': 'opensearch',
            'search': person_name,
            'limit': 1,
            'namespace': 0,
            'format': 'json'
        }

        logger.debug(f"Making opensearch request with params: {search_params}")
        search_response = session.get(search_url, params=search_params, timeout=15)
        search_response.raise_for_status()

        # opensearch returns [query, [titles], [descriptions], [urls]]
        results = search_response.json()
        if not results[1]:  # No titles found
            logger.info(f"No Wikipedia results found for {person_name}")
            return None

        title = results[1][0]
        page_url = results[3][0]

        # Get the full page content
        content_params = {
            'action': 'query',
            'prop': 'extracts',
            'exintro': True,
            'explaintext': True,
            'titles': title,
            'format': 'json'
        }

        content_response = session.get(search_url, params=content_params, timeout=15)
        content_response.raise_for_status()

        page_data = content_response.json()
        pages = page_data['query']['pages']
        page = next(iter(pages.values()))

        extract = page.get('extract', '')
        if not extract:
            logger.warning(f"No extract found for page: {title}")
            return None

        # Clean up and format the extract
        extract = extract.replace('\n', ' ').strip()

        # Limit extract length and add ellipsis if needed
        max_length = 300
        if len(extract) > max_length:
            truncated = extract[:max_length].rsplit('.', 1)[0]
            extract = truncated + '...'

        return {
            'title': title,
            'extract': extract,
            'link': page_url
        }

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout while fetching Wikipedia info for {person_name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error getting Wikipedia info: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting Wikipedia info: {str(e)}", exc_info=True)
        return None