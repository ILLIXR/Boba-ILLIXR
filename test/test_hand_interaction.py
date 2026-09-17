from dataclasses import replace
import threading

import numpy as np
import pytest

from qqtt.illixr_bridge import ILLIXRImmersiveBridge as Bridge
from qqtt.live_openxr import controller_pose_position, controller_pose_forward
from qqtt.object_selector import (
    RuntimeObjectSelector,
    selector_button_rects,
    selector_panel_world_corners,
    selector_target_from_ray,
    selector_point_from_ray,
)


def _packet(*, hand=True, pressed=False, tracked=True, ready=True, missing=None, value=None):
    import struct

    flags = 31 if tracked else 7
    eye = Bridge.INPUT_EYE_STRUCT.pack(30, 1344, 1344, 0, 1.6, 0, 0, 0, 0, 1, -0.8, 0.8, 0.8, -0.8)
    grip = Bridge.INPUT_POSE_STRUCT.pack(flags, 0.1, 1.1, -0.3, 0, 0, 0, 1)
    aim = Bridge.INPUT_POSE_STRUCT.pack(flags, 0.2, 1.2, -0.4, 0, 0, 0, 1)
    trigger = Bridge.INPUT_BUTTON_STRUCT.pack(
        (3 if pressed else 1) if ready else 0,
        float(pressed if value is None else value) if ready else 0.0)
    neutral = Bridge.INPUT_BUTTON_STRUCT.pack(0, 0)
    controllers = b"".join(
        struct.pack("<II", int(side != missing), 7 if hand else 2)
        + grip + aim + trigger + neutral * 4 + Bridge.INPUT_AXIS_STRUCT.pack(0, 0, 0)
        for side in ("left", "right"))
    return (Bridge.INPUT_HEADER_STRUCT.pack(Bridge.INPUT_MAGIC, 1, Bridge.INPUT_PACKET_BYTE_COUNT, 12, 1234)
            + eye * 2 + controllers)


def _sample(**kwargs):
    return Bridge._parse_input_packet(_packet(**kwargs))


def _gate():
    bridge = Bridge.__new__(Bridge)
    bridge._hand_select_armed = {"left": False, "right": False}
    bridge._last_input_time = None
    return bridge


def test_hand_packet_uses_existing_select_grip_and_aim_channels():
    sample = _sample(pressed=True)
    assert sample.left.is_hand_tracking
    assert sample.left.select_source == "illixr_pinch"
    assert sample.left.select_pressed
    np.testing.assert_allclose(controller_pose_position(sample.left, "grip"), [0.1, 1.1, -0.3])
    np.testing.assert_allclose(controller_pose_position(sample.left, "aim"), [0.2, 1.2, -0.4])
    np.testing.assert_allclose(controller_pose_forward(sample.left, "aim"), [0, 0, -1])
    controller = _sample(hand=False, pressed=True)
    assert not controller.left.is_hand_tracking
    assert controller.left.select_source == "illixr_trigger"
    assert controller.left.select_pressed


def test_hand_requires_release_on_acquisition_tracking_loss_and_transport_gap():
    gate = _gate()

    def update(t, **kwargs):
        return gate._prepare_hand_input(replace(_sample(**kwargs), received_monotonic_s=t))

    assert not update(1.0, pressed=True).left.select_pressed
    assert not update(1.1).left.select_pressed
    assert update(1.2, pressed=True).left.select_pressed
    lost = update(1.3, pressed=True, tracked=False)
    assert not lost.left.active and not lost.left.select_pressed
    assert not update(1.4, pressed=True).left.select_pressed
    update(1.5)
    assert update(1.6, pressed=True).left.select_pressed
    assert not update(2.0, pressed=True).left.select_pressed
    update(2.1)
    assert update(2.2, pressed=True).left.select_pressed
    assert not update(2.3).left.select_pressed


