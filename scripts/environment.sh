#!/usr/bin/env bash
# Source this file from the repository root before running training/rendering CLIs.
source .venv/bin/activate
export CUDA_HOME=/usr/local/cuda
export PATH="$CUDA_HOME/bin:$PATH"
export TORCH_CUDA_ARCH_LIST=12.0
export MAX_JOBS=4
export QT_QPA_PLATFORM=offscreen
# Compatibility for loading only this project's own Nerfstudio checkpoints.
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1
