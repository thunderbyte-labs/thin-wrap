"""Text processing and encoding utilities"""
import config
import re
import unicodedata
from typing import Optional

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

def estimate_tokens(text: Optional[str]) -> int:
    """
    Token approximation without external dependencies.
    
    This method provides a good estimate of token count for various types of text,
    including CJK characters, code, and natural language.
    
    Enhancements:
    - CJK character detection (Chinese/Japanese/Korean tokenize differently)
    - Better handling of contractions, camelCase, and numbers
    - Unicode normalization awareness
    - Refined code detection heuristics
    - Guardrails for edge cases (empty, very long, repetitive text)
    """
    if not text or not isinstance(text, str):
        return 0
    
    # Normalize to avoid NFD/NFC differences affecting counts
    text = unicodedata.normalize('NFC', text)
    text_len = len(text)
    
    # Fast paths
    if text_len == 0:
        return 0
    if text_len <= 2:
        return 1
    
    # Detect script types
    # CJK Unified Ideographs + Hiragana + Katakana + Hangul
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text))
    has_cjk = cjk_chars > 0
    
    # Method 1: Character-based with script awareness
    # Latin scripts: ~4 chars/token (GPT-4/cl100k_base average)
    # CJK scripts: ~1.3 chars/token (often 1-2 per character)
    non_cjk_chars = text_len - cjk_chars
    char_estimate = (non_cjk_chars / 4.0) + (cjk_chars / 1.3)
    
    # Method 2: Word-based with subword awareness
    words = text.split()
    word_count = len(words)
    
    # Adjust for contractions (don't → don + ' + t) and possessives
    contraction_extra = sum(1 for w in words if "'" in w and w.lower() not in ["'s", "'t", "'re", "'ve", "'ll", "'d", "'m"])
    
    # Adjust for camelCase (common in code)
    camel_splits = sum(len(re.findall(r'[a-z][A-Z][a-z]', w)) for w in words)
    
    # Base: words * 1.3, plus extras for contractions and camelCase
    word_estimate = (word_count * 1.3) + (contraction_extra * 0.7) + (camel_splits * 0.8)
    
    # Method 3: Improved BPE-like tokenization
    # Pattern: word chars (including apostrophe internals), individual non-word chars, whitespace runs
    tokens = re.findall(r"\w+(?:['\-]\w+)*|[^\w\s]|\s+", text)
    bpe_estimate = len(tokens)
    
    # Subword splitting for very long words (>10 chars)
    for token in tokens:
        tok_len = len(token)
        if tok_len > 10:
            bpe_estimate += (tok_len - 10) // 5  # Conservative: ~5 chars per subword
        
        # Numbers: long digit sequences often split (e.g., "12345" → "12" + "345")
        if token.isdigit():
            if tok_len > 3:
                bpe_estimate += tok_len // 4
    
    # Detect code with better heuristics
    code_score = 0
    code_indicators = [';', '}', '){', '=>', '::', '->', '[]', '++', '--', '&&', '||']
    for indicator in code_indicators:
        code_score += text.count(indicator)
    
    # High symbol-to-word ratio indicates code
    symbol_density = sum(1 for c in text if c in '{}[]();=<>!|&+-*/') / max(text_len, 1)
    is_code = (code_score >= 2) or (symbol_density > 0.15 and word_count > 0)
    
    # Weight selection based on content type
    if is_code:
        # Code: BPE method is most accurate (handles symbols/operators well)
        combined = word_estimate * 0.15 + char_estimate * 0.25 + bpe_estimate * 0.60
    elif has_cjk and (cjk_chars / text_len) > 0.4:
        # CJK-heavy: Character method dominates
        combined = word_estimate * 0.15 + char_estimate * 0.65 + bpe_estimate * 0.20
    else:
        # Natural language (English/Latin)
        combined = word_estimate * 0.35 + char_estimate * 0.40 + bpe_estimate * 0.25
    
    estimate = max(1, round(combined))
    
    # Refinements for edge cases
    
    # Very short text: likely 1-2 tokens per word max
    if text_len <= 15:
        estimate = min(estimate, max(1, len(words) * 2))
    
    # Repetitive characters (e.g., "aaaaaa") often compress to single token
    if len(set(text)) == 1 and text_len > 3:
        estimate = min(estimate, 2)
    
    # Sanity bounds
    estimate = min(estimate, text_len)  # Cannot exceed char count
    estimate = max(1, estimate)
    
    return int(estimate)

def truncate_for_preview(text, max_length=None):
    """Truncate text for preview display"""
    if max_length is None:
        max_length = config.PREVIEW_MAX_LENGTH
    if len(text) > max_length:
        return text[:max_length] + "\n... [truncated for preview] ..."
    return text

