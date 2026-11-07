#!/usr/bin/env bash
# Write /etc/caddy/Caddyfile and reload Caddy gracefully (the engine is not touched).
#   CADDY_MODE=v1  live portal, API and downloads behind basic auth (the old site)
#   CADDY_MODE=v2  live portal and /downloads public; /api open to the portal's demo key, basic auth for the FreeCAD panel
# Both modes also serve the staging portal at /next (public pages, API on $NEXT_PORT, same key-or-login rule).
set -euo pipefail
: "${HOST:?}" "${NIC:?}" "${PORT:?}" "${SQ_USER:?}" "${SQ_PASS:?}"
MODE="${CADDY_MODE:-v2}"
NEXT_PORT="${NEXT_PORT:-8781}"
KEY="${SQ_PORTAL_KEY:-sonariq-demo}"
SRV=/srv/sonariq
HASH="$(caddy hash-password --plaintext "$SQ_PASS")"
api_block() {   # $1 = path prefix (/api or /next/api), $2 = upstream port
cat <<EOF
	@key_$2 {
		path $1/*
		header X-SonarIQ-Key $KEY
	}
	handle @key_$2 {
		uri strip_prefix $1
		reverse_proxy 127.0.0.1:$2 {
			flush_interval -1
		}
	}
	handle_path $1/* {
		basicauth {
			$SQ_USER $HASH
		}
		reverse_proxy 127.0.0.1:$2 {
			flush_interval -1
		}
	}
EOF
}
{
echo "# Managed by sonariq/scripts/caddy_write.sh (mode $MODE)"
echo "$HOST {"
echo "	bind $NIC"
echo "	encode gzip"
api_block /next/api "$NEXT_PORT"
cat <<EOF
	handle_path /next/downloads/* {
		root * $SRV/downloads
		file_server browse
	}
	handle_path /next/* {
		root * $SRV/next
		try_files {path} /index.html
		file_server
	}
	redir /next /next/
EOF
if [ "$MODE" = v2 ]; then
api_block /api "$PORT"
cat <<EOF
	handle_path /downloads/* {
		root * $SRV/downloads
		file_server browse
	}
	handle {
		root * $SRV/portal
		try_files {path} /index.html
		file_server
	}
EOF
else
cat <<EOF
	handle {
		basicauth {
			$SQ_USER $HASH
		}
		handle_path /api/* {
			reverse_proxy 127.0.0.1:$PORT {
				flush_interval -1
			}
		}
		handle_path /downloads/* {
			root * $SRV/downloads
			file_server browse
		}
		handle {
			root * $SRV/portal
			try_files {path} /index.html
			file_server
		}
	}
EOF
fi
echo "}"
} > /tmp/Caddyfile.sonariq
sudo caddy validate --config /tmp/Caddyfile.sonariq --adapter caddyfile >/dev/null
sudo cp /tmp/Caddyfile.sonariq /etc/caddy/Caddyfile
rm -f /tmp/Caddyfile.sonariq
sudo systemctl reload caddy
echo "caddy: mode $MODE written and reloaded"
