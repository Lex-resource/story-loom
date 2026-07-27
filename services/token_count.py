import os
try:
    import transformers
except ImportError:
    transformers = None
from pathlib import Path
from config import settings

# Path to the offline DeepSeek V3 tokenizer directory
TOKENIZER_DIR = Path(settings.TOKENIZER_DIR)

# Lazy-loaded tokenizer instance
_tokenizer = None

# Emit the tokenizer-unavailable warning only once, not on every count.
_warned_tokenizer_error = False

def get_tokenizer():
    global _tokenizer
    if transformers is None:
        raise ImportError("The 'transformers' library is not installed.")
    if _tokenizer is None:
        # Avoid showing non-critical PyTorch warning messages on console
        import logging
        transformers.utils.logging.set_verbosity_error()
        
        _tokenizer = transformers.AutoTokenizer.from_pretrained(
            str(TOKENIZER_DIR),
            trust_remote_code=True,
            local_files_only=True
        )
    return _tokenizer


def count_tokens(text: str) -> int:
    """
    Offline calculation of DeepSeek V3 token count for a given text.
    """
    if not text:
        return 0
    try:
        tok = get_tokenizer()
        return len(tok.encode(text))
    except Exception as e:
        global _warned_tokenizer_error
        if not _warned_tokenizer_error:
            print(f"[Tokenizer WARNING] Falling back to char-based estimate: {e}")
            _warned_tokenizer_error = True
        # Fallback estimation if encoding fails: 1 token ≈ 1.5 characters
        return max(1, int(len(text) / 1.5))
