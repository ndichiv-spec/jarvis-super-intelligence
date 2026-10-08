#!/bin/sh
set -eu

password="$(cat /run/secrets/redis_password)"
test -n "$password"
exec redis-server --appendonly yes --requirepass "$password"
