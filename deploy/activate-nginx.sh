#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" -eq 0 || { echo "Ejecuta con sudo." >&2; exit 1; }
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
owner=$(stat -c '%U' "$repo")
test "$owner" != root
site=/etc/nginx/sites-available/promption.incubunt.com
enabled=/etc/nginx/sites-enabled/promption.incubunt.com
test -r /etc/ssl/certs/cloudflare_incubunt.pem
test -r /etc/ssl/private/cloudflare_incubunt.key
for url in http://127.0.0.1:3100/ http://127.0.0.1:8100/api/v1/health http://127.0.0.1:8101/health; do
    curl --fail --silent --retry 10 --retry-connrefused --retry-delay 1 --max-time 5 --output /dev/null "$url"
done
test ! -e "$site" && test ! -L "$enabled" && test ! -e "$enabled" || {
    echo "El sitio Promption ya existe. Revísalo antes de reemplazarlo." >&2; exit 1;
}
rollback() {
    rm -f "$enabled" "$site"
}
trap rollback ERR
install -m 0644 "$repo/deploy/nginx-promption.conf" "$site"
ln -s "$site" "$enabled"
nginx -t
systemctl reload nginx
trap - ERR
loginctl enable-linger "$owner"
echo "Promption activado. En Cloudflare: DNS A promption → 148.113.236.79, proxy activado y SSL Full (strict) para este hostname."
