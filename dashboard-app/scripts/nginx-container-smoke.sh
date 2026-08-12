#!/usr/bin/env sh
set -eu

IMAGE="${1:-media-manager-angular:smoke}"

docker build -t "$IMAGE" .

docker run --rm --add-host homepage-actions:127.0.0.1 -e ACTIONS_TOKEN=test-token --entrypoint /bin/sh "$IMAGE" -c '
  /docker-entrypoint.d/20-envsubst-on-templates.sh
  nginx -t
  internal_line="$(grep -nF "location ^~ /api/internal/" /etc/nginx/conf.d/default.conf | cut -d: -f1)"
  generation_line="$(grep -nF "location = /api/discover/hermes/generations" /etc/nginx/conf.d/default.conf | cut -d: -f1)"
  sync_line="$(grep -nF "location = /api/discover/hermes/sync" /etc/nginx/conf.d/default.conf | cut -d: -f1)"
  public_line="$(grep -nF "location /api/" /etc/nginx/conf.d/default.conf | cut -d: -f1)"
  test -n "$internal_line"
  test -n "$generation_line"
  test -n "$sync_line"
  test -n "$public_line"
  test "$internal_line" -lt "$public_line"
  test "$generation_line" -lt "$public_line"
  test "$sync_line" -lt "$public_line"
  awk "/location = \/api\/discover\/hermes\/generations/{getline; if (\$0 !~ /return 404;/) exit 1; found=1} END{if (!found) exit 1}" /etc/nginx/conf.d/default.conf
  awk "/location = \/api\/discover\/hermes\/sync/{getline; if (\$0 !~ /return 404;/) exit 1; found=1} END{if (!found) exit 1}" /etc/nginx/conf.d/default.conf
  grep -F "return 404;" /etc/nginx/conf.d/default.conf
  grep -F "\$uri" /etc/nginx/conf.d/default.conf
  grep -F "\$host" /etc/nginx/conf.d/default.conf
  grep -F "\$http_origin" /etc/nginx/conf.d/default.conf
  grep -F "\$proxy_add_x_forwarded_for" /etc/nginx/conf.d/default.conf
  grep -F "X-Actions-Token test-token" /etc/nginx/conf.d/default.conf
'

docker run --rm --add-host homepage-actions:127.0.0.1 -e ACTIONS_TOKEN=test-token --entrypoint /bin/sh "$IMAGE" -c '/docker-entrypoint.d/20-envsubst-on-templates.sh; nginx -t'

echo "nginx-container-smoke: ok"
