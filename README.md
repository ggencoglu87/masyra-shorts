# Masyra Viral Shorts Engine v3

Masyra Labs artik generic trend-news videolari ureten bir sistem degil; YouTube Shorts, TikTok ve Instagram Reels icin eglence odakli viral Shorts studio iskeletidir.

Ana hedef: watch time, completion rate, share, repeat view. Her karar su soruya gore degerlendirilir: "Birisi scroll'u durdurup bunu izler mi?"

## V3 Entertainment Categories

- Funny Animals
- Funny Kids
- Funny Fails
- Horror Stories
- Reddit Stories
- Sports Drama
- Relationship Stories
- Minecraft Stories
- Motivational Stories
- Celebrity Drama
- Survival Stories
- Crazy Facts

Her kategori kendi story style, voice profile, channel target ve scene search query seti ile uretilir. Eski "This trend is moving fast..." sablonu kaldirildi.

## V3 Viral Structure

Her video 20-30 saniyelik viral story beat yapisini takip eder:

- `Hook (0-3s)`: curiosity trigger
- `Curiosity (3-10s)`: conflict setup
- `Escalation (10-20s)`: tension increase
- `Twist (20-26s)`: unexpected turn
- `Payoff (26-30s)`: reveal, laugh, scare, emotion, or comment trigger

Her paket artik ek olarak sunlari uretir:

- `storyboard.json`: scene, beat, time, caption, visual prompt, stock search queries
- `captions.json`: TikTok-style word-by-word caption timing
- `voice_profile` metadata: energetic, suspenseful, commentator, inspiring, etc.
- `channel_target`: animals, kids, horror, sports, reddit, minecraft
- `learning.db`: views, likes, shares, comments ve completion history icin SQLite database

`daily-run` v3'te full pipeline calistirmaya ayarlidir: trend/story/storyboard/clips/visuals/voice/captions/render/score. Plan-only calismak icin `--no-render` kullan.

## Kaynaklar

- YouTube Trends: `videos.list chart=mostPopular`
- YouTube Search: populer arama sorgulari icin `search.list` ve video detaylari
- Google Trends: gunluk RSS trendleri
- Reddit: `r/popular` basliklari ve upvote sinyali

YouTube kaynaklari icin `YOUTUBE_API_KEY` gerekir. Google Trends RSS ve Reddit herkese acik endpoint kullanir, fakat ag politikasi veya servis tarafli kisitlar nedeniyle bazen bos donebilir.

## Kategori Secimi

Kategori secimi artik YouTube kategori ID'sine bagli degildir. Sistem baslik, kaynak ve anahtar kelime sinyallerinden v3 entertainment kategorisini tahmin eder. Eski AI/news/generic trend kategorileri, story-first kategorilere normalize edilir.

## Skor Algoritmasi

Her trend icin v3 viral skor seti uretilir:

- `trend_score`: gorunurluk gucu. YouTube goruntulenme/begeni, Reddit upvote, Google Trends trafik ve kaynak sayisini birlestirir.
- `growth_score`: buyume hizi. Yayin yasina gore YouTube view velocity, Google Trends trafik artisi, Reddit upvote ve cok kaynak sinyalini kullanir.
- `competition_score`: rekabet puani. Benzer YouTube arama yogunlugu, kaynak sayisi ve uzun/genis baslik sinyalinden hesaplanir. Yuksek rekabet daha zor firsat demektir.
- `hook_score`: ilk 3 saniyede scroll durdurma gucu.
- `curiosity_score`: 3-10 saniye arasi conflict/merak gucu.
- `payoff_score`: twist veya emotional payoff gucu.
- `shareability_score`: yorum, paylasim ve remix potansiyeli.
- `completion_probability`: videonun sonuna kadar izlenme olasiligi.
- `rewatch_probability`: tekrar izlenme olasiligi.
- `viral_score`: ranking icin ana entertainment skoru.
- `publish_ready`: skor ve asset kosullarindan gecen paketler icin gate.

## Icerik Uretim Kurallari