@pytest.mark.parametrize("source", ["left", "right"])
def test_tracked_hand_stays_visible_when_pinch_is_not_ready(source):
    gate = _gate()

    def update(t, **kwargs):
        return getattr(gate._prepare_hand_input(
            replace(_sample(**kwargs), received_monotonic_s=t)), source)

    # Before any pinch, valid poses must reach the renderer even if the runtime
    # is not ready to recognize a select gesture.
    hand = update(1.0, ready=False)
    assert hand.active and not hand.select_available and not hand.select_pressed
    np.testing.assert_allclose(controller_pose_position(hand, "grip"), [0.1, 1.1, -0.3])
    np.testing.assert_allclose(controller_pose_position(hand, "aim"), [0.2, 1.2, -0.4])
    np.testing.assert_allclose(controller_pose_forward(hand, "aim"), [0, 0, -1])

    # An inactive action's neutral value is not evidence of an open hand. Keep
    # acquisition protection until a ready, released sample actually arrives.
    assert not update(1.1, pressed=True).select_pressed
    assert update(1.2).active
    assert update(1.3, pressed=True).select_pressed
    released = update(1.4, ready=False)
    assert released.active and not released.select_pressed
    assert not update(1.5, pressed=True).select_pressed
    lost = update(1.6, ready=False, tracked=False)
    assert not lost.active and not lost.select_pressed


def test_stale_hand_input_releases_without_mutating_latest_view(monkeypatch):
    bridge = _gate()
    bridge._latest_lock = threading.Lock()
    bridge._latest_sample = replace(_sample(pressed=True), received_monotonic_s=1.0)
    monkeypatch.setattr("qqtt.illixr_bridge.time.monotonic", lambda: 1.5)
    sample = bridge.get_latest_sample()
    assert not sample.left.active and not sample.left.select_pressed
    assert sample.left_eye is bridge._latest_sample.left_eye
    assert bridge._latest_sample.left.select_pressed


@pytest.mark.parametrize("source", ["left", "right"])
@pytest.mark.parametrize("release_ready", [True, False])
def test_pinch_release_ends_attachment_without_another_pinch(monkeypatch, source, release_ready):
    import torch
    from types import SimpleNamespace
    from qqtt.engine import trainer_warp

    monkeypatch.setattr(trainer_warp, "cfg", SimpleNamespace(device="cpu"))
    trainer = trainer_warp.InvPhyTrainerWarp.__new__(trainer_warp.InvPhyTrainerWarp)
    gate = _gate()
    hold_state = {}
    alignment = {"basis": torch.eye(3), "translation_scale": torch.tensor(1.0)}
    for side in ("left", "right"):
        alignment[f"reference_live_{side}"] = torch.zeros(3)
        alignment[f"reference_scene_{side}"] = torch.zeros(3)

    def update(t, **kwargs):
        sample = gate._prepare_hand_input(replace(_sample(**kwargs), received_monotonic_s=t))
        hand = getattr(sample, source)
        return hand, trainer._update_controller_select_hold_state(source, hand, hold_state)

    update(1.0)
    # This value appeared in the headset log with select_pressed=0. It must
    # neither acquire an attachment nor advance a tutorial page.
    weak, weak_state = update(1.1, value=0.296)
    assert not any(weak_state[key] for key in ("start_active", "start_edge", "hold_active"))
    assert not trainer._immersive_controller_select_active(weak)
    pinched, pinched_state = update(1.2, pressed=True)
    assert pinched_state["start_edge"] and pinched_state["hold_active"]
    assert trainer._immersive_controller_select_active(pinched)

    interactions = {"left": None, "right": None}
    interactions[source] = {"translation_only": True, "spring_remap_applied": True,
                            "grab_controller_position_world": torch.zeros(3),
                            "grab_attach_anchor_world": torch.tensor([1., 2., 3.])}
    restored, released = [], []
    monkeypatch.setattr(trainer, "_restore_controller_attachment_remap", lambda side, metadata: restored.append(side))
    monkeypatch.setattr(trainer, "_log_controller_interaction_end", lambda *args: None)
    preview = {"left": {}, "right": {}}
    for frame in range(1, trainer.LIVE_CONTROLLER_SELECT_RELEASE_FRAMES + 1):
        hand, state = update(1.2 + frame * 0.05, value=0.296, ready=release_ready)
        assert hand.active and state["release_ready"] and not state["hold_active"]
        assert state["release_frames"] == frame
        world = trainer._convert_live_controller_to_world(
            source, hand, alignment, position_pose_role="grip", ray_pose_role="aim")
        world.update({f"select_{key}": state[key] for key in
                      ("start_edge", "hold_active", "release_ready", "release_frames")})
        worlds = {"left": None, "right": None, source: world}
        anchors = trainer._resolve_live_controller_interaction_anchors(
            worlds["left"], worlds["right"], {}, interactions, {}, {}, {}, {}, preview, None,
            allow_interaction_start=False, interaction_release_callback=lambda **event: released.append(event))
    assert interactions[source] is None and anchors == (None, None)
    assert restored == [source] and [event["source"] for event in released] == [source]


