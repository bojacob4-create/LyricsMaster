import logging
import requests
from urllib.parse import quote
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
    Get Wikipedia information about a person.

    Args:
        person_name (str): Name of the person to search

    Returns:
        Optional[Dict[str, str]]: Dictionary containing link and extract if found
    """
    try:
        # Clean up search terms
        person_name = person_name.strip().replace("'", "'").replace('"', '')

        logger.info(f"Searching Wikipedia for: {person_name}")

        # First, search for the page
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            'action': 'query',
            'list': 'search',
            'srsearch': f"{quote(person_name, safe='')} musician singer artist",  # Improve relevance for music-related results
            'format': 'json',
            'srprop': 'snippet',
            'srlimit': 1  # Limit to 1 result
        }

        logger.debug(f"Making search request with params: {search_params}")
        search_response = session.get(search_url, params=search_params, timeout=15)

        # Log the response details
        logger.debug(f"Search response status code: {search_response.status_code}")
        logger.debug(f"Search response content: {search_response.text[:500]}")  # Log first 500 chars of response

        search_response.raise_for_status()
        search_data = search_response.json()

        # Log the search data for debugging
        logger.debug(f"Search data: {search_data}")

        search_results = search_data.get('query', {}).get('search', [])
        if not search_results:
            logger.info(f"No Wikipedia results found for {person_name}")
            # Try alternative search without additional terms
            search_params['srsearch'] = quote(person_name, safe='')
            logger.debug("Trying alternative search without additional terms")
            search_response = session.get(search_url, params=search_params, timeout=15)
            search_response.raise_for_status()
            search_data = search_response.json()
            search_results = search_data.get('query', {}).get('search', [])
            if not search_results:
                # Try one last time with basic alphanumeric characters
                logger.debug("All endpoints failed, trying one last time with simplified terms")
                person_simple = ''.join(c for c in person_name if c.isalnum() or c.isspace()).strip()
                if person_simple != person_name:
                    logger.debug(f"Attempting with simplified terms: {person_simple}")
                    search_params['srsearch'] = quote(person_simple, safe='')
                    search_response = session.get(search_url, params=search_params, timeout=15)
                    search_response.raise_for_status()
                    search_data = search_response.json()
                    search_results = search_data.get('query', {}).get('search', [])
                    if not search_results:
                        return None
                else:
                    return None

        # Get the first result's page ID
        page_id = search_results[0]['pageid']
        logger.debug(f"Found page ID: {page_id}")

        # Get page details
        page_params = {
            'action': 'query',
            'prop': 'extracts|info',
            'exintro': True,
            'explaintext': True,
            'inprop': 'url',
            'pageids': page_id,
            'format': 'json'
        }

        logger.debug(f"Making page details request with params: {page_params}")
        page_response = session.get(search_url, params=page_params, timeout=15)

        # Log the response details
        logger.debug(f"Page details response status code: {page_response.status_code}")
        logger.debug(f"Page details response content: {page_response.text[:500]}")

        page_response.raise_for_status()
        page_data = page_response.json()

        if 'query' not in page_data or 'pages' not in page_data['query']:
            logger.error("Unexpected API response structure")
            logger.debug(f"Full API response: {page_data}")
            return None

        page = page_data['query']['pages'][str(page_id)]

        # Extract content and format it
        extract = page.get('extract', '')
        if not extract:
            logger.warning(f"No extract found for page ID: {page_id}")
            return None

        # Clean up and format the extract
        extract = extract.replace('\n', ' ').strip()

        # Limit extract length and add ellipsis if needed
        max_length = 300
        if len(extract) > max_length:
            truncated = extract[:max_length].rsplit('.', 1)[0]
            extract = truncated + '...'

        result = {
            'title': page.get('title', ''),
            'extract': extract,
            'link': f"https://en.wikipedia.org/wiki/{quote(page.get('title', '').replace(' ', '_'), safe='')}"
        }

        logger.info(f"Successfully retrieved Wikipedia info for {person_name}")
        return result

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout while fetching Wikipedia info for {person_name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error getting Wikipedia info: {str(e)}")
        return None
    except KeyError as e:
        logger.error(f"KeyError processing Wikipedia response: {str(e)}")
        logger.debug("Response data structure issue", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting Wikipedia info: {str(e)}", exc_info=True)
        return None