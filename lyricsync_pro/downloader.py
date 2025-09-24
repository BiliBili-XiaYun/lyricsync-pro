from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import requests
from mutagen import File as MutagenFile

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"


def _format_mmss_cc(seconds: float | int) -> str:
    s = int(seconds)
    ms = int(round((seconds - s) * 1000)) if isinstance(seconds, float) else 0
    mm = s // 60
    ss = s % 60
    cc = (ms // 10) if ms else 0
    return f"{mm:02d}:{ss:02d}.{cc:02d}"


class LyricDownloader:
    """Lyric downloader for Netease with ID3/metadata extraction and duration-aware matching."""

    def __init__(self, session: Optional[requests.Session] = None):
        self.sess = session or requests.Session()
        self.sess.headers.update({"User-Agent": USER_AGENT, "Referer": "https://music.163.com/"})

    # --------------------------- Metadata & Title ---------------------------
    def extract_metadata(self, audio_path: Path) -> tuple[str, str, Optional[float], bool]:
        """Return (title, artist, duration_sec, used_fuzzy_title).
        - Prefer ID3/metadata via mutagen.
        - If missing title, fallback to fuzzy title from filename and mark fuzzy=True.
        """
        title = ""
        artist = ""
        duration = None
        fuzzy = False
        try:
            mf = MutagenFile(str(audio_path))
            if mf is not None:
                # duration
                if hasattr(mf, "info") and getattr(mf.info, "length", None):
                    duration = float(mf.info.length)
                # tags (best-effort across formats)
                tags = getattr(mf, "tags", None) or {}
                # Common keys
                cand_title_keys = [
                    "TIT2",  # ID3 Title
                    "title", "TITLE", ("\xa9nam"),  # MP4/M4A
                ]
                cand_artist_keys = [
                    "TPE1",  # ID3 Lead performer
                    "artist", "ARTIST", ("\xa9ART"),
                ]
                def _get_first(tagdict, keys):
                    for k in keys:
                        if isinstance(k, tuple):  # e.g. ('\xa9nam',)
                            k = k[0]
                        if k in tagdict:
                            v = tagdict[k]
                            if isinstance(v, (list, tuple)):
                                return str(v[0])
                            return str(v)
                    return ""
                title = _get_first(tags, cand_title_keys) or ""
                artist = _get_first(tags, cand_artist_keys) or ""
        except Exception:
            pass

        if not title:
            title = self._fuzzy_title_from_filename(audio_path.stem)
            fuzzy = True
        return title.strip(), artist.strip(), duration, fuzzy

    @staticmethod
    def _fuzzy_title_from_filename(stem: str) -> str:
        # Remove track numbers (e.g., 01 -, 1. )
        s = re.sub(r"^\s*\d+\s*[-_. ]\s*", "", stem)
        # Remove brackets contents
        s = re.sub(r"[\[\(\{（【].*?[\]\)\}）】]", "", s)
        # Split on common separators and pick the longest token as title
        parts = re.split(r"\s*[-–—_|]\s*", s)
        parts = [p for p in parts if p]
        if not parts:
            return stem
        parts.sort(key=len, reverse=True)
        return parts[0].strip()

    # --------------------------- Netease Search ---------------------------
    def search_songs(self, keywords: str, limit: int = 20) -> List[Dict]:
        """Return list of songs: {id, name, artists, duration_ms}.
        Uses older public endpoint; fields may vary, so code is defensive.
        """
        url = "https://music.163.com/api/search/get/"
        params = {"s": keywords, "type": 1, "limit": max(1, min(limit, 50))}
        try:
            r = self.sess.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json() or {}
            songs = (data.get("result", {}) or {}).get("songs", []) or []
            results: List[Dict] = []
            for s in songs:
                sid = s.get("id")
                name = s.get("name") or ""
                arts = ", ".join(a.get("name", "") for a in (s.get("artists") or []))
                # duration may be in 'duration' (ms)
                dur = s.get("duration") if isinstance(s.get("duration"), int) else None
                results.append({"id": sid, "name": name, "artists": arts, "duration_ms": dur})
            return results
        except Exception:
            return []

    def get_lyric_by_id(self, song_id: int) -> Optional[str]:
        url = "https://music.163.com/api/song/lyric"
        params = {"id": song_id, "lv": 1, "kv": 1, "tv": -1}
        try:
            r = self.sess.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json() or {}
            return (data.get("lrc", {}) or {}).get("lyric")
        except Exception:
            return None

    # --------------------------- High-level APIs ---------------------------
    def auto_pick_song(self, keyword: str, local_duration_sec: Optional[float]) -> Optional[Dict]:
        """Search songs and pick the one closest to local duration if available."""
        results = self.search_songs(keyword, limit=20)
        if not results:
            return None
        if local_duration_sec is None:
            return results[0]
        target_ms = int(local_duration_sec * 1000)
        results.sort(key=lambda x: abs((x.get("duration_ms") or 0) - target_ms))
        return results[0]

    def download_lrc(self, title_only: str, local_duration_sec: Optional[float]) -> tuple[Optional[str], Optional[Dict]]:
        """Download LRC by title-only search, duration-aware.
        Returns (lrc_text, chosen_song_dict).
        """
        chosen = self.auto_pick_song(title_only, local_duration_sec)
        if not chosen:
            return None, None
        lrc = self.get_lyric_by_id(chosen["id"]) if chosen.get("id") else None
        return lrc, chosen

    @staticmethod
    def build_lrc_header(title: str, artist: str, length_sec: Optional[float], match_tag: str) -> str:
        parts = []
        if title:
            parts.append(f"[ti:{title}]")
        if artist:
            parts.append(f"[ar:{artist}]")
        if length_sec is not None:
            parts.append(f"[length:{_format_mmss_cc(length_sec)}]")
        parts.append("[by:LyricSync Pro]")
        parts.append(f"[match:{match_tag}]")
        return "\n".join(parts)