- Trend videolari kopyalanmaz.
- Telifli goruntu kullanilmaz.
- Sadece trend temasindan, kamuya acik bilgilerden ve ozgun yorumdan ilham alinir.
- Gorseller icin generated visuals, lisansli stok, public-domain materyal, ozgun grafik veya basit reenactment kullanilir.

## Video Uretim Akisi

```text
trend -> script -> voiceover -> subtitles -> vertical short video -> upload package
```

Mevcut surum her trend icin su dosyalari hazirlar:

- `script.txt`
- `voiceover.txt`
- `subtitles.srt`
- `render-brief.txt`
- `video-plan.json`
- `upload-metadata.json`

Sistem her paket icin `asset-prompts.json` uretir. Render istenirse once bu promptlardan 4-8 adet sahne gorseli uretilir:

Stock video pipeline birinci onceliktir. `VIDEO_PROVIDER=auto`, `PEXELS_API_KEY` varsa Pexels Videos, yoksa `PIXABAY_API_KEY` varsa Pixabay Videos kullanir. Bulunan klipler `video-clips/` altina indirilir ve `video-clips-manifest.json` icine kaynak, query, provider ve attribution metadata yazilir. Pexels API `Authorization` header ister; Pixabay video arama API'si `key` query parametresi kullanir.

- `VISUAL_PROVIDER=openai`: `OPENAI_API_KEY` ile OpenAI Images kullanir ve publish-ready sahne gorselleri uretir.
- `VISUAL_PROVIDER=auto`: OpenAI key varsa OpenAI Images, yoksa local placeholder fallback kullanir.
- `VISUAL_PROVIDER=placeholder`: API olmadan yerel sahne PNG'leri uretir. Bu gorseller sadece test icindir; dashboard "Placeholder visuals only — not ready for publishing." uyarisi gosterir.

FFmpeg varsa sistem sahne gorsellerinden Ken Burns zoom/pan hareketli temiz dikey Shorts videolari uretir. Varsayilan final video suresi 25 saniyedir. Her sahne 2-4 saniye gosterilir, altyazilar yalnizca altta yer alir, sahne gorsellerinin ustune baslik/metin bloklari basilmaz. `--render` artik otomatik olarak 12 saniyelik `preview.mp4` ve `thumbnail.jpg` da uretir. `--preview-only` yalnizca hizli preview ve thumbnail uretir. FFmpeg yoksa script, voiceover, altyazi, metadata ve sahne gorselleri uretimi devam eder; summary icinde net uyari doner.

ElevenLabs opsiyonel TTS provider'dir. `TTS_PROVIDER=elevenlabs` ve `ELEVENLABS_API_KEY` varsa `voiceover.mp3` uretilir ve FFmpeg render bunu final/preview videoya gomar. API key yoksa ElevenLabs cagrisi yapilmaz; sistem `voiceover.txt` ile devam eder ve `tts-result.json` icinde net uyari yazar.

Ubuntu icin ucretsiz offline fallback olarak Piper desteklenir. `TTS_PROVIDER=piper`, `PIPER_BIN` ve `PIPER_MODEL_PATH` ayarlandiginda sistem API key olmadan lokal `voiceover.mp3` uretir.

Her TTS denemesi paket icinde `tts-result.json` dosyasina yazilir. `voiceover.mp3` zaten varsa sistem varsayilan olarak yeniden uretmez; yeniden uretmek icin `--force` veya render sirasinda `--force-tts` gerekir.

Dashboard ile her gunluk trend/video paketini thumbnail, preview/final video, sahne timeline'i, script ve checklist ile inceleyebilir, `Needs Edit`, `Approved`, `Rejected` statuslerinden birini verebilirsin. Detay sayfasinda `Generate Visuals` promptlardan sahne gorselleri uretir, `Re-render Video` mevcut sahnelerle preview/final videoyu yeniden render eder. Statusler `outputs/review-status.json` dosyasinda saklanir.

## Kurulum

```powershell
py -m pip install -e .
Copy-Item .env.example .env
```

## Windows FFmpeg Kurulumu

Winget ile:

```powershell
winget install Gyan.FFmpeg
```

Chocolatey ile:

