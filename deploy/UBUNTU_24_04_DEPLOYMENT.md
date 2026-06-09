# Masyra Labs Ubuntu 24.04 VPS Deployment

This runbook deploys Masyra Labs on an existing Ubuntu 24.04 VPS.

Target:

```text
masyralabs.com             -> /var/www/masyra-labs landing page
www.masyralabs.com         -> /var/www/masyra-labs landing page
app.masyralabs.com         -> Nginx basic auth -> 127.0.0.1:8765
/opt/masyra-shorts         -> backend/dashboard app
```

Do not modify existing `gokergencoglu.com` or `leadaction.io` Nginx configs. Keep this deployment separate.

## 1. SSH Into VPS

```bash
ssh root@138.199.214.167
```

## 2. Put The Project In Place

If the project is not already on the VPS, copy it from your local machine:

```powershell
scp -r . root@138.199.214.167:/opt/masyra-shorts
```

Then on the VPS:

```bash
cd /opt/masyra-shorts
```

## 3. Install Ubuntu Packages And Python Environment

```bash
cd /opt/masyra-shorts
sudo bash scripts/install-ubuntu.sh
```

This installs Python, Nginx, FFmpeg, Certbot, Apache htpasswd tooling, and the project virtual environment.

Verify FFmpeg:

```bash
ffmpeg -version
```

## 4. Configure Environment

```bash
sudo nano /opt/masyra-shorts/.env
```

Recommended starting values:

```bash
YOUTUBE_API_KEY=your_youtube_data_api_key
CHANNEL_NAME=Masyra Labs
TREND_REGION_CODE=US
TREND_SOURCE_LIMIT=50
TREND_TOP_N=10
SHORTS_OUTPUT_DIR=outputs
TTS_PROVIDER=mock
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
YOUTUBE_OAUTH_CLIENT_ID=
YOUTUBE_OAUTH_CLIENT_SECRET=
```

Upload stays disabled unless OAuth is configured, `--upload` is explicitly used, the video has `Approved` status, and `final.mp4` exists.

## 5. Create Dashboard Basic Auth

Dashboard must not be public without protection.

```bash
sudo htpasswd -c /etc/nginx/.htpasswd-masyra-labs admin
```

Add more users later:

```bash
sudo htpasswd /etc/nginx/.htpasswd-masyra-labs another-user
```

## 6. Install Nginx Configs

Only add the new Masyra Labs configs:

```bash
sudo cp /opt/masyra-shorts/deploy/nginx/masyralabs.com.conf /etc/nginx/sites-available/masyralabs.com
sudo cp /opt/masyra-shorts/deploy/nginx/app.masyralabs.com.conf /etc/nginx/sites-available/app.masyralabs.com
```

Enable them:

```bash
sudo ln -s /etc/nginx/sites-available/masyralabs.com /etc/nginx/sites-enabled/masyralabs.com
sudo ln -s /etc/nginx/sites-available/app.masyralabs.com /etc/nginx/sites-enabled/app.masyralabs.com
```

If symlinks already exist, leave them alone or recreate only these Masyra Labs links. Do not touch existing site links for `gokergencoglu.com` or `leadaction.io`.

Test and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 7. Install Dashboard Systemd Service

```bash
sudo cp /opt/masyra-shorts/deploy/systemd/masyra-shorts-dashboard.service /etc/systemd/system/masyra-shorts-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable masyra-shorts-dashboard
sudo systemctl start masyra-shorts-dashboard
sudo systemctl status masyra-shorts-dashboard
```

The service uses:

```text
Restart=always
RestartSec=5
```

So the dashboard automatically restarts if it crashes.

Local dashboard check:

```bash
curl -I http://127.0.0.1:8765
```

## 8. Issue HTTPS Certificates

Run after Nginx config is enabled and DNS points to `138.199.214.167`.

```bash
sudo certbot --nginx -d masyralabs.com -d www.masyralabs.com
sudo certbot --nginx -d app.masyralabs.com
```

Reload Nginx:

```bash
sudo systemctl reload nginx
```

Verify renewal:

```bash
sudo certbot renew --dry-run
```

## 9. Install Daily 3 AM Cron

```bash
sudo cp /opt/masyra-shorts/deploy/cron/masyra-shorts-daily.cron /etc/cron.d/masyra-shorts-daily
sudo chmod 0644 /etc/cron.d/masyra-shorts-daily
sudo systemctl restart cron
```

Manual daily run:

```bash
sudo -u www-data APP_DIR=/opt/masyra-shorts /opt/masyra-shorts/scripts/daily-run.sh
```

## 10. Logs And Checks

Dashboard logs:

```bash
journalctl -u masyra-shorts-dashboard -f
```

Daily job logs:

```bash
tail -f /opt/masyra-shorts/outputs/cron.log
```

Nginx checks:

```bash
curl -I https://masyralabs.com
curl -I https://www.masyralabs.com
curl -I https://app.masyralabs.com
```

The `app.masyralabs.com` request should require basic auth.

## Copy/Paste Full VPS Command Block

Review before running. This block assumes the project already exists at `/opt/masyra-shorts`.

```bash
cd /opt/masyra-shorts
sudo bash scripts/install-ubuntu.sh
sudo htpasswd -c /etc/nginx/.htpasswd-masyra-labs admin
sudo cp /opt/masyra-shorts/deploy/nginx/masyralabs.com.conf /etc/nginx/sites-available/masyralabs.com
sudo cp /opt/masyra-shorts/deploy/nginx/app.masyralabs.com.conf /etc/nginx/sites-available/app.masyralabs.com
sudo ln -s /etc/nginx/sites-available/masyralabs.com /etc/nginx/sites-enabled/masyralabs.com
sudo ln -s /etc/nginx/sites-available/app.masyralabs.com /etc/nginx/sites-enabled/app.masyralabs.com
sudo nginx -t
sudo systemctl reload nginx
sudo cp /opt/masyra-shorts/deploy/systemd/masyra-shorts-dashboard.service /etc/systemd/system/masyra-shorts-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable --now masyra-shorts-dashboard
curl -I http://127.0.0.1:8765
sudo certbot --nginx -d masyralabs.com -d www.masyralabs.com
sudo certbot --nginx -d app.masyralabs.com
sudo systemctl reload nginx
sudo cp /opt/masyra-shorts/deploy/cron/masyra-shorts-daily.cron /etc/cron.d/masyra-shorts-daily
sudo chmod 0644 /etc/cron.d/masyra-shorts-daily
sudo systemctl restart cron
```
