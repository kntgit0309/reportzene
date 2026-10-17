#!/bin/bash
# Deploy ReportZenE lên macminiwork rồi khởi động lại service.
# usage: bash deploy/deploy.sh
#
# Trên macminiwork:
#   code   : ~/reportzene/{backend,web/dist}
#   dữ liệu: ~/reportzene/backend/data (SQLite + secret.key) — rsync không ghi đè
#   service: launchd online.kntmcptools.reportzene → uvicorn :8870 (bind IP Tailscale)
#   public : https://reportzene.trackingis.info qua tunnel cloudflared "mba-system" (chung MBA)
#   admin đầu tiên: tạo 1 lần, mật khẩu ngẫu nhiên ở ~/reportzene/.admin-password
#   token trackingis + Lark app: nhập trong web (Settings), lưu mã hoá trong DB bằng data/secret.key.
#   SSO POD: app riêng ReportZenE (17/10/2026). Key/secret chỉ nằm trong plist launchd (chmod 600), deploy sau tự giữ;
#   đổi app: POD_APP_KEY=... POD_APP_SECRET=... bash deploy/deploy.sh (plist trống thì mới lấy tạm từ plist TM Check ACO)
set -euo pipefail

HOST=macminiwork
BIND_IP=100.96.215.29
PORT=8870
LABEL=online.kntmcptools.reportzene
SSO_DONOR=online.kntmcptools.aco-tm-check   # plist có sẵn key/secret app SSO MBA
PUBLIC_URL="${PUBLIC_URL:-https://reportzene.trackingis.info}"   # Cloudflare tunnel "mba-system" (ingress thêm 17/10/2026)
ADMIN_EMAIL="${ADMIN_EMAIL:-copilot.isuccess@gmail.com}"
R=/Users/designertwo/reportzene
DEFAULT_ALLOWED="khoanht.des@isuccesscorp360.com"   # email vào thẳng qua SSO; người khác chờ admin mở khoá
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SECURE=false; [[ "$PUBLIC_URL" == https://* ]] && SECURE=true

echo "▸ Test + build web"
(cd "$HERE/backend" && uv run pytest -q -p no:logging >/dev/null)
(cd "$HERE/web" && npm run build >/dev/null)

echo "▸ Đồng bộ code"
ssh "$HOST" "mkdir -p $R/backend $R/web/dist $R/logs"
rsync -az --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.coverage' --exclude '.ruff_cache' --exclude 'data/' --exclude '.env' \
  "$HERE/backend/" "$HOST:$R/backend/"
rsync -az --delete "$HERE/web/dist/" "$HOST:$R/web/dist/"

echo "▸ Cài thư viện + admin đầu tiên"
ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
export PATH=/opt/homebrew/bin:\$PATH
cd $R/backend
uv sync --frozen --no-dev -q 2>/dev/null || uv sync --no-dev -q
if [ ! -f data/reportzene.db ]; then
  mkdir -p data
  PYTHONPATH=. uv run --no-dev python scripts/create_user.py "$ADMIN_EMAIL" "Khoa Nguyen" KHOA admin --password-file $R/.admin-password
  echo "  mật khẩu admin: $R/.admin-password"
fi
REMOTE

echo "▸ launchd"
PLIST_PATH="~/Library/LaunchAgents/$LABEL.plist"
# Value kept in the current plist; PlistBuddy prints its errors on stdout, so anything that is not a plain token is ignored.
current() {
  local v plist="${2:-$PLIST_PATH}"
  v=$(ssh "$HOST" "[ -f $plist ] && /usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:$1' $plist 2>/dev/null" || true)
  [[ "$v" =~ ^[A-Za-z0-9._:/+=@,-]+$ ]] && echo "$v" || true
}
DONOR_PLIST="~/Library/LaunchAgents/$SSO_DONOR.plist"
# Secrets live only in the launchd plist (chmod 600). Pass a value once (VAR=... bash deploy/deploy.sh); later deploys keep it.
SECRET_VARS="POD_APP_KEY POD_APP_SECRET POD_ALLOWED_USERS"
EXTRA_ENV=""
for VAR in $SECRET_VARS; do
  VAL="${!VAR:-$(current "$VAR")}"
  [ -z "$VAL" ] && [ "$VAR" != POD_ALLOWED_USERS ] && VAL="$(current "$VAR" "$DONOR_PLIST")"
  [ -z "$VAL" ] && [ "$VAR" = POD_ALLOWED_USERS ] && VAL="$DEFAULT_ALLOWED"
  [ -n "$VAL" ] && EXTRA_ENV="$EXTRA_ENV<key>$VAR</key><string>$VAL</string>"
  [ -n "$VAL" ] && echo "  $VAR: có" || echo "  $VAR: trống"
done
PLIST="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/opt/homebrew/bin/uv</string><string>run</string><string>--no-dev</string>
    <string>--directory</string><string>$R/backend</string>
    <string>uvicorn</string><string>app.main:app</string>
    <string>--host</string><string>$BIND_IP</string><string>--port</string><string>$PORT</string>
    <string>--proxy-headers</string>
  </array>
  <key>WorkingDirectory</key><string>$R/backend</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$R/logs/server.log</string>
  <key>StandardErrorPath</key><string>$R/logs/server.log</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>COOKIE_SECURE</key><string>$SECURE</string>
    <key>CORS_ORIGINS</key><string>$PUBLIC_URL</string>
    <key>POD_REDIRECT_URL</key><string>$PUBLIC_URL/auth/pod/callback</string>
    $EXTRA_ENV
  </dict>
</dict></plist>"
ssh "$HOST" "umask 077; cat > $PLIST_PATH && chmod 600 $PLIST_PATH" <<<"$PLIST"
ssh "$HOST" "launchctl bootout gui/\$(id -u)/$LABEL 2>/dev/null || true
for i in 1 2 3 4 5 6 7 8 9 10; do launchctl print gui/\$(id -u)/$LABEL >/dev/null 2>&1 || break; sleep 1; done
launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/$LABEL.plist"

echo "▸ Health check"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if ssh "$HOST" "curl -fsS http://$BIND_IP:$PORT/api/health" >/dev/null 2>&1; then
    echo "  OK → $PUBLIC_URL"
    exit 0
  fi
  sleep 2
done
echo "  Server chưa lên — xem log: ssh $HOST tail -50 $R/logs/server.log"
exit 1