def test_controller_keeps_analog_trigger_thresholds():
    from qqtt.engine import trainer_warp

    trainer = trainer_warp.InvPhyTrainerWarp.__new__(trainer_warp.InvPhyTrainerWarp)
    partial_trigger = _sample(hand=False, value=0.296).right
    state = {}
    held = trainer._update_controller_select_hold_state("right", partial_trigger, state)
    assert held["start_edge"] and held["hold_active"]
    assert trainer._immersive_controller_select_active(partial_trigger)
    released = trainer._update_controller_select_hold_state("right", _sample(hand=False, value=0.03).right, state)
    assert released["release_ready"] and not released["hold_active"]


@pytest.mark.parametrize("missing", ["left", "right"])
def test_one_missing_hand_releases_its_grab_without_disturbing_the_other(monkeypatch, missing):
    import torch
    from types import SimpleNamespace
    from qqtt.engine import trainer_warp

    monkeypatch.setattr(trainer_warp, "cfg", SimpleNamespace(device="cpu"))
    trainer = trainer_warp.InvPhyTrainerWarp.__new__(trainer_warp.InvPhyTrainerWarp)
    gate = _gate()
    other = "right" if missing == "left" else "left"
    alignment = {"basis": torch.eye(3), "translation_scale": torch.tensor(1.0)}
    interactions = {}
    for side in ("left", "right"):
        alignment[f"reference_live_{side}"] = torch.zeros(3)
        alignment[f"reference_scene_{side}"] = torch.zeros(3)
        interactions[side] = {"translation_only": True, "spring_remap_applied": True,
                              "grab_controller_position_world": torch.zeros(3),
                              "grab_attach_anchor_world": torch.tensor([1., 2., 3.])}

    def update(t, **kwargs):
        return gate._prepare_hand_input(replace(_sample(**kwargs), received_monotonic_s=t))

    update(1.0)
    held = update(1.1, pressed=True)
    assert held.left.select_pressed and held.right.select_pressed
    lost = update(1.2, pressed=True, missing=missing)
    assert not getattr(lost, missing).active and not getattr(lost, missing).select_pressed
    assert getattr(lost, missing).select_value == 0
    assert getattr(lost, other).active and getattr(lost, other).select_pressed
    worlds = {}
    for side in ("left", "right"):
        world = trainer._convert_live_controller_to_world(
            side, getattr(lost, side), alignment, position_pose_role="grip", ray_pose_role="aim")
        if world is not None:
            world["select_hold_active"] = True
        worlds[side] = world
    assert worlds[missing] is None and worlds[other] is not None
    restored, released = [], []
    monkeypatch.setattr(trainer, "_restore_controller_attachment_remap", lambda side, metadata: restored.append(side))
    monkeypatch.setattr(trainer, "_log_controller_interaction_end", lambda *args: None)
    preview = {"left": {}, "right": {}}
    anchors = trainer._resolve_live_controller_interaction_anchors(
        worlds["left"], worlds["right"], {}, interactions, {}, {}, {}, {}, preview, None,
        allow_interaction_start=False, interaction_release_callback=lambda **event: released.append(event))
    assert interactions[missing] is None and interactions[other] is not None
    assert restored == [missing] and [event["source"] for event in released] == [missing]
    assert anchors[0 if missing == "left" else 1] is None
    np.testing.assert_allclose(anchors[0 if other == "left" else 1], [1.1, 3.1, 2.7], atol=1e-6)

    # Reacquiring the absent hand while still pinching cannot start a new grab,
    # and must not disarm the other hand's uninterrupted hold.
    recovered = update(1.3, pressed=True)
    assert getattr(recovered, missing).active and not getattr(recovered, missing).select_pressed
    assert getattr(recovered, other).select_pressed
    update(1.4)
    assert getattr(update(1.5, pressed=True), missing).select_pressed


def _buttons(left=False, right=False, hand=True):
    return {"left": {"select": left, "hand": hand}, "right": {"select": right, "hand": hand}}


