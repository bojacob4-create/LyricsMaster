import os
import logging
import requests
from typing import Optional, Dict

logger = logging.getLogger(__name__)

def get_person_info(name: str) -> Optional[Dict[str, str]]:
    """
    Get AI-generated information about a person using HuggingFace's free endpoint.

    Args:
        name (str): Name of the person to search for

    Returns:
        Optional[Dict[str, str]]: Dictionary containing title and information if found
    """
    try:
        # API endpoint for generating text
        url = "https://api-inference.huggingface.co/models/gpt2"

        # Create a prompt focused on music-related information
        prompt = f"""Here's information about {name}:
        {name} is known for their contributions to music. Some key details about their career include:
        - Their musical style and achievements
        - Popular songs and albums
        - Impact on the music industry
        - Awards and recognition"""

        # Make request to the free endpoint
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            url,
            headers=headers,
            json={
                "inputs": prompt,
                "parameters": {
                    "max_length": 250,
                    "num_return_sequences": 1,
                    "temperature": 0.7,
                    "top_k": 50,
                    "return_full_text": False
                }
            },
            timeout=10
        )

        # Log the response for debugging
        logger.debug(f"API Status Code: {response.status_code}")
        logger.debug(f"API Response Headers: {response.headers}")

        if response.status_code != 200:
            logger.error(f"API request error: {response.status_code}")
            logger.error(f"Response content: {response.text}")
            return None

        response_json = response.json()
        logger.debug(f"API Response: {response_json}")

        # Extract and clean up the generated text
        if isinstance(response_json, list) and len(response_json) > 0:
            generated_text = response_json[0].get('generated_text', '')
        else:
            generated_text = response_json.get('generated_text', '')

        # Clean up and format the text
        cleaned_text = generated_text.replace('\n\n', '\n').strip()

        # Add emoji indicators for better readability
        formatted_text = (
            "🎵 Musical Style:\n" +
            cleaned_text.split('\n')[0] + "\n\n" +
            "🏆 Achievements:\n" +
            '\n'.join(cleaned_text.split('\n')[1:])
        )

        return {
            "title": name,
            "info": formatted_text
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error getting person info: {str(e)}")
        return None