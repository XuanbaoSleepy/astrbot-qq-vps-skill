#!/usr/bin/env bash
# Read-only. Keep output in a private terminal, not a public report.
set -uo pipefail
deploy_dir=
with_cloudflare=false
with_resend=false
while (( $# )); do
  case "$1" in
    --deploy-dir)
      [[ $# -ge 2 ]] || { echo 'missing deploy-dir' >&2; exit 2; }
      deploy_dir=$2
      shift 2 ;;
    --with-cloudflare) with_cloudflare=true; shift ;;
    --with-resend) with_resend=true; shift ;;
    --help) echo 'Usage: preflight.sh [--deploy-dir TARGET_DIRECTORY] [--with-cloudflare] [--with-resend] (read-only; optional probes are off by default)'; exit 0 ;;
    *) echo 'unknown argument' >&2; exit 2 ;;
  esac
done
if [[ $(uname -s) != Linux ]]; then
  echo 'UNVERIFIED: Linux target required' >&2
  exit 2
fi
probe() {
  local title=$1
  shift
  printf '\n[%s]\n' "$title"
  if ! command -v "$1" >/dev/null 2>&1; then
    echo 'UNVERIFIED: tool unavailable'
  elif ! "$@"; then
    echo 'UNVERIFIED: command failed or permission denied'
  fi
}
probe os cat /etc/os-release
probe architecture uname -m
probe cpu getconf _NPROCESSORS_ONLN
probe memory free -h
probe swap swapon --show
probe disk df -h
probe inode df -i
probe clock timedatectl status
probe docker docker version --format '{{.Server.Version}}'
probe compose docker compose version
probe containers docker ps -a --format '{{.Names}} {{.State}}'
probe compose-projects docker ps -a --format '{{.Label "com.docker.compose.project"}}'
probe listeners ss -lntu
probe docker-startup systemctl is-enabled docker
probe failed-units systemctl --failed --no-pager
probe related-units systemctl list-unit-files '*cloudflared*' '*qq*monitor*' --no-pager
if [[ -n $deploy_dir ]]; then
  if [[ -d $deploy_dir ]]; then
    printf 'target_directory=exists writable=%s\n' "$([[ -w $deploy_dir ]] && echo yes || echo no)"
    for entry in compose.yaml compose.yml docker-compose.yml data napcat ntqq snowluma astrbot; do
      [[ -e $deploy_dir/$entry ]] && printf 'target_existing=%s\n' "$entry"
    done
  elif [[ -e $deploy_dir ]]; then
    echo 'FAIL: target is not a directory'
  else
    echo 'target_directory=absent; creation not performed'
  fi
else
  echo 'UNVERIFIED: target directory not supplied'
fi
if command -v fuser >/dev/null 2>&1 && (( EUID == 0 )); then
  for lock in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/lib/apt/lists/lock; do
    if [[ -e $lock ]]; then
      if fuser "$lock" >/dev/null 2>&1; then
        echo 'FAIL: package-manager lock in use'
      else
        echo 'package-manager lock=not observed in use (recheck before apt)'
      fi
    fi
  done
else
  echo 'UNVERIFIED: package-manager lock ownership (root + fuser required)'
fi
for var in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
  [[ -n ${!var:-} ]] && printf 'proxy %s=set (value hidden)\n' "$var"
done
probe ipv4-forward sysctl net.ipv4.ip_forward
probe ipv6-forward sysctl net.ipv6.conf.all.forwarding
if (( EUID == 0 )); then
  for tool in nft iptables ip6tables; do
    if command -v "$tool" >/dev/null 2>&1; then
      case "$tool" in
        nft) rules=$(nft list ruleset 2>/dev/null) ;;
        *) rules=$("$tool" -S 2>/dev/null) ;;
      esac
      result=$?
      if (( result == 0 )); then
        printf 'firewall %s lines=%s (requires private review)\n' "$tool" "$(printf '%s' "$rules" | wc -l)"
      else
        printf 'UNVERIFIED: %s rules unavailable\n' "$tool"
      fi
      unset rules
    fi
  done
else
  echo 'UNVERIFIED: root firewall inspection not performed'
fi
hosts=(download.docker.com registry-1.docker.io)
urls=(https://download.docker.com/ https://registry-1.docker.io/v2/)
if $with_cloudflare; then
  hosts+=(region1.v2.argotunnel.com region2.v2.argotunnel.com)
fi
if $with_resend; then
  hosts+=(api.resend.com)
  urls+=(https://api.resend.com/)
fi
for host in "${hosts[@]}"; do
  if getent hosts "$host" >/dev/null 2>&1; then
    printf 'DNS %s=resolved\n' "$host"
  else
    printf 'UNVERIFIED: DNS %s\n' "$host"
  fi
done
for url in "${urls[@]}"; do
  if command -v curl >/dev/null 2>&1; then
    code=$(curl -s -o /dev/null --max-time 8 -w '%{http_code}' "$url")
    result=$?
    printf 'HTTPS %s status=%s transport_exit=%s\n' "$url" "$code" "$result"
  fi
done
echo 'INFO: HTTPS does not verify QQ login, cloud firewall, or user delivery.'
$with_cloudflare && echo 'INFO: selected Tunnel still requires outbound TCP/UDP 7844 verification.'
echo 'INFO: collection complete; review UNVERIFIED items before planning.'
exit 0
