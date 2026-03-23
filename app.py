#!/usr/bin/env python3
"""
whisper2tr — İngilizce → Türkçe Altyazı Oluşturucu
Gradio tabanlı · Whisper + Gemini · Cross-platform
"""
import gradio as gr
import sys
import os
import time
import subprocess
import tempfile
import torch
from pathlib import Path

# Uygulama dizinini sys.path'e ekle (nerede çalıştırılırsa çalıştırılsın)
APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

import config
import library

# pipeline.py de aynı dizinde olmalı
try:
    from pipeline import phase2_asr, flush_vram, _parse_srt, _blocks_to_srt, CHUNK_BLOCKS
except ImportError:
    print(f"HATA: pipeline.py bulunamadı. Beklenen konum: {APP_DIR / 'pipeline.py'}")
    sys.exit(1)

# ── Gemini çeviri ─────────────────────────────────────────────────────────────
def _gemini_translate(srt_en: Path, workdir: Path, progress_cb=None) -> Path:
    import google.generativeai as genai

    api_key = config.get("gemini_api_key")
    if not api_key:
        raise ValueError("Gemini API key ayarlanmamış. Ayarlar sekmesinden ekleyin.")

    genai.configure(api_key=api_key)
    model      = genai.GenerativeModel(config.get("gemini_model"))
    chunk_size = config.get("chunk_blocks") or CHUNK_BLOCKS
    en_blocks  = _parse_srt(srt_en.read_text(encoding="utf-8"))
    chunks     = [en_blocks[i:i + chunk_size] for i in range(0, len(en_blocks), chunk_size)]
    tr_all     = []

    for ci, chunk in enumerate(chunks):
        if progress_cb:
            progress_cb(ci, len(chunks))
        prompt = (
            "Translate the following English SRT subtitles to Turkish. "
            "Rules: 1) Never change timestamps. 2) Keep subtitle numbers exactly. "
            "3) Keep app names, software names, proper nouns as-is. "
            "4) Output ONLY the translated SRT content, nothing else.\n\n"
            + _blocks_to_srt(chunk)
        )
        try:
            tr_text  = model.generate_content(prompt).text.strip()
            tr_text  = tr_text.replace("```srt","").replace("```","").strip()
            tr_chunk = _parse_srt(tr_text)
            while len(tr_chunk) < len(chunk):
                tr_chunk.append(chunk[len(tr_chunk)])
            tr_all.extend(tr_chunk)
        except Exception as e:
            print(f"  Chunk {ci+1} hatası: {e}")
            tr_all.extend(chunk)

    srt_tr = workdir / "subtitles_tr.srt"
    srt_tr.write_text(_blocks_to_srt(tr_all), encoding="utf-8")
    return srt_tr

def _sync_timestamps(srt_en: Path, srt_tr: Path, workdir: Path) -> Path:
    en_blocks = _parse_srt(srt_en.read_text(encoding="utf-8"))
    tr_blocks = _parse_srt(srt_tr.read_text(encoding="utf-8"))
    synced    = []
    for i, (en, tr) in enumerate(zip(en_blocks, tr_blocks), 1):
        synced += [str(i), en["ts"], tr["text"], ""]
    out = workdir / "subtitles_tr_final.srt"
    out.write_text("\n".join(synced), encoding="utf-8")
    return out

def _get_video_title(source: str) -> str:
    try:
        if source.startswith("http"):
            r = subprocess.run(
                ["yt-dlp","--get-title","--no-playlist", source],
                capture_output=True, text=True, timeout=15
            )
            return r.stdout.strip() or source
    except Exception:
        pass
    return Path(source).stem if not source.startswith("http") else source

def _seconds_to_dur(s: int) -> str:
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

