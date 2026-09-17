# Phone-demo hand pointers

`Picture2.png` (left/red) and `Picture1.png` (right/blue) are unchanged copies
of the hand indicators in the Boba phone demo:

- Repository: https://github.com/jianxiapyh/Boba-Demo
- Source commit: `661e807076f082aa8f2f31ab2a3268b9a503d47f`
- Original paths: `assets/Picture2.png`, `assets/Picture1.png`
- License: [MIT](LICENSE), retained from the source repository.

`qqtt/hand_pointer.py` follows the phone demo's fingertip anchoring and caches
48-pixel scanlines for the existing native overlay transport. The fingertip
marks the ray target or held attachment; the artwork is visible independently
of pinch readiness. The two icons together use fewer than 160 line commands,
within the existing 256-command per-eye limit along with the usual ray and
attachment feedback.