def test_hand_can_open_select_and_close_without_controller_buttons():
    selector = RuntimeObjectSelector("rope_game")
    selector.update(0, _buttons())
    opened = selector.update(0.1, _buttons(right=True), pointer_targets={"right": "open"})
    assert opened["opened"] and selector.is_open
    held = selector.update(0.2, _buttons(right=True), pointer_targets={"right": "sloth"})
    assert held["selected_case"] is None
    selector.update(0.3, _buttons())
    closed = selector.update(0.4, _buttons(right=True), pointer_targets={"right": "close"})
    assert closed["cancelled"] and selector.mode == "closed"
    assert closed["consumed_sources"] == ["right"]
    held = selector.update(0.8, _buttons(right=True))
    assert held["consumed_sources"] == ["right"]
    assert selector.update(0.9, _buttons())["consumed_sources"] == []
    selector.update(1.0, _buttons(left=True), pointer_targets={"left": "open"})
    selector.update(1.1, _buttons())
    selected = selector.update(1.2, _buttons(left=True), pointer_targets={"left": "sloth"})
    assert selected["selected_case"] == "sloth" and selector.mode == "loading"


def test_off_panel_pinch_and_other_hands_hover_do_not_select():
    selector = RuntimeObjectSelector("rope_game")
    selector.update(0, _buttons())
    selector.update(0.1, _buttons(left=True), pointer_targets={"left": "open"})
    selector.update(0.2, _buttons())
    for targets in ({}, {"left": "sloth"}):
        event = selector.update(0.3, _buttons(right=True), hovered_index=1, pointer_targets=targets)
        assert event["selected_case"] is None and selector.is_open
        selector.update(0.4, _buttons())


def test_controller_manual_choice_wins_over_its_resting_ray():
    selector = RuntimeObjectSelector("rope_game")
    selector.update(0, _buttons(hand=False))
    selector.update(0.1, _buttons(right=True, hand=False), pointer_targets={"right": "open"})
    selector.update(0.2, _buttons(hand=False))
    buttons = _buttons(hand=False)
    buttons["right"]["vertical"] = -1
    selector.update(0.3, buttons, hovered_index=0, pointer_targets={"right": "rope_game"})
    selector.update(0.4, _buttons(hand=False), hovered_index=0, pointer_targets={"right": "rope_game"})
    selected = selector.update(0.5, _buttons(right=True, hand=False),
                               hovered_index=0, pointer_targets={"right": "rope_game"})
    assert selected["selected_case"] == "sloth"


@pytest.mark.parametrize("is_open", [False, True])
def test_visible_button_rects_match_ray_targets_after_head_motion(is_open):
    pose = np.eye(4, dtype=np.float32)
    pose[:3, :3] = [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]
    pose[:3, 3] = [1.2, 1.6, -0.2]
    corners = selector_panel_world_corners(pose, is_open=is_open)
    for target, (left, top, right, bottom) in selector_button_rects(is_open).items():
        center = corners[0] + (corners[1] - corners[0]) * ((left + right) / 2)
        center += (corners[3] - corners[0]) * ((top + bottom) / 2)
        assert selector_target_from_ray(pose[:3, 3], center - pose[:3, 3], corners, is_open=is_open) == target
        np.testing.assert_allclose(
            selector_point_from_ray(pose[:3, 3], center - pose[:3, 3], corners), center, atol=1e-6)
    assert selector_target_from_ray(pose[:3, 3], pose[:3, 2], corners, is_open=is_open) is None
    assert selector_point_from_ray(pose[:3, 3], pose[:3, 2], corners) is None


