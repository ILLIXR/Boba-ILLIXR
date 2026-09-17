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
)


def _packet(*, hand=True, pressed=False, tracked=True):
    import struct

    flags = 31 if tracked else 7
    eye = Bridge.INPUT_EYE_STRUCT.pack(30, 1344, 1344, 0, 1.6, 0, 0, 0, 0, 1, -0.8, 0.8, 0.8, -0.8)
    grip = Bridge.INPUT_POSE_STRUCT.pack(flags, 0.1, 1.1, -0.3, 0, 0, 0, 1)
    aim = Bridge.INPUT_POSE_STRUCT.pack(flags, 0.2, 1.2, -0.4, 0, 0, 0, 1)
    trigger = Bridge.INPUT_BUTTON_STRUCT.pack(3 if pressed else 1, float(pressed))
    neutral = Bridge.INPUT_BUTTON_STRUCT.pack(0, 0)
    controller = (struct.pack("<II", 1, 7 if hand else 2) + grip + aim + trigger + neutral * 4
                  + Bridge.INPUT_AXIS_STRUCT.pack(0, 0, 0))
    return (Bridge.INPUT_HEADER_STRUCT.pack(Bridge.INPUT_MAGIC, 1, Bridge.INPUT_PACKET_BYTE_COUNT, 12, 1234)
            + eye * 2 + controller * 2)


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


def test_stale_hand_input_releases_without_mutating_latest_view(monkeypatch):
    bridge = _gate()
    bridge._latest_lock = threading.Lock()
    bridge._latest_sample = replace(_sample(pressed=True), received_monotonic_s=1.0)
    monkeypatch.setattr("qqtt.illixr_bridge.time.monotonic", lambda: 1.5)
    sample = bridge.get_latest_sample()
    assert not sample.left.active and not sample.left.select_pressed
    assert sample.left_eye is bridge._latest_sample.left_eye
    assert bridge._latest_sample.left.select_pressed


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
    assert selector_target_from_ray(pose[:3, 3], pose[:3, 2], corners, is_open=is_open) is None


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
