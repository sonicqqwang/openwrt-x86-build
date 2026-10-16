#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="${1:?Usage: prepare.sh BUILD_DIRECTORY}"
source "$repo_dir/sources.env"
[[ "$(id -u)" != 0 ]] || { echo 'Use a non-root build user.' >&2; exit 1; }
[[ ! -e "$build_dir" ]] || { echo 'Build directory already exists.' >&2; exit 1; }

mkdir -p "$build_dir"
cd "$build_dir"
git init
git remote add origin "$LEDE_URL"
git fetch --depth 1 origin "$LEDE_REV"
git checkout --detach FETCH_HEAD
[[ "$(git rev-parse HEAD)" == "$LEDE_REV" ]]
cat > feeds.conf <<EOF
src-git packages ${PACKAGES_URL}^${PACKAGES_REV}
src-git luci ${LUCI_URL}^${LUCI_REV}
src-git helloworld ${HELLOWORLD_URL}^${HELLOWORLD_REV}
EOF
./scripts/feeds update -a
./scripts/feeds install -a
# Prefer the inspected proxy feed over duplicate packages in the base feeds.
./scripts/feeds install -f -p helloworld luci-app-ssr-plus xray-core mihomo
cp "$repo_dir/config/x86_64.config" .config
cp -a "$repo_dir/files" .
chmod 0755 files/etc/uci-defaults/99-local-defaults
make defconfig

required=(TARGET_x86_64 TARGET_x86_64_DEVICE_generic TARGET_ROOTFS_SQUASHFS
  GRUB_EFI_IMAGES PACKAGE_luci PACKAGE_luci-compat PACKAGE_firewall4
  PACKAGE_dnsmasq-full PACKAGE_dnsmasq_full_nftset
  PACKAGE_luci-app-ssr-plus PACKAGE_luci-app-ssr-plus_Nftables_Transparent_Proxy
  PACKAGE_xray-core PACKAGE_mihomo PACKAGE_shadowsocksr-libev-ssr-redir
  PACKAGE_kmod-igb PACKAGE_kmod-e1000e SIGNATURE_CHECK DOWNLOAD_CHECK_CERTIFICATE)
for symbol in "${required[@]}"; do
  grep -qx "CONFIG_${symbol}=y" .config || {
    echo "Required feature was not resolved: CONFIG_${symbol}" >&2
    exit 1
  }
done
for symbol in PACKAGE_default-settings PACKAGE_firewall USE_APK; do
  if grep -qx "CONFIG_${symbol}=y" .config; then
    echo "Unexpected incompatible option: CONFIG_${symbol}" >&2
    exit 1
  fi
done
{
  printf 'lede %s\n' "$(git rev-parse HEAD)"
  for feed in packages luci helloworld; do
    printf '%s %s\n' "$feed" "$(git -C "feeds/$feed" rev-parse HEAD)"
  done
  printf 'config_sha256 '
  sha256sum .config
} > build-sources.txt
./scripts/diffconfig.sh > build-diffconfig.txt
