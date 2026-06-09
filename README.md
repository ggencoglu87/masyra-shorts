# Masyra Labs Trend-Following Shorts Network

Masyra Labs artik kategori bazli tek kaynakli Shorts planlayici degil, cok kaynakli bir trend-following Shorts network iskeletidir.

Sistem gunluk trend sinyallerini toplar, kategorilere ayirir, puanlar, en iyi 10 trendi secer ve her biri icin ozgun Shorts paketi hazirlar.

## Kaynaklar

- YouTube Trends: `videos.list chart=mostPopular`
- YouTube Search: populer arama sorgulari icin `search.list` ve video detaylari
- Google Trends: gunluk RSS trendleri
- Reddit: `r/popular` basliklari ve upvote sinyali

YouTube kaynaklari icin `YOUTUBE_API_KEY` gerekir. Google Trends RSS ve Reddit herkese acik endpoint kullanir, fakat ag politikasi veya servis tarafli kisitlar nedeniyle bazen bos donebilir.

## Trend Kategorileri

- Sports
- Horror Stories
- Funny Kids
- Viral News
- Gaming
- AI
- Celebrity
- Animals
- Movies & TV
- Misc Viral

Kategori secimi artik YouTube kategori ID'sine bagli degildir. Sistem baslik, kaynak ve anahtar kelime sinyallerinden kendi kategorisini tahmin eder.

## Skor Algoritmasi

Her trend icin dort skor uretilir:

- `trend_score`: gorunurluk gucu. YouTube goruntulenme/begeni, Reddit upvote, Google Trends trafik ve kaynak sayisini birlestirir.
- `growth_score`: buyume hizi. Yayin yasina gore YouTube view velocity, Google Trends trafik artisi, Reddit upvote ve cok kaynak sinyalini kullanir.
- `competition_score`: rekabet puani. Benzer YouTube arama yogunlugu, kaynak sayisi ve uzun/genis baslik sinyalinden hesaplanir. Yuksek rekabet daha zor firsat demektir.
- `viral_potential_score`: nihai secim puani. Formul:

```text
viral = trend_score * 0.38
      + growth_score * 0.27
      + (100 - competition_score) * 0.18
      + emotional_category_score * 0.17
```

`emotional_category_score`, Shorts izlenebilirligini artiran kategori etkisini temsil eder. Horror Stories, Animals, Funny Kids ve AI gibi formatlar daha yuksek taban alir.

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

FFmpeg varsa sistem her paket icin temiz dikey Shorts layout ile `final.mp4` uretir. Varsayilan final video suresi 25 saniyedir. `--render` artik otomatik olarak 12 saniyelik `preview.mp4` ve thumbnail da uretir. `--preview-only` yalnizca hizli preview ve thumbnail uretir. FFmpeg yoksa script, voiceover, altyazi ve metadata uretimi devam eder; summary icinde net uyari doner.

ElevenLabs varsayilan TTS provider'dir. `ELEVENLABS_API_KEY` varsa `voiceover.mp3` uretilir ve FFmpeg render bunu final/preview videoya gomar. API key yoksa sistem mock fallback ile `voiceover.txt` uretmeye devam eder.

Dashboard ile her gunluk trend/video paketini thumbnail, preview/final video, script ve checklist ile inceleyebilir, `Needs Edit`, `Approved`, `Rejected` statuslerinden birini verebilirsin. Statusler `outputs/review-status.json` dosyasinda saklanir.

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
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
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

15 saniyelik hizli preview render:

```powershell
py -m shorts_automation.cli daily-run --sample --render --quick-preview
```

Yalnizca preview ve thumbnail uretmek:

```powershell
py -m shorts_automation.cli daily-run --sample --render --preview-only
```

ElevenLabs varsayilan TTS provider'dir. API key yoksa mock fallback devreye girer ve ses dosyasi uretmez:

```powershell
py -m shorts_automation.cli daily-run --sample --render
```

ElevenLabs ile `voiceover.mp3` uretmek:

```powershell
$env:ELEVENLABS_API_KEY="your_key_here"
py -m shorts_automation.cli daily-run --sample --tts-provider elevenlabs --render
```

Var olan video paketleri icin TTS calistirmak:

```powershell
py -m shorts_automation.cli generate-tts outputs\2026-06-09\videos --tts-provider elevenlabs
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
- `videos/01-.../voiceover.mp3` ElevenLabs TTS basariliysa uretilen ses
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

Ubuntu FFmpeg check:

```bash
ffmpeg -version
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
TTS_PROVIDER=mock
ELEVENLABS_API_KEY=
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
