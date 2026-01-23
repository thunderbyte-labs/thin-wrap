
"""Text processing and encoding utilities"""
import config

def clean_text(text):
    """Clean text by handling encoding issues and non-standard characters"""
    if isinstance(text, bytes):
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'ascii']:
            try:
                text = text.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = text.decode('utf-8', errors='replace')

    for old, new in config.UNICODE_REPLACEMENTS.items():
        text = text.replace(old, new)

    try:
        text.encode('utf-8')
        return text
    except UnicodeEncodeError:
        return ''.join(char if ord(char) < 128 or char.isalnum() or char in ' \n\t.,!?;:()-[]{}' else '?' for char in text)

def estimate_tokens(text):
    """Token estimation using approximate counting"""
    if not text:
        return 0
    chars = len(text)
    words = len(text.split())
    char_est = chars / 4
    word_est = words * 4 / 3
    return max(1, int((char_est + word_est) / 2))

def truncate_for_preview(text, max_length=None):
    """Truncate text for preview display"""
    if max_length is None:
        max_length = config.PREVIEW_MAX_LENGTH
    if len(text) > max_length:
        return text[:max_length] + "\n... [truncated for preview] ..."
    return text