# ── Ana pipeline ──────────────────────────────────────────────────────────────
def run_pipeline(video_file, url_input, save_to_library,
                 progress=gr.Progress(track_tqdm=True)):
    workdir    = Path(tempfile.mkdtemp(prefix="subsync_"))
    wav        = workdir / "audio.wav"
    start_time = time.time()
    source     = ""

    if url_input and url_input.strip():
        source = url_input.strip()
        progress(0.02, desc="⬇️  Ses indiriliyor...")
        m4a = workdir / "audio.m4a"
        ret = os.system(f'yt-dlp -f 140 "{source}" -o "{m4a}" -q')
        if ret != 0:
            return None, None, "❌ yt-dlp hatası.", _render_library()
        os.system(f'ffmpeg -y -i "{m4a}" -ar 16000 -ac 1 "{wav}" -loglevel error')
    elif video_file is not None:
        source = str(video_file)
        progress(0.05, desc="🎵 Ses ayıklanıyor...")
        os.system(f'ffmpeg -y -i "{video_file}" -ar 16000 -ac 1 "{wav}" -loglevel error')
    else:
        return None, None, "❌ Dosya veya URL giriniz.", _render_library()

    if not wav.exists():
        return None, None, "❌ Ses dönüştürme başarısız.", _render_library()

    try:
        progress(0.10, desc="🎙️  Whisper — konuşma tanıma...")
        srt_en     = phase2_asr(wav, workdir)
        en_blocks  = _parse_srt(srt_en.read_text(encoding="utf-8"))
        n_blocks   = len(en_blocks)
        chunk_size = config.get("chunk_blocks") or CHUNK_BLOCKS
        n_chunks   = max(1, -(-n_blocks // chunk_size))
        progress(0.30, desc=f"🎙️  ASR tamamlandı — {n_blocks} blok, {n_chunks} chunk")
        flush_vram()

        chunk_times = []
        def progress_cb(ci, total_c):
            pct = 0.35 + (ci / total_c) * 0.55
            eta = ""
            if chunk_times:
                avg = sum(chunk_times) / len(chunk_times)
                eta = f" · ~{int(avg*(total_c-ci))}s kaldı"
            progress(pct, desc=f"🇹🇷  Chunk {ci+1}/{total_c} çevriliyor{eta}")
            chunk_times.append(time.time())

        srt_tr    = _gemini_translate(srt_en, workdir, progress_cb)
        srt_final = _sync_timestamps(srt_en, srt_tr, workdir)

        progress(1.0, desc="✅ Tamamlandı!")
        elapsed = int(time.time() - start_time)
        summary = f"✅ {elapsed}s · {n_blocks} blok · {n_chunks} chunk"

        if save_to_library:
            title = _get_video_title(source)
            library.add(title, source, str(srt_en), str(srt_final),
                        _seconds_to_dur(elapsed), n_blocks)

        return str(srt_en), str(srt_final), summary, _render_library()

    except Exception as e:
        return None, None, f"❌ Hata: {str(e)}", _render_library()

# ── Kütüphane ─────────────────────────────────────────────────────────────────
def _render_library() -> str:
    entries = library.all_entries()
    if not entries:
        return ("<p style='color:var(--color-text-tertiary);font-size:13px;"
                "padding:12px 0;'>Henüz kayıt yok.</p>")
    rows = ""
    for e in entries:
        tid   = e["id"]
        title = e.get("title","—")[:70]
        meta  = (f"{e.get('duration','?')} · {e.get('blocks','?')} blok · "
                 f"{e.get('created_at','')[:10]}")
        rows += f"""
        <div style='display:flex;align-items:center;gap:12px;padding:10px 0;
                    border-bottom:0.5px solid var(--color-border-tertiary);'>
          <div style='flex:1;min-width:0;'>
            <div style='font-size:13px;font-weight:500;color:var(--color-text-primary);
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{title}</div>
            <div style='font-size:11px;color:var(--color-text-tertiary);margin-top:2px;'>{meta}</div>
          </div>
          <div style='display:flex;gap:6px;flex-shrink:0;'>
            <button onclick="navigator.clipboard.writeText('{tid}')"
              style='font-size:11px;padding:5px 10px;border-radius:8px;
                     border:0.5px solid var(--color-border-secondary);
                     background:transparent;color:var(--color-text-secondary);cursor:pointer;'>
              ID kopyala
            </button>
          </div>
        </div>"""
    return rows

def play_entry(entry_id: str) -> str:
    return library.open_with_player(entry_id.strip())

def delete_entry(entry_id: str):
    library.delete(entry_id.strip())
    return _render_library(), "🗑️ Silindi."

# ── Ayarlar ───────────────────────────────────────────────────────────────────
def save_settings(api_key, gemini_model, player, library_dir,
                  chunk_blocks, whisper_model, compute_type, n_gpu_layers):
    cfg = config.load()
    cfg["gemini_api_key"] = api_key.strip()
    cfg["gemini_model"]   = gemini_model
    cfg["player"]         = player
    cfg["library_dir"]    = library_dir.strip()
    cfg["chunk_blocks"]   = int(chunk_blocks)
    cfg["whisper_model"]  = whisper_model
    cfg["compute_type"]   = compute_type
    cfg["n_gpu_layers"]   = int(n_gpu_layers)
    config.save(cfg)
    return "✅ Ayarlar kaydedildi."

def test_api_key(api_key):
    if not api_key.strip():
        return "❌ API key boş."
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key.strip())
        genai.GenerativeModel(config.get("gemini_model")).generate_content("Say OK")
        return "✅ API key geçerli."
    except Exception as e:
        return f"❌ {str(e)[:120]}"

def reset_hardware():
    hw = config.detect_hardware()
    return (
        hw["whisper_model"],
        hw["compute_type"],
        hw["n_gpu_layers"],
        f"✅ Yeniden tespit: {config.hardware_summary()}",
    )

# ── Arayüz ────────────────────────────────────────────────────────────────────
cfg = config.load()

with gr.Blocks(title="whisper2tr") as demo:

    gr.HTML(f"""
    <div style='display:flex;align-items:baseline;justify-content:space-between;
                padding:20px 0 4px;'>
      <div style='display:flex;align-items:baseline;gap:10px;'>
        <span style='font-size:18px;font-weight:500;color:var(--color-text-primary);'>whisper2tr</span>
        <span style='font-size:12px;color:var(--color-text-tertiary);'>İngilizce → Türkçe altyazı</span>
      </div>
      <span style='font-size:11px;color:var(--color-text-tertiary);'>{config.hardware_summary()}</span>
    </div>
    """)

    with gr.Tabs():

        # ── Çeviri ────────────────────────────────────────────────────────────
        with gr.Tab("Çeviri"):
            with gr.Row():
                with gr.Column(scale=1):
                    url_input   = gr.Textbox(label="YouTube / Web URL",
                                             placeholder="https://www.youtube.com/watch?v=...")
                    video_input = gr.File(label="veya Video Dosyası",
                                          file_types=["video",".mkv",".mp4",".avi",".webm",".mov"])
                    save_cb     = gr.Checkbox(label="Kütüphaneye kaydet", value=True)
                    run_btn     = gr.Button("▶  Altyazı Oluştur", variant="primary", size="lg")
                with gr.Column(scale=1):
                    status_box  = gr.Textbox(label="Durum", interactive=False, lines=2)
                    with gr.Row():
                        srt_en_out = gr.File(label="⬇ İngilizce SRT", interactive=False)
                        srt_tr_out = gr.File(label="⬇ Türkçe SRT",    interactive=False)

            lib_refresh = gr.HTML(visible=False)
            run_btn.click(
                fn=run_pipeline,
                inputs=[video_input, url_input, save_cb],
                outputs=[srt_en_out, srt_tr_out, status_box, lib_refresh],
            )

        # ── Kütüphane ─────────────────────────────────────────────────────────
        with gr.Tab("Kütüphane"):
            lib_html    = gr.HTML(value=_render_library())
            lib_status  = gr.Textbox(label="", interactive=False, lines=1)
            entry_id_in = gr.Textbox(label="Giriş ID",
                                     placeholder="Yukarıdaki 'ID kopyala' butonundan al")
            with gr.Row():
                play_btn    = gr.Button("▶ Oynat",   variant="secondary")
                delete_btn  = gr.Button("🗑 Sil",    variant="secondary")
                refresh_btn = gr.Button("↻ Yenile")

            play_btn.click(fn=play_entry,    inputs=[entry_id_in], outputs=[lib_status])
            delete_btn.click(fn=delete_entry,inputs=[entry_id_in], outputs=[lib_html, lib_status])
            refresh_btn.click(fn=lambda: (_render_library(),""), outputs=[lib_html, lib_status])

        # ── Ayarlar ───────────────────────────────────────────────────────────
        with gr.Tab("Ayarlar"):

            gr.HTML(f"""
            <div style='background:var(--color-background-secondary);
                        border:0.5px solid var(--color-border-tertiary);
                        border-radius:var(--border-radius-md);
                        padding:10px 14px;margin-bottom:8px;'>
              <div style='font-size:11px;color:var(--color-text-tertiary);
                          text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px;'>
                Tespit edilen donanım
              </div>
              <div style='font-size:13px;font-weight:500;color:var(--color-text-primary);'>
                {config.hardware_summary()}
              </div>
            </div>
            """)

            with gr.Group():
                gr.Markdown("### API")
                s_api_key = gr.Textbox(label="Gemini API key",
                                       value=cfg.get("gemini_api_key",""),
                                       type="password", placeholder="AIzaSy...")
                s_gemini_model = gr.Dropdown(
                    label="Model", value=cfg.get("gemini_model"),
                    choices=["gemini-2.5-flash-lite","gemini-2.5-flash"]
                )
                with gr.Row():
                    test_btn = gr.Button("API key'i test et", variant="secondary")
                    test_out = gr.Textbox(label="", interactive=False, lines=1)
                test_btn.click(fn=test_api_key, inputs=[s_api_key], outputs=[test_out])

            with gr.Group():
                gr.Markdown("### Oynatıcı ve depolama")
                s_player  = gr.Dropdown(
                    label="Varsayılan oynatıcı",
                    value=cfg.get("player", "mpv"),
                    choices=["mpv","vlc","wmplayer","Sistem varsayılanı"]
                )
                s_lib_dir = gr.Textbox(label="Kütüphane dizini",
                                       value=cfg.get("library_dir",""))
                s_chunks  = gr.Slider(label="Chunk boyutu", minimum=30, maximum=300,
                                      step=10, value=cfg.get("chunk_blocks",150))

            with gr.Accordion("Gelişmiş — Whisper ve GPU", open=False):
                gr.HTML("<p style='font-size:12px;color:var(--color-text-tertiary);margin-bottom:8px;'>"
                        "Bu değerler donanımınıza göre otomatik ayarlanmıştır. "
                        "Değiştirmeniz gerekmeyebilir.</p>")
                s_whisper = gr.Dropdown(
                    label="Whisper modeli",
                    value=cfg.get("whisper_model","large-v3-turbo"),
                    choices=["tiny","base","small","medium","large-v3","large-v3-turbo"]
                )
                s_compute = gr.Dropdown(
                    label="Compute type",
                    value=cfg.get("compute_type","int8"),
                    choices=["int8","float16","int4","float32"]
                )
                s_gpu_layers = gr.Slider(
                    label="GPU katman sayısı  (-1 = tam GPU · 0 = CPU)",
                    minimum=-1, maximum=100, step=1,
                    value=cfg.get("n_gpu_layers",-1)
                )
                with gr.Row():
                    reset_hw_btn = gr.Button("↻ Otomatik değerlere dön", variant="secondary")
                    reset_out    = gr.Textbox(label="", interactive=False, lines=1)
                reset_hw_btn.click(
                    fn=reset_hardware,
                    outputs=[s_whisper, s_compute, s_gpu_layers, reset_out]
                )

            save_btn     = gr.Button("Kaydet", variant="primary")
            settings_out = gr.Textbox(label="", interactive=False, lines=1)
            save_btn.click(
                fn=save_settings,
                inputs=[s_api_key, s_gemini_model, s_player, s_lib_dir,
                        s_chunks, s_whisper, s_compute, s_gpu_layers],
                outputs=[settings_out],
            )

if __name__ == "__main__":
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    print(f"GPU   : {gpu}")
    print(f"Dizin : {APP_DIR}")
    print(f"Arayüz: http://localhost:7860")
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        theme=gr.themes.Soft(),
        show_error=True,
    )
