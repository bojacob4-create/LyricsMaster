import logging
import requests
from urllib.parse import quote
from typing import Optional, Dict
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Configure retries for requests
retry_strategy = Retry(
    total=3,  # number of retries
    backoff_factor=0.5,  # wait 0.5s * (2 ** retry) between retries
    status_forcelist=[429, 500, 502, 503, 504],  # retry on these status codes
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session = requests.Session()
session.mount("https://", adapter)
session.mount("http://", adapter)

def get_wikipedia_info(person_name: str) -> Optional[Dict[str, str]]:
    """
    Get Wikipedia information about a person.

    Args:
        person_name (str): Name of the person to search

    Returns:
        Optional[Dict[str, str]]: Dictionary containing link and extract if found
    """
    try:
        # Clean and encode the search term
        search_term = quote(person_name.strip())
        logger.info(f"Searching Wikipedia for: {person_name}")

        # First, search for the page
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            'action': 'query',
            'list': 'search',
            'srsearch': f"{search_term} musician singer artist",  # Improve relevance for music-related results
            'format': 'json',
            'srprop': 'snippet',
            'srlimit': 1  # Limit to 1 result
        }

        logger.debug(f"Making search request with params: {search_params}")
        search_response = session.get(search_url, params=search_params, timeout=10)
        search_response.raise_for_status()  # Raise exception for non-200 status codes

        search_data = search_response.json()
        if not search_data.get('query', {}).get('search'):
            logger.info(f"No Wikipedia results found for {person_name}")
            return None

        # Get the first result's page ID
        first_result = search_data['query']['search'][0]
        page_id = first_result['pageid']
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
        page_response = session.get(search_url, params=page_params, timeout=10)
        page_response.raise_for_status()

        page_data = page_response.json()
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
            # Try to break at a sentence boundary
            truncated = extract[:max_length].rsplit('.', 1)[0]
            extract = truncated + '...'

        result = {
            'title': page.get('title', ''),
            'extract': extract,
            'link': f"https://en.wikipedia.org/wiki/{quote(page.get('title', '').replace(' ', '_'))}"
        }

        logger.info(f"Successfully retrieved Wikipedia info for {person_name}")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error getting Wikipedia info: {str(e)}")
        return None
    except KeyError as e:
        logger.error(f"KeyError processing Wikipedia response: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting Wikipedia info: {str(e)}", exc_info=True)
        return None