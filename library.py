"""
library.py — SubSync kütüphane yönetimi
Dinamik path'ler, cross-platform
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import config

LIBRARY_FILE = Path.home() / ".config" / "subsync" / "library.json"

def _load() -> list:
    if LIBRARY_FILE.exists():
        try:
            return json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save(entries: list) -> None:
    LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_FILE.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )

def add(title: str, source: str, srt_en: str, srt_tr: str,
        duration_str: str, block_count: int) -> dict:
    lib_dir = Path(config.get("library_dir"))
    lib_dir.mkdir(parents=True, exist_ok=True)

    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:60].strip()
    ts         = datetime.now().strftime("%Y%m%d_%H%M%S")
    base       = lib_dir / f"{ts}_{safe_title}"

    srt_en_dst = str(base) + ".en.srt"
    srt_tr_dst = str(base) + ".tr.srt"

    for src, dst in [(srt_en, srt_en_dst), (srt_tr, srt_tr_dst)]:
        if Path(src).exists():
            shutil.copy2(src, dst)

    entry = {
        "id":         ts,
        "title":      title,
        "source":     source,
        "srt_en":     srt_en_dst,
        "srt_tr":     srt_tr_dst,
        "duration":   duration_str,
        "blocks":     block_count,
        "created_at": datetime.now().isoformat(),
    }
    entries = _load()
    entries.insert(0, entry)
    _save(entries)
    return entry

def all_entries() -> list:
    return _load()

def delete(entry_id: str) -> None:
    entries = _load()
    to_del  = next((e for e in entries if e["id"] == entry_id), None)
    if to_del:
        for key in ("srt_en", "srt_tr"):
            p = Path(to_del.get(key, ""))
            if p.exists():
                p.unlink(missing_ok=True)
    _save([e for e in entries if e["id"] != entry_id])

def open_with_player(entry_id: str) -> str:
    import subprocess
    entries = _load()
    entry   = next((e for e in entries if e["id"] == entry_id), None)
    if not entry:
        return "❌ Giriş bulunamadı."

    source = entry.get("source", "")
    srt_tr = entry.get("srt_tr", "")
    player = config.get("player")

    if not Path(srt_tr).exists():
        return f"❌ SRT bulunamadı: {srt_tr}"

    try:
        if player == "mpv":
            subprocess.Popen(["mpv", source, f"--sub-file={srt_tr}", "--sub-visibility=yes"])
        elif player == "vlc":
            subprocess.Popen(["vlc", source, f"--sub-file={srt_tr}"])
        elif player in ("wmplayer", "windows media player"):
            # WMP doğrudan sub-file desteklemiyor, SRT'yi yanına koy
            import shutil as sh
            src_path = Path(source)
            srt_dest = src_path.parent / (src_path.stem + ".srt")
            sh.copy2(srt_tr, str(srt_dest))
            subprocess.Popen(["wmplayer", source])
        else:
            # Sistem varsayılanı
            if sys.platform == "win32":
                import os
                os.startfile(source)
            else:
                subprocess.Popen(["xdg-open", source])
        return f"▶ {player} açıldı"
    except FileNotFoundError:
        return f"❌ {player} bulunamadı."
    except Exception as e:
        return f"❌ Hata: {e}"
