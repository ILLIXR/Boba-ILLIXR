# Quest hand input

The native ILLIXR bridge supports the existing `XR_EXT_hand_interaction` actions.
ILLIXR sends the hand aim and grip poses, and adapts the runtime's pinch value
and readiness into the existing select channel. Hand movement uses the grip
pose, with the same calibration and movement limit as controller interaction.
The simulation and its attachment model are unchanged.

Tracked hands show the phone demo's red left-hand and blue right-hand pointers
before pinching. Each icon's index fingertip marks the aim target, menu position,
or held attachment. Pinching adds a white fingertip indicator; releasing leaves
the pointer visible. Pinch readiness controls selection without hiding valid
hand poses. Tracking loss or stale input still removes the pointer and releases
the grab.

## Controls

| Action | Hands | Controllers |
| --- | --- | --- |
| Advance tutorial / start when Ready | Pinch, release, then pinch for the next step | Trigger |
| Select an interaction marker | Point the hand aim ray at it | Point the controller ray |
| Grab and move | Hold an index–thumb pinch and move the hand | Hold trigger and move controller |
| Release | Open the pinch | Release trigger |
| Open game selector | Point at the lower-right **Game Select** button and pinch | Point and trigger, or hold Y/B |
| Choose Rope or Sloth | Point at its button and pinch | Point and trigger, or joystick/X/A then trigger |
| Close selector | Point at **Close** and pinch | Point and trigger, or Y/B |

The small Game Select button follows the lower-right of the view. Opening it
shows a larger panel in front of the user and pauses object interaction. A
pinch clicks only the button under that same hand's ray; pinching outside the
panel does nothing. A menu click stays captured until release, including after
closing the panel or switching objects. Selecting the current game restarts it.

Open the hand before the first pinch. Tracking loss or an input gap longer than
250 ms releases hand input; an open-hand sample is required before pinching
again. The controller path retains its existing controls. Swipe gestures are
not required by this implementation.

## Integration

This companion change requires the ILLIXR hand-input PR stacked on
[ILLIXR/ILLIXR#498](https://github.com/ILLIXR/ILLIXR/pull/498). Rebuild the Quest
APK with Boba enabled and use the updated companion checkout on the desktop.
The existing `boba_quest_native_server` profile and launch commands apply.

The input packet remains version 1 with the same size. Interaction profile
value 7 identifies the existing `XR_EXT_hand_interaction` profile. The ordinary
grip/aim/select fields carry hand input; no joint-distance gesture detector or
additional OpenXR session is introduced. The menu uses the existing stereo
bitmap overlay and ILLIXR texture transport.

The hand icons reuse the [phone-demo artwork](assets/hand_pointer/README.md),
cached as line commands in the existing native overlay. The updated ILLIXR
client draws this pointing feedback above the menu. Reinstall the matching APK
to apply that draw order; the visibility fix itself runs in the desktop bridge.

## Verification

Run in the configured `boba-cu132` environment from this repository:

```bash
PYTHONPATH="$PWD" python -m pytest -q test/test_hand_interaction.py test/test_object_selector.py
PYTHONPATH="$PWD" python -m pytest -q test -ra
```

The hand tests cover packet compatibility, grip movement through the existing
grab path, pinch release, reacquisition, transport timeout, button geometry,
same-hand selection, closing while pinching, and input carried across a game
switch. The complete suite also exercises controller behavior and simulation.
GPU-dependent tests require access to CUDA; optional Garden tests require the
separately downloaded Garden assets.

Physical Quest validation still needs a hands-only tutorial, marker grab/move/
release, tracking loss and recovery, menu close, Rope → Sloth → Rope, and switching
between hands and Touch controllers. Check both eyes for button visibility and
alignment with the hand ray. Synthetic input does not validate Quest gesture
recognition or headset comfort.
