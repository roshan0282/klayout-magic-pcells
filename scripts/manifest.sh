#!/bin/sh
# Rebuild the shipped manifests from the Magic and PDKs in the pinned image:
#   scripts/manifest.sh                     rewrite python/klayout_magic_pcells/data/manifest-<pdk>.json for every PDK
#   scripts/manifest.sh --check             exit 1 if a committed manifest differs from Magic
#   scripts/manifest.sh --pdk gf180mcuD     one PDK
case " $* " in
  *" --pdk "*|*" --pdk="*) ;;
  *) set -- --all "$@" ;;
esac
exec "$(dirname "$0")/in_image.sh" 'python3 tools/build_manifest.py "$@"' "$@"
