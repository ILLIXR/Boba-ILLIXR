# Boba-ILLIXR: Quest 3 operator guide

Build and run Boba through the **native ILLIXR Quest app**. The Quest supplies
headset/controller tracking, the Ubuntu PC simulates and renders Boba, and
ILLIXR streams stereo video back over the local network. This workflow uses
ILLIXR directly and does not require ALVR or SteamVR.

Already built and installed? Jump to [Start a demo session](#4-start-a-demo-session).
For the same instructions with copy buttons, open the
[offline HTML guide](IMMERSIVE_DEMO_OPERATOR_GUIDE.html), or run
`./open_operator_guide.sh` from Boba-ILLIXR.
For hands-only controls and the floating Game Select menu, use the paired
ILLIXR hand-input branch and follow [Quest hand input](HAND_INPUT.md).

## 1. Prepare the computer and repositories

Use an Ubuntu x86-64 computer with a working NVIDIA driver and a local X11/OpenGL
desktop session. The tested machine uses an RTX 5090; the current ILLIXR Boba
streaming build targets CUDA architecture 120 (Blackwell). Have a Quest 3, both
controllers, and a USB **data** cable available.

Install these prerequisites before continuing:

| Component | Requirement |
| --- | --- |
| Source and environments | Git, Git LFS, and initialized Conda |
| Desktop GPU build | CUDA 12.8 in the tested ILLIXR configuration; NVIDIA Video Codec SDK headers, or an `nv-codec-headers` installation |
| Android build on the PC | JDK 17, Android SDK command-line tools, `tar`, and `unzip` |
| Network | PC and Quest on the same LAN, with peer-to-peer traffic allowed; Ethernet for the PC is preferable |

Follow [ILLIXR's dependency guide](https://illixr.github.io/ILLIXR/getting_started/)
for system prerequisites. Boba setup installs its separate Python/CUDA 13.2
environment; that environment does not replace the desktop ILLIXR build tools.

In a directory where you want the two repositories, run:

```bash
git clone --branch boba-immersive-integration https://github.com/ILLIXR/ILLIXR.git
cd ILLIXR
./scripts/setup_boba_immersive.sh --install-root ..
```

The installer downloads the pinned public Boba-ILLIXR source and Git LFS assets,
creates `boba-cu132`, builds its CUDA extensions, and checks the runtime and
assets. GitHub credentials are unnecessary. The first setup downloads several
gigabytes; Conda can display `Installing pip dependencies: ...working...` for
an extended period while buffering the download output.

The resulting layout is:

```text
workspace/
  ILLIXR/       # desktop integration, profiles, and Quest app
  Boba-ILLIXR/  # simulation, renderer, games, assets, and environment setup
```

If you already have both checkouts, run
`./scripts/setup_boba_immersive.sh --source-dir ../Boba-ILLIXR` from ILLIXR to
configure the existing companion without changing its revision or local edits.

All remaining build and launch commands run from **ILLIXR/**. Replace paths,
`QUEST_SERIAL`, and `QUEST_WIFI_IP` with values for your computer and headset.

## 2. Build the desktop ILLIXR server

Create the ILLIXR build environment once. Skip creation if it already exists.
The additional `protobuf` package supplies the host `protoc` executable needed
by the Android build helper.

```bash
conda env create -f environment.yml
conda install -n illixr -c conda-forge protobuf
conda activate illixr
protoc --version
```

With that environment active, configure and build the native Boba profile.
Replace the CUDA and Video Codec SDK paths with your installations:

```bash
cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PWD/install" \
  -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" \
  -DYAML_FILE=profiles/boba_quest_native_server.yaml \
  -DBUILD_DOCS=OFF -DBUILD_DEP_MAP=OFF \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DVIDEO_CODEC_SDK_PATH=/path/to/nvidia-video-codec-sdk
cmake --build build --parallel 8
cmake --install build
```

For `nv-codec-headers`, set `VIDEO_CODEC_SDK_PATH` to the prefix containing
`include/ffnvcodec/nvEncodeAPI.h`. The installed executable is
`./install/bin/main.opt.exe`. Use this native Boba profile when building so its
frame format matches the Boba-enabled Quest APK below.

## 3. Build and install the Quest 3 app

The APK is built **on the Ubuntu PC**, then installed on the Quest through USB.

### Prepare the Android tools

Install Android Studio's SDK tools or the
[Android command-line tools](https://developer.android.com/tools/sdkmanager).
Set the SDK and JDK paths in this terminal. The example assumes the command-line
tools are under `cmdline-tools/latest`; adjust that path if needed.

```bash
export JAVA_HOME="/path/to/jdk-17"
export ANDROID_HOME="$HOME/Android/Sdk"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"

sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-33" "build-tools;35.0.0" \
  "ndk;27.2.12479018" "cmake;3.22.1"
```

Review the SDK license prompts. These package versions match this ILLIXR branch;
Android Studio's SDK Manager can also install them.

### Prepare the headset and signing key

1. Enable developer mode using [Meta's device setup instructions](https://developers.meta.com/horizon/documentation/native/android/mobile-device-setup/).
2. Connect the Quest directly to the PC by USB, put it on, and allow USB debugging.
3. Check that ADB recognizes it:

```bash
adb devices
```

Expected output includes a line like:

```text
QUEST_SERIAL    device
```

The first column is your headset's serial number. If the status is
`unauthorized`, accept the debugging prompt in the headset and check again.

On a new developer machine, create your own signing key once. Reuse an existing
`$HOME/illixr.keystore` for updates; the following command leaves it in place:

```bash
if [ ! -e "$HOME/illixr.keystore" ]; then
  keytool -genkeypair -keystore "$HOME/illixr.keystore" \
    -alias illixr -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass illixr -keypass illixr
  chmod 600 "$HOME/illixr.keystore"
fi
```

Enter your certificate details when prompted. The alias and passwords match
ILLIXR's existing local research-build configuration. Keep the keystore outside
the source repositories.

### Build and install the Release APK

From ILLIXR, with the Android paths above set and the headset authorized, run:

```bash
conda activate illixr
./scripts/install_quest_app.sh --boba --release --no-launch --serial QUEST_SERIAL
```

This prepares ILLIXR's Android dependency submodule, builds
`app/build/outputs/apk/release/app-release.apk`, installs **ILLIXRApp**, and prints
the Quest's Wi-Fi IP address. Save that address for `--quest-ip` in the next
step. Use the Boba-enabled Release build for performance testing.

To reinstall that same APK later without rebuilding:

```bash
./scripts/install_quest_app.sh --boba --release --no-build --no-launch --serial QUEST_SERIAL
```

The helper also accepts `--android-sdk PATH` and `--java-home PATH` when tools
are not found automatically. Installation updates the existing app in place.
If Android reports a signing-key mismatch, use the original key; removing the
old app is a separate manual choice that deletes its app data.

## 4. Start a demo session

1. Put the PC and Quest on the same local network. Use the Quest's current Wi-Fi
   address, which can change after reconnecting. While USB is connected,
   `adb -s QUEST_SERIAL shell ip route` shows it after `src` on the Wi-Fi route.
2. Put on the Quest, keep it awake, and look naturally forward. Open **ILLIXRApp**
   from the headset's sideloaded apps list before starting the desktop process.
3. In a local desktop terminal, run the following from your ILLIXR checkout:

```bash
cd /path/to/ILLIXR
conda activate illixr
export BOBA_IMMERSIVE_ROOT="$(realpath ../Boba-ILLIXR)"
export LD_LIBRARY_PATH="$PWD/install/lib:$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
unset BOBA_DEMO_LAUNCHER

./install/bin/main.opt.exe \
  --yaml=profiles/boba_quest_native_server.yaml \
  --duration=600 \
  --quest-ip QUEST_WIFI_IP \
  2>&1 | tee boba-desktop.log
```

ILLIXR starts Boba automatically. Clearing `BOBA_DEMO_LAUNCHER` selects the
default **Rope in the Lab**. The command allows ten minutes of testing; press
Ctrl+C to stop earlier. Without `--duration`, ILLIXR defaults to 60 seconds and
then closes the desktop demo and Quest app. Reopen ILLIXRApp before each run.

If you cannot find the installed app in the headset menu, launch it over USB:

```bash
adb -s QUEST_SERIAL shell am start \
  -n com.example.native_activity/com.example.ILLIXR.ILLIXRNativeActivity
```

USB can be disconnected after installation. Tracking and video use the local
network. Allow the PC to receive TCP **9001** and UDP **9003**, and the Quest to
receive the startup handshake on UDP **9010**. Guest Wi-Fi/client isolation can
prevent the two devices from reaching each other.

The native profile hides the desktop spectator view to reduce rendering work.
If needed, run `export BOBA_DESKTOP_PREVIEW=true` before launching; use
`unset BOBA_DESKTOP_PREVIEW` to return to the default. A valid X11 `DISPLAY` is
still needed by Boba even with the spectator hidden.

## 5. Operate and stop the demo

Press a trigger to advance each tutorial page. On the final page, wait for
**Ready**, release the trigger, and press it again. Confirm that Rope appears,
head movement updates the view, and both controller rays track correctly.

| Control | Action |
| --- | --- |
| Trigger | Advance the tutorial; hold to grab, release to drop |
| Point at a marker | Select an interaction point |
| X or A | Cycle interaction points |
| Y or B, short press | Restart the Rope course or reset the current object |
| Y or B, hold | Open the Rope/Sloth selector |
| Joystick up/down in selector | Change the highlighted object; recenter between moves |
| Trigger in selector | Confirm the selection |
| Y or B in selector | Cancel the selection |
| Grip, hold | Exit the demo |

Wait for the loading overlay when switching Rope → Sloth → Rope. For a new
wearer, reset the current object with Y or B. If the view is misaligned, stop
and relaunch while the wearer is upright and looking forward.

Stop with **Ctrl+C** in the desktop terminal, or hold a controller grip. After
an in-headset exit, stop any remaining desktop session with Ctrl+C before
starting another run.

## 6. Troubleshooting and logs

| Symptom | Check |
| --- | --- |
| ADB shows no device or `unauthorized` | Check the USB data cable, developer mode, and the debugging prompt inside the Quest. |
| Setup cannot find Conda or `boba-cu132` | Initialize Conda and rerun `setup_boba_immersive.sh`; use the same `CONDA_ENVS_PATH` for setup and launch if you customized it. |
| App build cannot find `protoc`, SDK, or JDK | Activate `illixr`, run `protoc --version`, and check the Android tool paths and package versions from step 3. |
| Desktop waits for the Quest | Reopen ILLIXRApp, keep the headset awake, check its current IP, and verify local network/firewall connectivity. |
| Demo closes after about a minute | Include `--duration=600` in the desktop command. |
| View stutters | Confirm the APK was built with `--boba --release`, keep the spectator view disabled, and compare desktop and Quest logs. |
| Tutorial or object switch appears paused | Wait for the loading progress; check the desktop log for errors. If it stops progressing, stop, reopen ILLIXRApp, and relaunch. |
| OpenGL or `DISPLAY` error | Launch from the PC's X11 desktop session with access to the NVIDIA GPU. |

For diagnosis, leave USB connected and capture the Quest log in another
terminal with the Android tools on its `PATH`:

```bash
adb -s QUEST_SERIAL logcat -T 1 -v threadtime > quest-boba.log
```

The launch command already saves `boba-desktop.log`. Compare desktop
`Boba native stream` FPS/encode/send times with Quest `Boba receiver` and
`Decoder FPS` messages. Stop log capture with Ctrl+C. See the
[ILLIXR Boba integration guide](https://github.com/ILLIXR/ILLIXR/blob/boba-immersive-integration/docs/docs/plugin_README/README_boba.md)
for protocol settings and development checks.
