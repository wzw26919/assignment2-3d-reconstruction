#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
venv_dir="${A2_VENV_DIR:-/opt/assignment2-venv}"
python -m venv --system-site-packages "$venv_dir"
if [ ! -e .venv ]; then ln -s "$venv_dir" .venv; fi
. "$venv_dir/bin/activate"
export CUDA_HOME=/usr/local/cuda
export PATH="$CUDA_HOME/bin:$PATH"
# A standard university PyPI mirror is faster from this SenseCore region.
python -m pip install --no-compile --index-url https://pypi.tuna.tsinghua.edu.cn/simple 'nerfstudio==1.1.5' 'numpy<2' 'tyro==0.8.14' 'wandb==0.16.6'
python -m pip freeze > artifacts/environment_freeze.txt
python -c 'import torch; print(torch.__version__, torch.version.cuda); print(torch.cuda.get_device_name()); print(torch.ones(1, device="cuda"))'
ns-train splatfacto --help > artifacts/ns_train_help.txt
ns-process-data images --help > artifacts/ns_process_help.txt
ns-render interpolate --help > artifacts/ns_render_help.txt
blender --version > artifacts/blender_version.txt
colmap -h > artifacts/colmap_version.txt
touch artifacts/setup_complete
