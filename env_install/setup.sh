#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENVIRONMENT=boba-cu132
FETCH_GARDEN=0
REBUILD=0
log() { printf '[Boba-ILLIXR setup] %s\n' "$*"; }
die() { log "error: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --garden) FETCH_GARDEN=1 ;;
        --rebuild) REBUILD=1 ;;
        -h|--help)
            printf '%s\n' 'Usage: env_install/setup.sh [--garden] [--rebuild]' \
                'Create boba-cu132, build the bundled CUDA extensions, and validate assets.' \
                'CONDA_ENVS_PATH selects the environment directory; no system packages are installed.'
            exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
    shift
done

[[ "$(uname -s)" == Linux ]] || die 'Linux with an NVIDIA GPU is required.'
CONDA_BIN="${CONDA_EXE:-$(command -v conda || true)}"
[[ -n "${CONDA_BIN}" && -x "${CONDA_BIN}" ]] || die 'Initialize Conda first.'
command -v python3 >/dev/null || die 'python3 is required for setup.'
nvidia-smi >/dev/null || die 'A working NVIDIA driver is required.'

# Choose the first Conda environment directory, including for an isolated
# installation via CONDA_ENVS_PATH, instead of reusing another registered env.
ENV_ROOT="$("${CONDA_BIN}" info --json | python3 -c \
    'import json, sys; from pathlib import Path; print(Path(json.load(sys.stdin)["envs_dirs"][0]) / "boba-cu132")')"
if [[ ! -f "${ENV_ROOT}/conda-meta/history" ]]; then
    [[ ! -e "${ENV_ROOT}" ]] || die "Incomplete environment at ${ENV_ROOT}; select another CONDA_ENVS_PATH."
    log "Creating ${ENV_ROOT}"
    "${CONDA_BIN}" env create --prefix "${ENV_ROOT}" --file "${REPO_ROOT}/env_install/boba-cu132.yml"
fi

run_boba() {
    env -u CONDA_PREFIX -u CONDA_DEFAULT_ENV -u CONDA_SHLVL -u CUDA_HOME -u LD_LIBRARY_PATH \
        "${CONDA_BIN}" run --no-capture-output --prefix "${ENV_ROOT}" \
        env PYTHONNOUSERSITE=1 BOBA_RUNTIME_ENV="${ENVIRONMENT}" "$@"
}

run_boba python -c 'import sys, torch
assert sys.version_info[:2] == (3, 10), sys.version
assert torch.__version__ == "2.12.1+cu132", torch.__version__
assert torch.version.cuda == "13.2", torch.version.cuda' ||
    die 'The existing environment does not match the pinned Python/Torch/CUDA stack; it has been left in place.'

cd "${REPO_ROOT}"
run_boba python tools/fetch_demo_case_assets.py
run_boba python -m pip install --disable-pip-version-check --no-input -r requirements-demo.txt
run_boba python -m pip check

# Rebuild after source, checkout location, or GPU architecture changes. Hash
# tracked build inputs, including local edits, without hashing compiled output.
BUILD_KEY="$(run_boba python - "${REPO_ROOT}" <<'PY'
import hashlib
from pathlib import Path
import subprocess
import sys
from env_install.cuda_arch import resolve_architectures

root = Path(sys.argv[1]).resolve()
digest = hashlib.sha256(str(root).encode())
digest.update(repr(resolve_architectures()).encode())
names = subprocess.check_output([
    'git', 'ls-files', '-z', 'env_install', 'gaussian_splatting', 'requirements-demo.txt'
]).split(b'\0')
for name in sorted(filter(None, names)):
    digest.update(name + b'\0')
    digest.update((root / name.decode()).read_bytes())
print(digest.hexdigest())
PY
)"
STATE_FILE="${ENV_ROOT}/var/cache/boba-illixr-build"
if [[ ${REBUILD} -eq 0 && -f "${STATE_FILE}" && "$(cat "${STATE_FILE}")" == "${BUILD_KEY}" ]] &&
    run_boba python -c 'import fused_ssim_cuda, pycuda.gl, simple_knn._C; import gaussian_splatting._gsplat_vendor' >/dev/null 2>&1; then
    log 'CUDA extensions are already built and verified.'
else
    log 'Building and verifying the CUDA extensions from this checkout.'
    run_boba bash env_install/build_cuda13_extensions.sh
    mkdir -p "$(dirname -- "${STATE_FILE}")"
    printf '%s\n' "${BUILD_KEY}" > "${STATE_FILE}.tmp"
    mv -f -- "${STATE_FILE}.tmp" "${STATE_FILE}"
fi

run_boba python -c 'import gaussian_splatting._gsplat_vendor'
log 'Checking the full simulation and renderer import path.'
run_boba python -c 'from qqtt import InvPhyTrainerWarp; import pycuda.gl'
if [[ ${FETCH_GARDEN} -eq 1 ]]; then
    run_boba python tools/fetch_demo_case_assets.py --scene garden --fetch
fi
log "Ready: ${REPO_ROOT}/boba_app.sh (${ENV_ROOT})"
