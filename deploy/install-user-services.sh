#!/usr/bin/env bash
set -euo pipefail
umask 077
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
for name in filter chat web; do
    test -s "$HOME/.config/promption/$name.env" || { echo "Falta $name.env" >&2; exit 1; }
done
test -x "$repo/.venv/bin/python"
test -f "$repo/demo/.next/BUILD_ID"
node_bin=$(command -v node)
mkdir -p "$HOME/.config/systemd/user" "$HOME/.local/share/promption"
write_unit() {
    local name=$1 directory=$2 command=$3
    cat > "$HOME/.config/systemd/user/promption-$name.service" <<EOF
[Unit]
Description=Promption $name
After=network.target

[Service]
Type=simple
WorkingDirectory=$directory
EnvironmentFile=%h/.config/promption/$name.env
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$repo
ExecStart=$command
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
}
write_unit filter "$repo" "$repo/.venv/bin/python -m uvicorn promption.api.main:app --host 127.0.0.1 --port 8100 --workers 1"
write_unit chat "$repo/chat-service" "$repo/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8101 --workers 1"
write_unit web "$repo/demo" "$node_bin $repo/demo/node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3100"
if test -x "$repo/.venv/bin/streamlit" && test -s "$HOME/.config/promption/dashboard.env"; then
    write_unit dashboard "$repo" "$repo/.venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8510 --server.headless true --browser.gatherUsageStats false"
fi
systemd-analyze --user verify "$HOME/.config/systemd/user/promption-"*.service
systemctl --user daemon-reload
systemctl --user enable --now promption-filter promption-chat promption-web
if test -f "$HOME/.config/systemd/user/promption-dashboard.service"; then
    systemctl --user enable --now promption-dashboard
fi
echo "Servicios instalados. Consulta: systemctl --user status promption-{filter,chat,web}"