@pytest.mark.parametrize("backend", ["native", "desktop"])
def test_open_hand_icons_move_in_both_eyes_without_a_pinch(monkeypatch, backend):
    import torch
    from types import SimpleNamespace
    from qqtt.engine import trainer_warp
    from qqtt.hand_pointer import hand_pointer_strokes
    from qqtt.quest_display import OpenXRImmersiveBridge

    monkeypatch.setattr(trainer_warp, "cfg", SimpleNamespace(device="cpu"))
    trainer = trainer_warp.InvPhyTrainerWarp.__new__(trainer_warp.InvPhyTrainerWarp)
    alignment = {"basis": torch.diag(torch.tensor([1.0, 1.0, -1.0])),
                 "translation_scale": torch.tensor(1.0)}
    eyes = {}
    for source, offset in (("left", -0.032), ("right", 0.032)):
        alignment[f"reference_live_{source}"] = torch.tensor([0.1, 1.1, -0.3])
        alignment[f"reference_scene_{source}"] = torch.tensor([offset * 5, 0.0, 1.0])
        w2c = np.eye(4, dtype=np.float32)
        w2c[0, 3] = -offset
        eyes[source] = {"w2c_cv_np": w2c,
                        "intrinsic_np": np.array([[180, 0, 160], [0, 180, 120], [0, 0, 1]], dtype=np.float32)}
        eyes[source]["w2c_cv_t"] = torch.from_numpy(w2c)
        eyes[source]["intrinsic_t"] = torch.from_numpy(eyes[source]["intrinsic_np"])

    def render(sample, feedback=None):
        overlays = []
        for source in ("left", "right"):
            world = trainer._convert_live_controller_to_world(
                source, getattr(sample, source), alignment,
                position_pose_role="grip", ray_pose_role="aim")
            if world is None:
                continue
            preview = {"origin_world": world["ray_origin"], "direction_world": world["ray_direction"],
                       "hit_world": None, "ray_end_world": world["ray_origin"] + 0.65 * world["ray_direction"]}
            overlay = trainer._build_live_controller_world_overlay(
                source, world, None, None, None, preview_context=preview)
            marker = torch.tensor([0.6, 0.1, 1.3])
            if feedback == "hover":
                overlay.update(attach_candidate=True, attach_candidate_world=marker)
            elif feedback == "held":
                overlay.update(attachment_active=True, active_contact_only=True,
                               active_overlay_world=marker, active_overlay_fallback_world=marker,
                               ray_end_world=marker)
            overlays.append(overlay)
        if backend == "native":
            return trainer._build_live_controller_viewer_overlay_commands_from_world_batched(
                overlays, eyes, 240, 320)
        projected = trainer._project_live_controller_world_overlays_batched(overlays, eyes, 240, 320)
        result = {}
        for eye, entries in projected.items():
            commands = []
            monkeypatch.setattr(trainer, "_draw_marker_line", lambda frame, start, end, color, **style:
                trainer._append_viewer_overlay_line_command(commands, start, end, color, **style))
            monkeypatch.setattr(trainer, "_blend_marker", lambda frame, pixel, color, **style:
                trainer._append_viewer_overlay_marker_command(commands, pixel, color, **style))
            trainer._draw_live_controller_overlay(torch.zeros((240, 320, 3)), entries)
            result[eye] = commands
        return result

    sample = _gate()._prepare_hand_input(replace(_sample(ready=False), received_monotonic_s=1.0))
    idle = render(sample)
    ready = render(_gate()._prepare_hand_input(replace(_sample(), received_monotonic_s=1.0)))
    # With no hovered or held object, hand mode draws only the hand artwork:
    # no laser, origin dot, or controller readiness indicator, even when ready.
    hand_colors = {hand_pointer_strokes(side)[0] for side in ("left", "right")}
    for rendered in (idle, ready):
        assert all(tuple(c[7:10]) in hand_colors for commands in rendered.values() for c in commands)
    moved = replace(sample, **{source: replace(getattr(sample, source),
        grip_position=getattr(sample, source).grip_position + [0.08, 0, 0],
        aim_position=getattr(sample, source).aim_position + [0.08, 0, 0])
        for source in ("left", "right")})
    moving = render(moved)
    centers = {}
    for eye in eyes:
        assert len(idle[eye]) < OpenXRImmersiveBridge.OVERLAY_MAX_COMMANDS_PER_EYE
        for source in ("left", "right"):
            color, strokes = hand_pointer_strokes(source)
            icon = np.array([c for c in idle[eye] if tuple(c[7:10]) == color])
            moved_icon = np.array([c for c in moving[eye] if tuple(c[7:10]) == color])
            assert len(icon) == len(strokes) > 0
            np.testing.assert_allclose(moved_icon[:, 1] - icon[:, 1], 180 * 0.08 / 1.75, atol=1e-4)
            centers[eye, source] = icon[:, 1].mean()
    for source in ("left", "right"):
        assert centers["left", source] > centers["right", source]
    # Hovering or grabbing can move the attachment marker, but the hand cursor
    # must continue to follow the same aim trajectory in both renderers/eyes.
    for feedback in ("hover", "held"):
        with_marker = render(moved, feedback=feedback)
        for eye in eyes:
            for source in ("left", "right"):
                color = hand_pointer_strokes(source)[0]
                actual = np.array([c for c in with_marker[eye] if tuple(c[7:10]) == color])
                expected = np.array([c for c in moving[eye] if tuple(c[7:10]) == color])
                np.testing.assert_allclose(actual, expected, atol=1e-4)
    lost = replace(sample, left=replace(sample.left, active=False), right=replace(sample.right, active=False))
    assert render(lost) == {"left": [], "right": []}
    for missing in ("left", "right"):
        one_hand = _gate()._prepare_hand_input(replace(_sample(missing=missing), received_monotonic_s=1.0))
        other = "right" if missing == "left" else "left"
        for commands in render(one_hand).values():
            assert len(commands) == len(hand_pointer_strokes(other)[1])
            assert all(tuple(c[7:10]) == hand_pointer_strokes(other)[0] for c in commands)
    controller = render(_sample(hand=False))
    for commands in controller.values():
        assert sum(c[0] == 0 for c in commands) == 2  # Touch retains both laser rays.
        assert len(commands) < len(idle["left"])
        assert not any(tuple(c[7:10]) == hand_pointer_strokes(side)[0]
                       for c in commands for side in ("left", "right"))


