# Source provenance

This repository packages the Boba runtime used by ILLIXR PR
[#498](https://github.com/ILLIXR/ILLIXR/pull/498). It is maintained for ILLIXR
integration and is distinct from the upstream standalone Boba demo.

- Runtime, physics, custom gsplat sources, tests, and packaged assets originate
  from [Boba-Demo](https://github.com/jianxiapyh/Boba-Demo) branch
  `Boba-Immersive-Demo-Quest`, commit
  `684d3c2d7fc0cd4c5ba1202748cadf6584d2db01`.
- CUDA 13.2 environment specification, extension builder, architecture selection,
  activation hooks, and their tests originate from
  [Boba-Public](https://github.com/jianxiapyh/Boba-Public) branch `Boba_Batched`,
  commit `612d22a74c2d54e3f20d2c197182090a22a20494`.
- The import includes the compatibility fixes tested with ILLIXR PR #498 through
  commit `f6e6ff162c7c1d2343bd605ad2d7ec0c81c53fe4`: the `boba-cu132` environment,
  CUDA 13 PyCUDA/OpenGL build, shared frame generation invalidation, and staged
  copies for CPU loading images during object switching. These are ordinary
  committed source changes here; installation does not patch another repository.
- Physics, controller motion limiting, the cuSOLVER rotation solver, Rope as the
  default game, and rendering defaults are retained from the tested runtime.

These upstream links record attribution; setup and the default demo do not
download source or assets from either personal repository.

The hand pointer artwork and fingertip anchoring come from Boba's phone demo,
commit `d2590a41fdaa11f9fad4fa42835d9fc8b8b0fbb1` of Boba-Demo. The two original
images and their MIT license are bundled under
[`assets/hand_pointer`](assets/hand_pointer/README.md).

The original copyright notices, Apache 2.0 license, and bundled third-party
licenses are retained. See [NOTICE](NOTICE), [LICENSE](LICENSE), and the license
and provenance files next to each asset or vendored library. Third-party assets
and Gaussian rasterization components retain their own license terms.
