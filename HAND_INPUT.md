# Quest hand input

The native ILLIXR bridge supports the existing `XR_EXT_hand_interaction` actions.
ILLIXR sends the hand aim and grip poses, and adapts the runtime's pinch value
and readiness into the existing select channel. Hand movement uses the grip
pose, with the same calibration and movement limit as controller interaction.
The simulation and its attachment model are unchanged.

Tracked hands show red left-hand and blue right-hand pointers from the phone
demo, with the decorative arrows removed and no visible laser. Each icon's
index fingertip follows the actual aim target or menu position while the hand
is open. During a grab it follows the exact contact marker, keeping the icon
and grabbed point together even during large movements. Pinching or hovering a
menu button adds a white fingertip indicator; releasing leaves the pointer
visible. Pinch readiness controls selection without hiding valid
hand poses. ILLIXR checks each hand's joint tracker and tracked wrist at the
current display time. Losing one hand removes only its pointer and releases
only its grab; the other hand continues working. Stale input releases both.

Hand grabs and tutorial navigation use the pinch button state supplied by the
Quest adapter. Weak nonzero pinch values do not start or sustain a grab.
Releasing the pinch, including loss of pinch readiness while the hand remains
tracked, ends the grab after the existing two-frame release confirmation.
No second pinch is required. On release the cursor returns to the aim location;
hovering a marker does not snap it to the attachment or start an interaction.

The first startup slide explains pointing, pinching, moving, releasing, the
Game Select menu, and tracking recovery. Pinch and release once per page.

## Controls

| Action | Hands | Controllers |
| --- | --- | --- |
| Advance tutorial / start when Ready | Pinch, release, then pinch for the next step | Trigger |
| Select an interaction marker | Place the hand icon's fingertip on it | Point the controller ray |
| Grab and move | Hold an index–thumb pinch and move the hand | Hold trigger and move controller |
| Release | Open the pinch | Release trigger |
| Open game selector | Place the fingertip on the upper-right **Game Select** button; pinch when it highlights | Point and trigger, or hold Y/B |
| Choose Rope or Sloth | Point at its button and pinch | Point and trigger, or joystick/X/A then trigger |
| Close selector | Point at **Close** and pinch | Point and trigger, or Y/B |
| Exit demo | Open Game Select, point at **Exit Game**, and pinch | Point and trigger on **Exit Game**, or hold either side grip for 0.75 seconds |

The small Game Select button follows the upper-right of the view, inset toward
the center for easier reach. Opening it
expands the panel leftward and downward from that corner and pauses object
interaction. Move the icon's index fingertip onto a button: its fill turns teal
and a white fingertip dot appears. Pinch and release to click it, then repeat
for Rope, Sloth, Close, or Exit Game. Close dismisses the menu; Exit Game ends
the demo and requests native Quest client shutdown. Overlapping only the body of the hand icon does not
select a button. Release a grabbed object before using that hand for the menu.

Hit testing projects through the displayed hand aim endpoint onto the current
frame's panel. The pointer uses that same panel point in both stereo eyes;
menu targeting does not substitute a differently calibrated hand ray. A pinch
clicks only the button under that hand's fingertip. A menu click stays captured
until release, including after closing the panel or switching objects.
Selecting the current game restarts it.
Exit Game requires a fresh pinch/trigger press and cannot fire from the pinch
held while opening the menu. Ctrl+C in the desktop terminal also stops the demo.

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
client draws this pointing feedback above the menu. The aim ray remains an
internal targeting calculation. Reinstall the matching APK for the per-hand
joint tracking check and restart the desktop for the updated pointer rendering.
If the APK already includes the per-hand joint presence check from ILLIXR
`78ce974`, the pinch-release, cursor alignment, menu, and tutorial changes only require
a desktop restart; another APK installation is unnecessary.

## Verification

Run in the configured `boba-cu132` environment from this repository:

```bash
PYTHONPATH="$PWD" python -m pytest -q test/test_hand_interaction.py test/test_object_selector.py
PYTHONPATH="$PWD" python -m pytest -q test -ra
```

The hand tests cover packet compatibility, grip movement through the existing
grab path, release with nonzero pinch strength or unavailable readiness,
independent left/right loss and spring-remap release, reacquisition, free
hover/release motion, contact alignment during large vertical holds, and
laser suppression in both rendering paths. They also cover transport timeout,
upper-right button geometry, fingertip hit testing across calibration scales and head poses,
same-hand selection, closing while pinching, and input carried across a game
switch. The complete suite also exercises controller behavior and simulation.
GPU-dependent tests require access to CUDA; optional Garden tests require the
separately downloaded Garden assets.

Physical Quest validation still needs a hands-only tutorial, marker grab/move/
release, tracking loss and recovery, menu close, Rope → Sloth → Rope, and switching
between hands and Touch controllers. Check both eyes for button visibility and
alignment with the hand pointer. Hide each hand separately while the other is
still grabbing, then bring it back while still pinching: it must remain released
until an open-hand sample arrives. Synthetic input does not validate Quest gesture
recognition or headset comfort.
