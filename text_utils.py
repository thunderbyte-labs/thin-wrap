"""Text processing and encoding utilities"""
import config
import tiktoken
# Global tokenizer encoding cache
_tokenizer_encoding = None

def get_tokenizer_encoding():
    """Get or create a tiktoken encoding instance with caching."""
    global _tokenizer_encoding
        
    if _tokenizer_encoding is None:
        # Use cl100k_base encoding which is the most modern and used by GPT-3.5-turbo and GPT-4
        # This provides a good balance of accuracy for most text
        _tokenizer_encoding = tiktoken.get_encoding("cl100k_base")
    
    return _tokenizer_encoding

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
    """
    Exact token counting using tiktoken's cl100k_base encoding.
    
    This provides professional-grade token estimation that is:
    - Exact: Uses the same tokenization as OpenAI's models0
    - Fast: tiktoken is optimized for performance
    - Model-agnostic: Uses modern encoding suitable for most text
    
    Args:
        text: Input text to tokenize
        
    Returns:
        Exact token count using tiktoken
        
    Raises:
        ImportError: If tiktoken is not installed
    """
    if not text:
        return 0
    
    encoding = get_tokenizer_encoding()
    return len(encoding.encode(text))

def truncate_for_preview(text, max_length=None):
    """Truncate text for preview display"""
    if max_length is None:
        max_length = config.PREVIEW_MAX_LENGTH
    if len(text) > max_length:
        return text[:max_length] + "\n... [truncated for preview] ..."
    return text

def clear_tokenizer_cache():
    """Clear the tokenizer encoding cache."""
    global _tokenizer_encoding
    _tokenizer_encoding = None
