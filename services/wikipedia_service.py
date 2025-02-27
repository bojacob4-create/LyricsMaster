import logging
import requests
from urllib.parse import quote
from typing import Optional, Dict

logger = logging.getLogger(__name__)

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
            'srsearch': search_term,
            'format': 'json',
            'srprop': 'snippet'
        }

        search_response = requests.get(search_url, params=search_params)
        logger.debug(f"Search response status: {search_response.status_code}")

        if search_response.status_code != 200:
            logger.warning(f"Wikipedia search failed for {person_name}")
            return None

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
            'prop': 'info|extracts',
            'exintro': 1,
            'explaintext': 1,
            'inprop': 'url',
            'pageids': page_id,
            'format': 'json'
        }

        page_response = requests.get(search_url, params=page_params)
        logger.debug(f"Page details response status: {page_response.status_code}")

        if page_response.status_code != 200:
            logger.warning(f"Failed to get page details for {person_name}")
            return None

        page_data = page_response.json()
        page = page_data['query']['pages'][str(page_id)]

        result = {
            'title': page.get('title', ''),
            'link': f"https://en.wikipedia.org/wiki/{quote(page.get('title', '').replace(' ', '_'))}",
            'extract': page.get('extract', '')[:200] + '...' if page.get('extract') else ''
        }

        logger.info(f"Successfully retrieved Wikipedia info for {person_name}")
        return result

    except Exception as e:
        logger.error(f"Error getting Wikipedia info: {str(e)}", exc_info=True)
        return None