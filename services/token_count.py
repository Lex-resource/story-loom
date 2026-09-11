import logging

try:
    import transformers
except ImportError:
    transformers = None
from pathlib import Path
from config import settings

logger = logging.getLogger(__name__)

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
        transformers.utils.logging.set_verbosity_error()

        _tokenizer = transformers.AutoTokenizer.from_pretrained(
            str(TOKENIZER_DIR),
            trust_remote_code=True,
            local_files_only=True
        )
    return _tokenizer


def preload_tokenizer() -> bool:
    """启动时预热 tokenizer。

    首次 ``AutoTokenizer.from_pretrained`` 是数秒级磁盘加载，放在首次 LLM
    调用的热路径上会造成明显停顿；worker / API 启动时调用本函数把加载提前。
    加载失败不致命——count_tokens 有字符数兜底。调用方应放在线程里跑
    （asyncio.to_thread），加载本身是同步阻塞的。
    """
    try:
        get_tokenizer()
        return True
    except Exception as exc:
        logger.warning("tokenizer_preload_failed fallback=char_estimate error=%s", exc)
        return False


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
            logger.warning("tokenizer_encode_failed fallback=char_estimate error=%s", e)
            _warned_tokenizer_error = True
        # Fallback estimation if encoding fails: 1 token ≈ 1.5 characters
        return max(1, int(len(text) / 1.5))
