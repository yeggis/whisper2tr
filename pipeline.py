#!/usr/bin/env python3
"""
whisper2tr — pipeline.py
Ses tanıma ve çeviri pipeline'ı
API key config.py üzerinden yönetilir, buraya yazılmaz.
"""
import gc
import os
import re
import sys
import subprocess
import torch
from pathlib import Path

# Uygulama dizini
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

import config

# ── Yapılandırma ──────────────────────────────────────────────────────────────
WHISPER_MODEL_DIR = str(APP_DIR / "models" / "whisper")
GGUF_MODEL_PATH   = str(APP_DIR / "models" / "trendyol-gguf" / "Trendyol-LLM-8B-T1.Q4_K_M.gguf")
CHUNK_BLOCKS      = 150

SYSTEM_PROMPT = (
    "You are a subtitle translator. "
    "Translate the following English SRT subtitles to Turkish. "
    "Rules: "
    "1) Never change timestamps like 00:01:23,450 --> 00:01:25,100. "
    "2) Keep subtitle numbers exactly. "
    "3) Keep app names, software names, and proper nouns as-is. "
    "4) Output ONLY the translated SRT content, nothing else."
)

# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────
def flush_vram():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    print("[VRAM] Cache cleared ✓")

def run(cmd: list[str], **kwargs):
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.run(cmd, check=True, **kwargs)

def _fmt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h,  ms = divmod(ms, 3_600_000)
    m,  ms = divmod(ms, 60_000)
    s,  ms = divmod(ms, 1_000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def _parse_srt(content: str) -> list[dict]:
    blocks = []
    for block in content.strip().split("\n\n"):
        lines = block.strip().splitlines()
        if len(lines) >= 3:
            blocks.append({"num": lines[0], "ts": lines[1], "text": "\n".join(lines[2:])})
    return blocks

def _blocks_to_srt(blocks: list[dict]) -> str:
    lines = []
    for b in blocks:
        lines += [b["num"], b["ts"], b["text"], ""]
    return "\n".join(lines)

# ── Phase 1: Ses ayıklama ─────────────────────────────────────────────────────
def phase1_audio(url: str, workdir: Path) -> Path:
    print("\n=== Phase 1: Audio Extraction ===")
    m4a = workdir / "audio.m4a"
    wav = workdir / "audio.wav"
    run(["yt-dlp", "-f", "140", url, "-o", str(m4a)])
    run(["ffmpeg", "-y", "-i", str(m4a), "-ar", "16000", "-ac", "1", str(wav)])
    print(f"[Phase 1] WAV ready: {wav}")
    return wav

# ── Phase 2: ASR ─────────────────────────────────────────────────────────────
def phase2_asr(wav: Path, workdir: Path) -> Path:
    print("\n=== Phase 2: ASR (Whisper) ===")
    from faster_whisper import WhisperModel

    whisper_model  = config.get("whisper_model") or "large-v3-turbo"
    whisper_device = config.get("whisper_device") or "cuda"
    compute_type   = config.get("compute_type") or "int8"

    model = WhisperModel(
        whisper_model,
        device=whisper_device,
        compute_type=compute_type,
        download_root=WHISPER_MODEL_DIR,
    )
    segments, info = model.transcribe(
        str(wav),
        language="en",
        beam_size=5,
        vad_filter=True,
    )
    print(f"[Phase 2] Language: {info.language} ({info.language_probability:.0%})")

    srt_en = workdir / "subtitles_en.srt"
    with open(srt_en, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}\n{seg.text.strip()}\n\n")

    del model
    block_count = len(_parse_srt(srt_en.read_text()))
    print(f"[Phase 2] SRT written: {srt_en} ({block_count} blok)")
    return srt_en

# ── Phase 4: Çeviri (Gemini) ──────────────────────────────────────────────────
def phase4_translate(srt_en: Path, workdir: Path) -> Path:
    print("\n=== Phase 4: Translation (Gemini) ===")
    import google.generativeai as genai

    api_key = config.get("gemini_api_key")
    if not api_key:
        raise ValueError("Gemini API key ayarlanmamış. Ayarlar sekmesinden ekleyin.")

    genai.configure(api_key=api_key)
    model_name = config.get("gemini_model") or "gemini-2.5-flash-lite"
    model      = genai.GenerativeModel(model_name)

    chunk_size = config.get("chunk_blocks") or CHUNK_BLOCKS
    en_blocks  = _parse_srt(srt_en.read_text(encoding="utf-8"))
    total      = len(en_blocks)
    chunks     = [en_blocks[i:i + chunk_size] for i in range(0, total, chunk_size)]
    tr_all     = []

    print(f"[Phase 4] {total} blok, {len(chunks)} chunk...")

    for ci, chunk in enumerate(chunks, 1):
        print(f"[Phase 4] Chunk {ci}/{len(chunks)}...")
        prompt = (
            "Translate the following English SRT subtitles to Turkish. "
            "Rules: 1) Never change timestamps. 2) Keep subtitle numbers exactly. "
            "3) Keep app names, software names, proper nouns as-is. "
            "4) Output ONLY the translated SRT content, nothing else.\n\n"
            + _blocks_to_srt(chunk)
        )
        try:
            tr_text  = model.generate_content(prompt).text.strip()
            tr_text  = tr_text.replace("```srt", "").replace("```", "").strip()
            tr_chunk = _parse_srt(tr_text)
            while len(tr_chunk) < len(chunk):
                tr_chunk.append(chunk[len(tr_chunk)])
            tr_all.extend(tr_chunk)
        except Exception as e:
            print(f"  Chunk {ci} hatası: {e}")
            tr_all.extend(chunk)

    srt_tr = workdir / "subtitles_tr.srt"
    srt_tr.write_text(_blocks_to_srt(tr_all), encoding="utf-8")
    print(f"[Phase 4] Turkish SRT: {srt_tr}")
    return srt_tr

# ── Phase 5: Timestamp sync ───────────────────────────────────────────────────
def phase5_validate(srt_en: Path, srt_tr: Path, workdir: Path) -> Path:
    print("\n=== Phase 5: Timestamp Sync ===")
    en_blocks = _parse_srt(srt_en.read_text(encoding="utf-8"))
    tr_blocks = _parse_srt(srt_tr.read_text(encoding="utf-8"))
    synced    = []
    for i, (en, tr) in enumerate(zip(en_blocks, tr_blocks), 1):
        synced += [str(i), en["ts"], tr["text"], ""]
    out = workdir / "subtitles_tr_final.srt"
    out.write_text("\n".join(synced), encoding="utf-8")
    print(f"[Phase 5] Final SRT: {out} ({len(en_blocks)} blok)")
    return out

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Kullanım: python pipeline.py <YouTube-URL> [çıktı_dizini]")
        sys.exit(1)

    url      = sys.argv[1]
    out_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd() / "pipeline_output"
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"\nÇıktı dizini: {out_root}")
    print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

    wav          = phase1_audio(url, out_root)
    srt_en       = phase2_asr(wav, out_root)
    flush_vram()
    srt_tr       = phase4_translate(srt_en, out_root)
    flush_vram()
    srt_tr_final = phase5_validate(srt_en, srt_tr, out_root)

    print(f"\n✅ Tamamlandı.")
    print(f"   İngilizce SRT : {srt_en}")
    print(f"   Türkçe SRT    : {srt_tr_final}")

if __name__ == "__main__":
    main()
