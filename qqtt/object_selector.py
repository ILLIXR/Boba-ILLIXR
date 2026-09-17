"""Pure runtime object-selector input and ray-hit logic.

The immersive trainer owns rendering and OpenXR sampling.  Keeping the input
state machine here makes tap-versus-hold and post-switch debouncing testable
without importing CUDA, Warp, or OpenXR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np


OBJECT_SELECTOR_HOLD_SECONDS = 0.75
OBJECT_SELECTOR_DEBOUNCE_SECONDS = 0.30
OBJECT_SELECTOR_STICK_ACTIVATE = 0.55
OBJECT_SELECTOR_STICK_RELEASE = 0.30


@dataclass(frozen=True)
class ObjectChoice:
    case_name: str
    label: str


OBJECT_CHOICES: tuple[ObjectChoice, ...] = (
    ObjectChoice("rope_game", "Rope \u2014 Game"),
    ObjectChoice("sloth", "Sloth \u2014 Free Play"),
)

FREE_PLAY_OBJECT_CHOICES: tuple[ObjectChoice, ...] = (
    ObjectChoice("rope_game", "Rope \u2014 Free Play"),
    ObjectChoice("sloth", "Sloth \u2014 Free Play"),
)

# Retain the public name used by existing tests and callers.
GARDEN_OBJECT_CHOICES = FREE_PLAY_OBJECT_CHOICES


def object_choices_for_scene(scene_name: str = "lab") -> tuple[ObjectChoice, ...]:
    normalized = str(scene_name or "lab").strip().lower()
    if normalized in {"garden", "ambulance"}:
        return FREE_PLAY_OBJECT_CHOICES
    if normalized == "lab":
        return OBJECT_CHOICES
    raise ValueError(f"Unsupported immersive scene: {scene_name}")


def _pressed(source: Mapping[str, object] | None, field: str) -> bool:
    return bool(source is not None and source.get(field, False))


def _axis(source: Mapping[str, object] | None, field: str) -> float:
    if source is None:
        return 0.0
    try:
        value = float(source.get(field, 0.0))
    except (TypeError, ValueError):
        return 0.0
    return value if np.isfinite(value) else 0.0


def _quad_uv_from_ray(
    ray_origin: Sequence[float],
    ray_direction: Sequence[float],
    world_corners: Sequence[Sequence[float]],
) -> tuple[float, float] | None:
    """Intersect a world-space ray with the displayed rectangular panel.

    ``world_corners`` are ordered top-left, top-right, bottom-right,
    bottom-left.  The normalized ``v`` coordinate increases downward.
    """

    origin = np.asarray(ray_origin, dtype=np.float64).reshape(3)
    direction = np.asarray(ray_direction, dtype=np.float64).reshape(3)
    corners = np.asarray(world_corners, dtype=np.float64)
    if corners.shape != (4, 3):
        return None
    if not np.all(np.isfinite(origin)) or not np.all(np.isfinite(direction)):
        return None
    if not np.all(np.isfinite(corners)):
        return None

    right = corners[1] - corners[0]
    down = corners[3] - corners[0]
    right_len_sq = float(np.dot(right, right))
    down_len_sq = float(np.dot(down, down))
    if right_len_sq <= 1.0e-10 or down_len_sq <= 1.0e-10:
        return None
    normal = np.cross(right, down)
    normal_norm = float(np.linalg.norm(normal))
    direction_norm = float(np.linalg.norm(direction))
    if normal_norm <= 1.0e-10 or direction_norm <= 1.0e-10:
        return None

    denom = float(np.dot(direction, normal))
    if abs(denom) <= 1.0e-10:
        return None
    distance = float(np.dot(corners[0] - origin, normal) / denom)
    if distance <= 0.0:
        return None

    hit = origin + direction * distance
    offset = hit - corners[0]
    u = float(np.dot(offset, right) / right_len_sq)
    v = float(np.dot(offset, down) / down_len_sq)
    if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0:
        return None
    return u, v


def selector_row_from_ray(
    ray_origin,
    ray_direction,
    world_corners,
    *,
    row_v_ranges=((0.25, 0.43), (0.43, 0.61)),
) -> int | None:
    uv = _quad_uv_from_ray(ray_origin, ray_direction, world_corners)
    if uv is None:
        return None
    _, v = uv
    for row_index, (v_min, v_max) in enumerate(row_v_ranges):
        if float(v_min) <= v < float(v_max):
            return row_index
    return None


def selector_button_rects(is_open: bool):
    """Shared normalized bounds for drawing and hit testing, including gaps."""
    if not is_open:
        return {"open": (0.03, 0.08, 0.97, 0.92)}
    return {
        "rope_game": (0.06, 0.23, 0.94, 0.43),
        "sloth": (0.06, 0.47, 0.94, 0.67),
        "close": (0.68, 0.76, 0.94, 0.92),
    }


def selector_target_from_ray(ray_origin, ray_direction, world_corners, *, is_open):
    uv = _quad_uv_from_ray(ray_origin, ray_direction, world_corners)
    if uv is not None:
        u, v = uv
        for target, (left, top, right, bottom) in selector_button_rects(is_open).items():
            if left <= u <= right and top <= v <= bottom:
                return target
    return None


def selector_point_from_ray(ray_origin, ray_direction, world_corners):
    """Locate a pointer on the same panel plane used by button hit testing."""
    uv = _quad_uv_from_ray(ray_origin, ray_direction, world_corners)
    if uv is None:
        return None
    corners = np.asarray(world_corners, dtype=np.float32)
    return corners[0] + uv[0] * (corners[1] - corners[0]) + uv[1] * (corners[3] - corners[0])


def selector_panel_world_corners(center_eye_pose_world, *, is_open):
    """Anchor Game Select at the upper-right; expand leftward and downward."""
    pose = np.asarray(center_eye_pose_world, dtype=np.float32)
    if pose.shape != (4, 4) or not np.all(np.isfinite(pose)):
        return None
    width, height = (0.64, 0.40) if is_open else (0.28, 0.081)
    right, up, back = pose[:3, 0], pose[:3, 1], pose[:3, 2]
    top_right = pose[:3, 3] - 0.85 * back + 0.65 * right + 0.50 * up
    center = top_right - width / 2 * right - height / 2 * up
    return np.asarray([
        center - width / 2 * right + height / 2 * up,
        center + width / 2 * right + height / 2 * up,
        center + width / 2 * right - height / 2 * up,
        center - width / 2 * right - height / 2 * up,
    ], dtype=np.float32)


def selector_panel_texture(selector, *, hovered_targets=(), font, title_font, finished_time_s=None):
    """A cached caller can send this texture through the existing modal overlay."""
    from PIL import Image, ImageDraw

    is_open = selector.is_open
    width, height = (640, 400) if is_open else (560, 162)
    image = Image.new("RGBA", (width, height), (17, 24, 35, 242))
    draw = ImageDraw.Draw(image)
    completion = f"Finished in {finished_time_s:.1f}s" if finished_time_s is not None else None
    if is_open:
        draw.text((width / 2, 42), completion or "Game Select",
                  font=title_font, anchor="mm", fill=(245, 248, 255, 255))
    labels = {choice.case_name: choice.label for choice in selector.choices}
    labels.update(open="Game Select", close="Close")
    highlighted = selector.highlighted_case if is_open else None
    for target, rect in selector_button_rects(is_open).items():
        left, top, right, bottom = (rect[0] * width, rect[1] * height, rect[2] * width, rect[3] * height)
        hovered = target in hovered_targets
        color = (42, 124, 150, 255) if hovered else (42, 56, 77, 255)
        outline = (126, 228, 248, 255) if hovered or target == highlighted else (84, 105, 132, 255)
        draw.rounded_rectangle((left, top, right, bottom), radius=14, fill=color, outline=outline, width=3)
        label_y = (top + bottom) / 2
        if target == "open" and completion:
            draw.text((width / 2, label_y - 27), completion, font=font,
                      anchor="mm", fill=(184, 198, 218, 255))
            label_y += 20
        draw.text(((left + right) / 2, label_y), labels[target],
                  font=font if is_open else title_font, anchor="mm", fill=(255, 255, 255, 255))
    if is_open:
        draw.text((40, 334), "Point + pinch / trigger", font=font,
                  anchor="lm", fill=(184, 198, 218, 255))
    return {
        "texture_rgba": np.asarray(image, dtype=np.uint8).copy(),
        "width_px": width,
        "height_px": height,
        "aspect_ratio": height / width,
    }


class RuntimeObjectSelector:
    """Shared selector for hand-ray buttons and controller buttons/sticks."""

    def __init__(
        self,
        active_case: str,
        *,
        hold_seconds: float = OBJECT_SELECTOR_HOLD_SECONDS,
        debounce_seconds: float = OBJECT_SELECTOR_DEBOUNCE_SECONDS,
        blocked_until: float = 0.0,
        scene_name: str = "lab",
    ) -> None:
        self.scene_name = str(scene_name or "lab").strip().lower()
        self.choices = object_choices_for_scene(self.scene_name)
        case_names = tuple(choice.case_name for choice in self.choices)
        if active_case not in case_names:
            raise ValueError(f"Unsupported active object: {active_case}")
        self.active_case = active_case
        self.hold_seconds = float(hold_seconds)
        self.debounce_seconds = float(debounce_seconds)
        self.blocked_until = float(blocked_until)
        self.mode = "closed"
        self.highlighted_index = case_names.index(active_case)
        self.hovered_index: int | None = None
        self._button_cache = {
            source: {"menu": False, "navigate": False, "select": False}
            for source in ("left", "right")
        }
        self._menu_down_since: dict[str, float | None] = {
            "left": None,
            "right": None,
        }
        self._menu_hold_consumed = {"left": False, "right": False}
        self._stick_latched = {"left": False, "right": False}
        self._manual_navigation_active = False
        self._neutral_seen = False
        self._cancel_armed = False
        self._pointer_captured = {"left": False, "right": False}

    @property
    def is_open(self) -> bool:
        return self.mode == "open"

    @property
    def blocks_object_input(self) -> bool:
        return self.mode in {"open", "loading", "error"}

    @property
    def highlighted_case(self) -> str:
        return self.choices[self.highlighted_index].case_name

    def set_loading(self) -> None:
        self.mode = "loading"

    def set_error(self) -> None:
        self.mode = "error"

    def close(self, *, now: float) -> None:
        self.mode = "closed"
        self.hovered_index = None
        self.blocked_until = max(
            float(self.blocked_until),
            float(now) + self.debounce_seconds,
        )
        self._neutral_seen = False
        self._cancel_armed = False
        self._manual_navigation_active = False

    def _all_neutral(self, buttons_by_source: Mapping[str, Mapping[str, object]]) -> bool:
        buttons_neutral = all(
            not _pressed(buttons_by_source.get(source), field)
            for source in ("left", "right")
            for field in ("menu", "navigate", "select")
        )
        sticks_neutral = all(
            abs(_axis(buttons_by_source.get(source), "vertical"))
            <= OBJECT_SELECTOR_STICK_RELEASE
            for source in ("left", "right")
        )
        return buttons_neutral and sticks_neutral

    def update(
        self,
        now: float,
        buttons_by_source: Mapping[str, Mapping[str, object]],
        *,
        hovered_index: int | None = None,
        pointer_targets: Mapping[str, str | None] | None = None,
    ) -> dict[str, object]:
        """Advance the selector and return one-frame semantic events."""

        now = float(now)
        events: dict[str, object] = {
            "opened": False,
            "cancelled": False,
            "reset_requested": False,
            "reset_sources": [],
            "selected_case": None,
            "highlighted_index": self.highlighted_index,
            "consumed_sources": [],
        }
        current = {
            source: {
                field: _pressed(buttons_by_source.get(source), field)
                for field in ("menu", "navigate", "select")
            }
            for source in ("left", "right")
        }
        edges = {
            source: {
                field: current[source][field]
                and not self._button_cache[source][field]
                for field in ("menu", "navigate", "select")
            }
            for source in ("left", "right")
        }
        releases = {
            source: {
                field: not current[source][field]
                and self._button_cache[source][field]
                for field in ("menu", "navigate", "select")
            }
            for source in ("left", "right")
        }
        pointer_targets = pointer_targets or {}
        pointer_action = False
        for source in ("left", "right"):
            if not current[source]["select"]:
                self._pointer_captured[source] = False
            target = pointer_targets.get(source)
            if not (edges[source]["select"] and target is not None):
                continue
            if (self.mode == "open" and self._manual_navigation_active
                    and target in {choice.case_name for choice in self.choices}
                    and not _pressed(buttons_by_source.get(source), "hand")):
                # Preserve trigger confirmation of a joystick/X/A choice even
                # when the resting controller ray points at a different row.
                continue
            self._pointer_captured[source] = True
            if pointer_action or not self._neutral_seen or now < self.blocked_until:
                continue
            if self.mode == "closed" and target == "open":
                self.mode = "open"
                self._manual_navigation_active = False
                self._cancel_armed = False
                events["opened"] = True
                pointer_action = True
            elif self.mode == "open" and target == "close":
                self.close(now=now)
                events["cancelled"] = True
                pointer_action = True
            elif self.mode == "open" and target in {choice.case_name for choice in self.choices}:
                self.highlighted_index = next(i for i, choice in enumerate(self.choices) if choice.case_name == target)
                self.mode = "loading"
                events["selected_case"] = target
                pointer_action = True
        events["consumed_sources"] = [source for source, captured in self._pointer_captured.items() if captured]
        stick_steps = {"left": 0, "right": 0}
        for source in ("left", "right"):
            vertical = _axis(buttons_by_source.get(source), "vertical")
            if abs(vertical) <= OBJECT_SELECTOR_STICK_RELEASE:
                self._stick_latched[source] = False
            elif (
                not self._stick_latched[source]
                and abs(vertical) >= OBJECT_SELECTOR_STICK_ACTIVATE
            ):
                self._stick_latched[source] = True
                # OpenXR thumbstick +Y is up.  Moving up selects the previous
                # row; moving down selects the next row.
                stick_steps[source] = -1 if vertical > 0.0 else 1

        if now >= self.blocked_until and self._all_neutral(buttons_by_source):
            self._neutral_seen = True

        if pointer_action:
            pass
        elif self.mode == "closed":
            for source in ("left", "right"):
                if edges[source]["menu"]:
                    if self._neutral_seen and now >= self.blocked_until:
                        self._menu_down_since[source] = now
                        self._menu_hold_consumed[source] = False
                    else:
                        # A button carried across an object handoff is not a new
                        # tap or hold.  Wait for a neutral sample and a later press.
                        self._menu_down_since[source] = None
                        self._menu_hold_consumed[source] = True

                down_since = self._menu_down_since[source]
                if (
                    current[source]["menu"]
                    and down_since is not None
                    and not self._menu_hold_consumed[source]
                    and self._neutral_seen
                    and now >= self.blocked_until
                    and (now - float(down_since)) >= self.hold_seconds
                ):
                    self.mode = "open"
                    self._menu_hold_consumed[source] = True
                    self._cancel_armed = False
                    self._manual_navigation_active = False
                    self.hovered_index = None
                    events["opened"] = True
                    break

                if releases[source]["menu"]:
                    if (
                        down_since is not None
                        and not self._menu_hold_consumed[source]
                        and self._neutral_seen
                        and now >= self.blocked_until
                        and (now - float(down_since)) < self.hold_seconds
                    ):
                        events["reset_requested"] = True
                        events["reset_sources"].append(source)
                    self._menu_down_since[source] = None
                    self._menu_hold_consumed[source] = False

        elif self.mode == "open":
            if not current["left"]["menu"] and not current["right"]["menu"]:
                self._cancel_armed = True

            manual_navigation = bool(
                edges["left"]["navigate"]
                or edges["right"]["navigate"]
                or stick_steps["left"]
                or stick_steps["right"]
            )
            if manual_navigation:
                # A resting controller ray must not overwrite a joystick/X/A
                # choice on the following frame.  Once manual navigation is
                # used, Trigger confirms its highlight until this menu closes.
                self._manual_navigation_active = True

            if (
                not self._manual_navigation_active
                and hovered_index is not None
                and 0 <= int(hovered_index) < len(self.choices)
            ):
                self.hovered_index = int(hovered_index)
                self.highlighted_index = int(hovered_index)
            else:
                self.hovered_index = None

            if self._cancel_armed and (
                edges["left"]["menu"] or edges["right"]["menu"]
            ):
                events["cancelled"] = True
                self.close(now=now)
            elif self._neutral_seen and now >= self.blocked_until:
                if edges["left"]["navigate"]:
                    self.highlighted_index = (
                        self.highlighted_index - 1
                    ) % len(self.choices)
                    self.hovered_index = None
                if edges["right"]["navigate"]:
                    self.highlighted_index = (
                        self.highlighted_index + 1
                    ) % len(self.choices)
                    self.hovered_index = None
                for source in ("left", "right"):
                    if stick_steps[source]:
                        self.highlighted_index = (
                            self.highlighted_index + stick_steps[source]
                        ) % len(self.choices)
                        self.hovered_index = None
                # Hands only select a button hit by that same hand's ray. A
                # resting other hand must not turn an off-panel pinch into a click.
                if any(edges[source]["select"] and not _pressed(buttons_by_source.get(source), "hand")
                       and not self._pointer_captured[source] for source in ("left", "right")):
                    selected_index = (
                        self.hovered_index
                        if self.hovered_index is not None
                        else self.highlighted_index
                    )
                    self.highlighted_index = int(selected_index)
                    selected_case = self.choices[self.highlighted_index].case_name
                    self.mode = "loading"
                    events["selected_case"] = selected_case

        self._button_cache = current
        events["highlighted_index"] = self.highlighted_index
        return events


def selector_lines(
    active_case: str,
    highlighted_index: int,
    *,
    mode: str = "open",
    selected_case: str | None = None,
    scene_name: str = "lab",
) -> list[str]:
    choices = object_choices_for_scene(scene_name)
    if mode == "loading":
        target = selected_case or active_case
        target_label = next(
            choice.label.split(" \u2014 ", 1)[0]
            for choice in choices
            if choice.case_name == target
        )
        return [f"Loading {target_label}…", "Please wait"]
    if mode == "error":
        return ["Object switch failed", "Restoring previous object…"]

    lines = ["Choose Object"]
    for index, choice in enumerate(choices):
        pointer = ">" if index == int(highlighted_index) else " "
        active = "  [Active]" if choice.case_name == active_case else ""
        lines.append(f"{pointer} {choice.label}{active}")
    lines.append("Sticks up/down or X/A; trigger selects")
    lines.append("Y/B: cancel")
    return lines
