# Boba-ILLIXR

Boba's physics and rendering runtime for the native ILLIXR Quest 3 demo.
The `main` branch combines the Boba-Batched engine with the immersive games
used by [ILLIXR PR #498](https://github.com/ILLIXR/ILLIXR/pull/498).

| Repository | Provides |
| --- | --- |
| **Boba-ILLIXR** | Simulation, rendering, game assets, and CUDA environment setup |
| [**ILLIXR**](https://github.com/ILLIXR/ILLIXR/tree/boba-immersive-integration) | Plugins, tracking/video transport, desktop profiles, and Quest app |

**Start with the [operator guide](IMMERSIVE_DEMO_OPERATOR_GUIDE.md)** for
prerequisites, building ILLIXR and the Quest APK, installation, and launching
Rope over Wi-Fi. The [HTML guide](IMMERSIVE_DEMO_OPERATOR_GUIDE.html) provides
the same steps with copy buttons and works offline; open it with
`./open_operator_guide.sh`.

Both repositories are public, and setup uses HTTPS with Git LFS. These two
checkouts provide the default demo; no separate Boba-Public or Boba-Demo checkout
is needed. The runtime starts with Rope in the Lab and supports switching to
Sloth. Garden is an optional external download.

See [PROVENANCE.md](PROVENANCE.md), [LICENSE](LICENSE), and [NOTICE](NOTICE)
for upstream revisions and licensing.
