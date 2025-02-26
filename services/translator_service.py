from googletrans import Translator
from typing import Optional

# Initialize translator
translator = Translator()

def translate_to_arabic(text: str) -> Optional[str]:
    """
    Translate text to Arabic.

    Args:
        text (str): Text to translate

    Returns:
        Optional[str]: Translated text if successful, None otherwise
    """
    try:
        # Split text into smaller chunks to avoid length limitations
        chunks = [text[i:i+500] for i in range(0, len(text), 500)]
        translated_chunks = []

        for chunk in chunks:
            translation = translator.translate(chunk, dest='ar')
            translated_chunks.append(translation.text)

        return '\n'.join(translated_chunks)
    except Exception as e:
        print(f"Error translating text: {e}")
        return None