#!/usr/bin/env sh
set -eu

IMAGE="${1:-media-manager-angular:smoke}"

docker build -t "$IMAGE" .

docker run --rm -e ACTIONS_TOKEN=test-token --entrypoint /bin/sh "$IMAGE" -c '
  nginx -t
  internal_line="$(grep -nF "location ^~ /api/internal/" /etc/nginx/conf.d/default.conf | cut -d: -f1)"
  public_line="$(grep -nF "location /api/" /etc/nginx/conf.d/default.conf | cut -d: -f1)"
  test -n "$internal_line"
  test -n "$public_line"
  test "$internal_line" -lt "$public_line"
  grep -F "return 404;" /etc/nginx/conf.d/default.conf
  grep -F "$uri" /etc/nginx/conf.d/default.conf
  grep -F "$host" /etc/nginx/conf.d/default.conf
  grep -F "$http_origin" /etc/nginx/conf.d/default.conf
  grep -F "$proxy_add_x_forwarded_for" /etc/nginx/conf.d/default.conf
  grep -F "X-Actions-Token test-token" /etc/nginx/conf.d/default.conf
'

docker run --rm --entrypoint /bin/sh "$IMAGE" -c 'nginx -t'

echo "nginx-container-smoke: ok"