```powershell
choco install ffmpeg
```

Manuel kurulum:

1. `https://www.gyan.dev/ffmpeg/builds/` adresinden release build indir.
2. ZIP dosyasini ac.
3. `bin` klasorunu Windows PATH'e ekle.
4. Yeni PowerShell acip kontrol et:

```powershell
ffmpeg -version
```

`.env` ornegi:

```powershell
YOUTUBE_API_KEY=your_youtube_data_api_key
CHANNEL_NAME=Masyra Labs
TREND_REGION_CODE=US
TREND_SOURCE_LIMIT=50
TREND_TOP_N=10
SHORTS_OUTPUT_DIR=outputs
VIDEO_PROVIDER=auto
PEXELS_API_KEY=
PIXABAY_API_KEY=
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
PIPER_BIN=piper
PIPER_MODEL_PATH=/opt/masyra-shorts/models/piper/en_US-lessac-medium.onnx
VISUAL_PROVIDER=openai
IMAGE_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_IMAGE_SIZE=1024x1536
YOUTUBE_OAUTH_CLIENT_ID=
YOUTUBE_OAUTH_CLIENT_SECRET=
```

## Kullanım

Ornek veriyle gunluk rapor ve video paketleri:

```powershell
py -m shorts_automation.cli daily-run --sample
```

Ornek veriyle rapor, paketler ve FFmpeg varsa MP4 render:

```powershell
py -m shorts_automation.cli daily-run --sample --render
```

Ornek veriyle local placeholder sahne gorselleri ve preview render:

```powershell
py -m shorts_automation.cli daily-run --sample --render --preview-only --image-provider placeholder
```

OpenAI Images ile sahne gorselleri uretmek:

```powershell
$env:OPENAI_API_KEY="your_key_here"
py -m shorts_automation.cli daily-run --sample --render --image-provider openai
```

OpenAI Images ile tek paket icin sahne gorselleri uretmek:

```powershell
$env:OPENAI_API_KEY="your_key_here"
py -m shorts_automation.cli generate-visuals outputs\2026-06-09\videos\01-example --image-provider openai
```

Tek video paketi icin stock video klipleri indirmek:

```powershell
py -m shorts_automation.cli generate-video-clips outputs\2026-06-09\videos\01-example --video-provider pexels
```

Tum paketler icin stock video klipleri indirmek:

```powershell
py -m shorts_automation.cli generate-video-clips-all outputs\2026-06-09\videos --video-provider auto
```

OpenAI hata detaylarini `visual-result.json` ve `scene-manifest.json` icine yazmak:

```powershell
py -m shorts_automation.cli generate-visuals outputs\2026-06-09\videos\01-example --image-provider openai --debug
```

OpenAI hata verirse bilincli olarak placeholder fallback'e izin vermek:

```powershell
py -m shorts_automation.cli generate-visuals outputs\2026-06-09\videos\01-example --image-provider openai --allow-placeholder
```

Desteklenen `OPENAI_IMAGE_SIZE` degerleri:

```text
1024x1024
1024x1536
1536x1024
```

15 saniyelik hizli preview render:

```powershell
py -m shorts_automation.cli daily-run --sample --render --quick-preview
```

Yalnizca preview ve thumbnail uretmek:

```powershell
py -m shorts_automation.cli daily-run --sample --render --preview-only
```

ElevenLabs varsayilan TTS provider'dir. API key yoksa ElevenLabs cagrisi yapilmaz ve ses dosyasi uretmez:

```powershell
py -m shorts_automation.cli daily-run --sample --render
```

Ubuntu'da Piper ile API key olmadan offline `voiceover.mp3` uretmek:

```powershell
py -m shorts_automation.cli generate-tts outputs\2026-06-09\videos\01-example --tts-provider piper
```

Piper ile tum paketler icin TTS:

```powershell
py -m shorts_automation.cli generate-tts-all outputs\2026-06-09\videos --tts-provider piper
```

ElevenLabs ile `voiceover.mp3` uretmek:

```powershell
$env:ELEVENLABS_API_KEY="your_key_here"
py -m shorts_automation.cli daily-run --sample --tts-provider elevenlabs --render
```

