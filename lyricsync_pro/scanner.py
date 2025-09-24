from pathlib import Path
from typing import Iterable

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg"}

def find_audio_files(root: Path) -> Iterable[str]:
    if not root.exists():
        return []
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            yield str(p)
