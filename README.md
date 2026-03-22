# whisper2tr

**TR:** Yerel GPU'nuzda çalışan, İngilizce videolar için Türkçe altyazı oluşturan hafif bir araç. Ses tanıma tamamen yerel çalışır, çeviri için Gemini API kullanılır.

**EN:** A lightweight tool that generates Turkish subtitles for English videos using local Whisper speech recognition and the Gemini API for translation.

---

## Nasıl Çalışır / How It Works

```
Video / URL → Whisper (yerel/local) → İngilizce SRT → Gemini API → Türkçe SRT
```

---

## Gereksinimler / Requirements

- NVIDIA GPU (4GB+ VRAM) veya CPU
- [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- [Gemini API key](https://aistudio.google.com) (ücretsiz / free)
- ffmpeg, yt-dlp (kurulum scripti ile otomatik yüklenir / installed automatically)

---

## Kurulum / Installation

### Arch Linux (AUR)

```bash
yay -S whisper2tr
```

```bash
paru -S whisper2tr
```

### Linux

```bash
git clone https://github.com/yeggis/whisper2tr.git
cd whisper2tr
bash install.sh
```

### Windows

```
git clone https://github.com/yeggis/whisper2tr.git
```

`install.bat` dosyasına sağ tık → **Yönetici olarak çalıştır**

---

## Kullanım / Usage

### Linux

```bash
bash launch.sh
```

veya sistem tepsisinden başlatın.

### Windows

Masaüstündeki **whisper2tr** kısayoluna çift tıklayın.

---

## İlk Açılış / First Launch

1. **Ayarlar** sekmesine gidin
2. Gemini API key'inizi girin ([buradan ücretsiz alabilirsiniz](https://aistudio.google.com))
3. Kaydedin — hazır!

---

## Özellikler / Features

| | |
|---|---|
| 🎙️ Ses tanıma | Whisper Large-V3-Turbo (yerel/local) |
| 🇹🇷 Çeviri | Gemini 2.5 Flash Lite |
| 📚 Kütüphane | Video + altyazı çiftlerini kaydet ve yönet |
| ▶️ Oynatıcı | mpv, VLC, Windows Media Player desteği |
| 🖥️ Arayüz | Web tabanlı, sistem tepsisi entegrasyonu |
| ⚙️ Donanım | Otomatik GPU tespiti, ayarlanabilir parametreler |

---

## Donanım Desteği / Hardware Support

| VRAM | Whisper Modeli | Hız |
|------|---------------|-----|
| 10GB+ | large-v3-turbo | En hızlı |
| 7-10GB | large-v3-turbo (INT8) | Hızlı |
| 5-7GB | medium | Orta |
| 3-5GB | small | Yavaş |
| <3GB / CPU | base | Çok yavaş |

---

## Lisans / License

MIT