Tek video paketi icin TTS calistirmak:

```powershell
py -m shorts_automation.cli generate-tts outputs\2026-06-09\videos\01-example --tts-provider elevenlabs
```

Var olan `voiceover.mp3` dosyasini yeniden uretmek:

```powershell
py -m shorts_automation.cli generate-tts outputs\2026-06-09\videos\01-example --tts-provider elevenlabs --force
```

Tum video paketleri icin TTS calistirmak:

```powershell
py -m shorts_automation.cli generate-tts-all outputs\2026-06-09\videos --tts-provider elevenlabs
```

Mock provider ile API key olmadan TTS workflow test etmek:

```powershell
py -m shorts_automation.cli generate-tts outputs\2026-06-09\videos\01-example --tts-provider mock
```

Render oncesi TTS uretmeyi denemek ve varsa sesi videoya gommek:

```powershell
py -m shorts_automation.cli render-video outputs\2026-06-09\videos\01-example --with-audio --tts-provider elevenlabs
```

Var olan tek paket icin sahne gorselleri uretmek:

```powershell
py -m shorts_automation.cli generate-visuals outputs\2026-06-09\videos\01-example --image-provider placeholder
```

Var olan video klasorundeki tum paketler icin OpenAI sahne gorselleri uretmek:

```powershell
py -m shorts_automation.cli generate-visuals-all outputs\2026-06-09\videos --image-provider openai
```

Var olan sahne gorsellerini bilincli olarak yeniden uretmek:

```powershell
py -m shorts_automation.cli generate-visuals outputs\2026-06-09\videos\01-example --image-provider openai --force
```

Render oncesi gorsel uretmeyi denemek:

```powershell
py -m shorts_automation.cli render-video outputs\2026-06-09\videos\01-example --with-visuals --image-provider openai
```

Render oncesi stock video klipleri indirmeyi denemek:

```powershell
py -m shorts_automation.cli render-video outputs\2026-06-09\videos\01-example --with-clips --video-provider auto
```

Canli kaynaklarla gunluk calisma:

```powershell
py -m shorts_automation.cli daily-run
```

Canli kaynaklarla render:

```powershell
py -m shorts_automation.cli daily-run --render
```

Tek video paketini render etmek:

```powershell
py -m shorts_automation.cli render-video outputs\2026-06-09\videos\01-example
```

Tek video paketini preview olarak render etmek:

```powershell
py -m shorts_automation.cli render-video outputs\2026-06-09\videos\01-example --quick-preview
```

Ornek tek video paketi uretmek ve render etmek:

```powershell
py -m shorts_automation.cli generate-video --render
```

Review dashboard baslatmak:

```powershell
py -m shorts_automation.cli dashboard --output-dir outputs --port 8765
```

Sonra tarayicida:

```text
http://127.0.0.1:8765
```

Upload guvenligi:

```powershell
py -m shorts_automation.cli daily-run --render --upload
```

`--upload` acikca verilmedikce upload denenmez. Mevcut surum YouTube OAuth entegrasyonu olmadan upload yapmaz; summary icinde uyari doner.

Upload gate kurallari:

- `--upload` verilmezse upload denenmez.
- `YOUTUBE_OAUTH_CLIENT_ID` ve `YOUTUBE_OAUTH_CLIENT_SECRET` yoksa upload denenmez.
- Video statusu `Approved` degilse upload denenmez.
- `final.mp4` yoksa upload denenmez.
- Bu build icinde uploader bilerek pasif tutulur; gate gecse bile gercek upload uygulanmaz.