def test_hand_cursor_uses_aim_or_menu_target_without_attachment_fallback():
    from qqtt.engine import trainer_warp
    trainer = trainer_warp.InvPhyTrainerWarp.__new__(trainer_warp.InvPhyTrainerWarp)
    fields = {"hand_pointer_target_world": (30.0, 50.0),
              "active_overlay_world": (40.0, 70.0),
              "attach_candidate_world": (60.0, 80.0),
              "ray_end_world": (100.0, 110.0)}
    hand = {"is_hand_tracking": True}
    assert trainer._hand_pointer_pixel(hand, fields) == (30.0, 50.0)
    fields.pop("hand_pointer_target_world")
    assert trainer._hand_pointer_pixel(hand, fields) is None
    assert trainer._hand_pointer_pixel({"is_hand_tracking": False}, fields) is None
    # A visible aim/menu target must not require a visible attachment or laser.
    geometry = trainer._resolve_live_controller_projected_overlay_geometry(
        hand, {"hand_pointer_target_world": (30.0, 50.0)}, eye_label="left", height=240, width=320)
    assert geometry is not None


def test_panel_gap_does_not_activate_adjacent_game():
    pose = np.eye(4)
    corners = selector_panel_world_corners(pose, is_open=True)
    gap = corners[0] + 0.5 * (corners[1] - corners[0]) + 0.45 * (corners[3] - corners[0])
    assert selector_target_from_ray([0, 0, 0], gap, corners, is_open=True) is None


def test_new_selector_rejects_pinch_carried_across_game_switch():
    selector = RuntimeObjectSelector("sloth", blocked_until=1)
    assert not selector.update(1.1, _buttons(right=True), pointer_targets={"right": "open"})["opened"]
    assert not selector.update(1.2, _buttons(right=True), pointer_targets={"right": "open"})["opened"]
    selector.update(1.3, _buttons())
    assert selector.update(1.4, _buttons(right=True), pointer_targets={"right": "open"})["opened"]


def test_existing_grab_path_uses_hand_grip_translation_and_pinch_release(monkeypatch):
    import torch
    from qqtt.engine import trainer_warp

    from types import SimpleNamespace
    monkeypatch.setattr(trainer_warp, "cfg", SimpleNamespace(device="cpu"))
    trainer = trainer_warp.InvPhyTrainerWarp.__new__(trainer_warp.InvPhyTrainerWarp)
    alignment = {"basis": torch.eye(3), "translation_scale": torch.tensor(0.25)}
    for side in ("left", "right"):
        alignment[f"reference_live_{side}"] = torch.zeros(3)
        alignment[f"reference_scene_{side}"] = torch.zeros(3)
    hand = _sample(pressed=True).right
    initial = trainer._convert_live_controller_to_world(
        "right", hand, alignment, position_pose_role="grip", ray_pose_role="aim")
    interaction = {"translation_only": True, "grab_controller_position_world": initial["position"],
                   "grab_attach_anchor_world": torch.tensor([1.0, 2.0, 3.0])}
    moved = replace(hand, grip_position=hand.grip_position + [0.08, 0, 0],
                    aim_position=hand.aim_position + [0, 0.2, 0])
    world = trainer._convert_live_controller_to_world(
        "right", moved, alignment, position_pose_role="grip", ray_pose_role="aim")
    np.testing.assert_allclose(trainer._controller_interaction_anchor(world, interaction), [1.02, 2, 3])
    state = {}
    trainer._update_controller_select_hold_state("right", _sample().right, state)
    assert trainer._update_controller_select_hold_state("right", hand, state)["start_edge"]
    assert trainer._update_controller_select_hold_state("right", moved, state)["hold_active"]
    released = trainer._update_controller_select_hold_state("right", _sample().right, state)
    assert released["release_ready"] and not released["hold_active"]
