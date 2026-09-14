# Boba-ILLIXR

Boba-ILLIXR contains the Boba physics and rendering runtime for
[ILLIXR PR #498](https://github.com/ILLIXR/ILLIXR/pull/498). Together, the two
repositories contain the Boba source, game assets, setup scripts, desktop
integration, and native Quest 3 application needed to run the demo.

| Repository | Contents |
| --- | --- |
| [ILLIXR/ILLIXR](https://github.com/ILLIXR/ILLIXR) | Boba plugins, tracking and video transport, desktop profiles, and Quest APK source/build tools |
| [ILLIXR/Boba-ILLIXR](https://github.com/ILLIXR/Boba-ILLIXR) (this repository) | Simulation, custom gsplat and cuSOLVER code, immersive game logic, Rope/Sloth and Lab/Ambulance assets, and CUDA environment setup |

The `main` branch is the ILLIXR companion runtime. It incorporates the tested
Boba-Batched runtime and immersive demo; a separate Boba-Public or Boba-Demo
checkout is unnecessary. See [PROVENANCE.md](PROVENANCE.md) for upstream
revisions and integration changes.

## Setup with ILLIXR

Use Ubuntu x86-64 with a working NVIDIA driver, an OpenGL/X11 session (`DISPLAY`
set), Conda, Git, and Git LFS. Setup installs Python 3.10, PyTorch 2.12.1 with
CUDA 13.2, and builds the bundled CUDA extensions for the visible GPU. ILLIXR
and Android SDK/NDK build prerequisites remain separate; follow the
[ILLIXR Boba guide](https://github.com/ILLIXR/ILLIXR/blob/boba-immersive-integration/docs/docs/plugin_README/README_boba.md).

This repository is public. HTTPS downloads, including Git LFS assets, do not
require a GitHub account, SSH key, or access token. Git LFS must be installed.

For a pinned installation, clone ILLIXR and let its installer create the sibling
Boba-ILLIXR checkout:

```bash
git clone --branch boba-immersive-integration https://github.com/ILLIXR/ILLIXR.git
cd ILLIXR
./scripts/setup_boba_immersive.sh --install-root ..
export BOBA_IMMERSIVE_ROOT="$(realpath ../Boba-ILLIXR)"
```

The installer uses public HTTPS by default and Git LFS to download Sloth from
the same organization repository. If you prefer authenticated SSH, pass
`--repository git@github.com:ILLIXR/Boba-ILLIXR.git`.

If you have already cloned both repositories side by side:

```bash
cd Boba-ILLIXR
git lfs install --local
git lfs pull
cd ../ILLIXR
./scripts/setup_boba_immersive.sh --source-dir ../Boba-ILLIXR
export BOBA_IMMERSIVE_ROOT="$(realpath ../Boba-ILLIXR)"
```

`--source-dir` uses that checkout as it is and reports if it differs from the
version pinned by ILLIXR. Normal setup pins the tested revision. Setup can be
rerun; a mismatched existing Python/Torch environment is left in place with an
error. Set `CONDA_ENVS_PATH` to another directory for an isolated installation.

## Run on Quest 3

Build ILLIXR with `profiles/boba_quest_native_server.yaml`, then install its
Release APK using `./scripts/install_quest_app.sh --boba`. The ILLIXR guide
covers first-time USB debugging, signing-key setup, and ADB device selection.
Put the desktop and Quest on the same LAN, open ILLIXRApp on the headset, and
run from the ILLIXR checkout:

```bash
export BOBA_IMMERSIVE_ROOT="$(realpath ../Boba-ILLIXR)"
unset BOBA_DEMO_LAUNCHER
./install/bin/main.opt.exe \
  --yaml=profiles/boba_quest_native_server.yaml \
  --duration=600 \
  --quest-ip QUEST_WIFI_IP
```

Adjust the executable path to your ILLIXR build directory. This runs for ten
minutes; Ctrl+C stops earlier. USB can be disconnected after APK installation.
The native path uses the ILLIXR Quest app and does not require SteamVR or ALVR.

Rope in the Lab is the default. Hold Y or B to open the object selector and
switch between Rope and Sloth. The runtime uses one simulation instance
(`--n_dup 0`), 1344-pixel source eyes, stereo batched rendering, and at most
5 cm of controller-target motion per rendered simulation period. Excess motion
continues toward the newest pose across subsequent frames. The native profile
hides the desktop spectator view by default; `BOBA_DESKTOP_PREVIEW=true` enables
it.

The Lab, Ambulance, Rope, and Sloth assets are packaged here. Garden remains an
optional external scene (roughly 13.6 GB of upstream downloads), outside the
default two-repository demo. Request it with the installer's `--garden` flag;
see [its asset license](assets/scenes/garden/ASSET_LICENSE.md).

## Runtime development and checks

The ILLIXR plugin launches `boba_app.sh` and exchanges poses, frames, and UI
metadata through local IPC. Run the whole native session through ILLIXR; starting
`boba_app.sh` alone selects the retained standalone desktop OpenXR path.
The older [operator guide](IMMERSIVE_DEMO_OPERATOR_GUIDE.md) describes that
ALVR/SteamVR path.

```bash
./env_install/setup.sh                 # environment, extensions, asset validation
./env_install/setup.sh --rebuild       # force CUDA extension rebuild
conda run -n boba-cu132 python tools/fetch_demo_case_assets.py
conda run -n boba-cu132 python -m unittest discover -s test -p 'test_cuda*.py'
```

Additional tests use pytest (an optional development dependency). The ILLIXR
Boba guide includes the CPU/GPU frame-switching and NVENC regression checks.
See [LICENSE](LICENSE), [NOTICE](NOTICE), and [PROVENANCE.md](PROVENANCE.md)
for licenses and attribution.