Windows Task Scheduler icin:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\daily-run.ps1
```

## Ciktilar

Her gun icin `outputs/YYYY-MM-DD/` altinda:

- `daily-trend-report.json`
- `daily-run-summary.json`
- `videos/01-.../` ile baslayan 10 video paketi
- `videos/01-.../final.mp4` FFmpeg varsa uretilen final video
- `videos/01-.../preview.mp4` quick-preview modunda uretilen hizli onizleme
- `videos/01-.../thumbnail.jpg`
- `videos/01-.../preview-thumbnail.jpg`
- `videos/01-.../video-clips-manifest.json`
- `videos/01-.../video-clips-result.json`
- `videos/01-.../video-clips/clip-01.mp4` ile baslayan lisansli stock klipler
- `videos/01-.../scene-manifest.json`
- `videos/01-.../visual-result.json`
- `videos/01-.../scene-images/scene-01.png` ile baslayan 4-6 sahne gorseli
- `videos/01-.../voiceover.mp3` ElevenLabs TTS basariliysa uretilen ses
- `videos/01-.../tts-result.json`
- `videos/01-.../quality-score.json`
- `videos/01-.../asset-prompts.json`
- `videos/01-.../copyright-checklist.json`
- `review-status.json`

Bu dosyalar upload oncesi editor, TTS, render ve YouTube OAuth upload adimlari icin hazir veri saglar.

## Ubuntu VPS Deployment

Ubuntu 24.04 copy/paste deployment runbook:

[deploy/UBUNTU_24_04_DEPLOYMENT.md](deploy/UBUNTU_24_04_DEPLOYMENT.md)

Target layout:

```text
masyralabs.com       -> public landing page
app.masyralabs.com   -> private review dashboard behind Nginx basic auth
/var/www/masyra-labs -> landing page files
/opt/masyra-shorts   -> Shorts automation backend/dashboard
127.0.0.1:8765       -> dashboard service, not public directly
```

Important: keep this deployment separate from LeadAction and your existing sites. Do not edit or replace existing Nginx files for `gokergencoglu.com` or `leadaction.io`. Add only the new `masyralabs.com` and `app.masyralabs.com` site configs.

### 1. DNS

Point these records to the VPS public IP:

```text
A  masyralabs.com      YOUR_VPS_IP
A  www.masyralabs.com  YOUR_VPS_IP
A  app.masyralabs.com  YOUR_VPS_IP
```

### 2. Copy Project To VPS

From your local machine:

```powershell
scp -r . root@YOUR_VPS_IP:/opt/masyra-shorts
```

Or clone/copy by your preferred deploy method, then SSH:

```powershell
ssh root@YOUR_VPS_IP
cd /opt/masyra-shorts
```

### 3. Install Ubuntu Dependencies

On the VPS:

```bash
cd /opt/masyra-shorts
sudo bash scripts/install-ubuntu.sh
```

This installs:

- `python3`
- `python3-venv`
- `python3-pip`
- `ffmpeg`
- `nginx`
- `apache2-utils`
- `certbot`
- `python3-certbot-nginx`
- `curl`
- `piper-tts` inside `/opt/masyra-shorts/.venv`
- default Piper voice model at `/opt/masyra-shorts/models/piper/en_US-lessac-medium.onnx`

Ubuntu FFmpeg check:

```bash
ffmpeg -version
```

Piper check:

```bash
/opt/masyra-shorts/.venv/bin/piper --help
ls -lh /opt/masyra-shorts/models/piper/en_US-lessac-medium.onnx
```

### 4. Configure Environment

```bash
sudo nano /opt/masyra-shorts/.env
```

Minimum live config:

```bash
YOUTUBE_API_KEY=your_youtube_data_api_key
CHANNEL_NAME=Masyra Labs
TREND_REGION_CODE=US
TREND_SOURCE_LIMIT=50
TREND_TOP_N=10
SHORTS_OUTPUT_DIR=outputs
TTS_PROVIDER=piper
ELEVENLABS_API_KEY=
PIPER_BIN=/opt/masyra-shorts/.venv/bin/piper
PIPER_MODEL_PATH=/opt/masyra-shorts/models/piper/en_US-lessac-medium.onnx
YOUTUBE_OAUTH_CLIENT_ID=
YOUTUBE_OAUTH_CLIENT_SECRET=
```

Upload remains disabled by default. Do not add upload automation until OAuth is configured, a package is `Approved`, and you intentionally implement the uploader.

### 5. Nginx Basic Auth For Dashboard

The dashboard must not be public without protection. Create a password file:

```bash
sudo htpasswd -c /etc/nginx/.htpasswd-masyra-labs admin
```

For additional users later:

```bash
sudo htpasswd /etc/nginx/.htpasswd-masyra-labs another-user
```

The `app.masyralabs.com` example keeps basic auth enabled for the dashboard and only disables it for `/.well-known/acme-challenge/` so Certbot can issue/renew SSL certificates.

### 6. Enable Nginx Sites

Review the example files first:

```bash
cat /opt/masyra-shorts/deploy/nginx/masyralabs.com.conf
cat /opt/masyra-shorts/deploy/nginx/app.masyralabs.com.conf
```

Install only the new Masyra Labs configs:

```bash
sudo cp /opt/masyra-shorts/deploy/nginx/masyralabs.com.conf /etc/nginx/sites-available/masyralabs.com
sudo cp /opt/masyra-shorts/deploy/nginx/app.masyralabs.com.conf /etc/nginx/sites-available/app.masyralabs.com
sudo ln -s /etc/nginx/sites-available/masyralabs.com /etc/nginx/sites-enabled/masyralabs.com
sudo ln -s /etc/nginx/sites-available/app.masyralabs.com /etc/nginx/sites-enabled/app.masyralabs.com
sudo nginx -t
sudo systemctl reload nginx
```

Again: do not touch `gokergencoglu.com` or `leadaction.io` Nginx configs.

### 7. Systemd Dashboard Service

```bash
sudo cp /opt/masyra-shorts/deploy/systemd/masyra-shorts-dashboard.service /etc/systemd/system/masyra-shorts-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable masyra-shorts-dashboard
sudo systemctl start masyra-shorts-dashboard
sudo systemctl status masyra-shorts-dashboard
```

Dashboard local check on VPS:

```bash
curl -I http://127.0.0.1:8765
```

Public protected dashboard:

```text
https://app.masyralabs.com
```

### 8. Certbot SSL

After DNS points to the VPS and Nginx config passes:

```bash
sudo certbot --nginx -d masyralabs.com -d www.masyralabs.com
sudo certbot --nginx -d app.masyralabs.com
sudo systemctl reload nginx
```

Renewal check:

```bash
sudo certbot renew --dry-run
```

### 9. Daily Cron At 3 AM

Install the cron example:

```bash
sudo cp /opt/masyra-shorts/deploy/cron/masyra-shorts-daily.cron /etc/cron.d/masyra-shorts-daily
sudo chmod 0644 /etc/cron.d/masyra-shorts-daily
sudo systemctl restart cron
```

Manual daily run:

```bash
sudo -u www-data APP_DIR=/opt/masyra-shorts /opt/masyra-shorts/scripts/daily-run.sh
```

Logs:

```bash
tail -f /opt/masyra-shorts/outputs/cron.log
journalctl -u masyra-shorts-dashboard -f
```

### 10. Deployment Commands Summary

```bash
cd /opt/masyra-shorts
sudo bash scripts/install-ubuntu.sh
sudo htpasswd -c /etc/nginx/.htpasswd-masyra-labs admin
sudo cp deploy/nginx/masyralabs.com.conf /etc/nginx/sites-available/masyralabs.com
sudo cp deploy/nginx/app.masyralabs.com.conf /etc/nginx/sites-available/app.masyralabs.com
sudo ln -s /etc/nginx/sites-available/masyralabs.com /etc/nginx/sites-enabled/masyralabs.com
sudo ln -s /etc/nginx/sites-available/app.masyralabs.com /etc/nginx/sites-enabled/app.masyralabs.com
sudo nginx -t
sudo systemctl reload nginx
sudo cp deploy/systemd/masyra-shorts-dashboard.service /etc/systemd/system/masyra-shorts-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now masyra-shorts-dashboard
sudo certbot --nginx -d masyralabs.com -d www.masyralabs.com
sudo certbot --nginx -d app.masyralabs.com
sudo cp deploy/cron/masyra-shorts-daily.cron /etc/cron.d/masyra-shorts-daily
sudo chmod 0644 /etc/cron.d/masyra-shorts-daily
```
