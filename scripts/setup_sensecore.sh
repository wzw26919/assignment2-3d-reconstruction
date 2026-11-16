#!/usr/bin/env bash
set -euo pipefail
# Run only inside the dedicated assignment environment. Shared dataset is read-only.
cd "$(dirname "$0")/.."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends blender colmap ffmpeg python3-venv libgl1 libglib2.0-0 ninja-build
bash scripts/install_training.sh
