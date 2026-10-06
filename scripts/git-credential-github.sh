#!/bin/bash
# Git credential helper for GitHub — reads GITHUB_TOKEN from environment.
# Configured via: git config credential.helper '/path/to/this/script'
# Supports the git credential protocol (get/store/erase).

case "$1" in
  get)
    echo "protocol=https"
    echo "host=github.com"
    echo "username=x-access-token"
    echo "password=${GITHUB_TOKEN}"
    ;;
esac
