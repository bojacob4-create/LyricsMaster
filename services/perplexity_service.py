import os
import logging
import requests
from typing import Optional, Dict

logger = logging.getLogger(__name__)

def get_person_info(name: str) -> Optional[Dict[str, str]]:
    """
    Get AI-generated information about a person using Perplexity API.
    
    Args:
        name (str): Name of the person to search for
        
    Returns:
        Optional[Dict[str, str]]: Dictionary containing title and information if found
    """
    try:
        api_key = os.environ.get("PERPLEXITY_API_KEY")
        if not api_key:
            logger.error("PERPLEXITY_API_KEY not found in environment variables")
            return None

        url = "https://api.perplexity.ai/chat/completions"
        
        prompt = f"""
        Provide key information about {name}, focusing on their career highlights, achievements, and impact on music.
        Include only verified facts. Be concise but informative.
        Format the response in clear sections with emojis.
        Limit the response to 3-4 short paragraphs.
        """

        payload = {
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a knowledgeable assistant that provides accurate and concise information about musicians and artists."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 0.9
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        if not data.get("choices"):
            logger.error("No choices in Perplexity API response")
            return None
            
        content = data["choices"][0]["message"]["content"]
        
        return {
            "title": name,
            "info": content,
            "citations": data.get("citations", [])
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error getting person info: {str(e)}")
        return None
