from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .models import MediaInfo


@dataclass(slots=True)
class CropPoint:
    time: float
    center_x: float
    center_y: float


@dataclass(slots=True)
class _FaceDetector:
    classifier: cv2.CascadeClassifier
    mirrored: bool = False


def analyse_crop_path(
    source: Path,
    media: MediaInfo,
    start: float,
    end: float,
    *,
    sample_interval: float = 0.35,
) -> list[CropPoint]:
    """Build a smooth subject path from faces, continuity and visible motion.

    This lightweight first-version tracker intentionally has a safe fallback:
    if it cannot identify a subject confidently, it holds the previous crop
    instead of jumping to a random person.
    """
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        return [CropPoint(0.0, media.width / 2, media.height / 2)]
    yunet = _load_yunet_detector()
    detectors = _load_face_detectors()
    fps = capture.get(cv2.CAP_PROP_FPS) or media.fps or 30.0
    step_frames = max(1, int(round(fps * sample_interval)))
    first_frame = max(0, int(round(start * fps)))
    last_frame = max(first_frame + 1, int(round(end * fps)))
    capture.set(cv2.CAP_PROP_POS_FRAMES, first_frame)

    previous_small: np.ndarray | None = None
    smoothed = np.array([media.width / 2, media.height / 2], dtype=np.float64)
    last_face: np.ndarray | None = None
    face_misses = 0
    locked = False
    points: list[CropPoint] = []
    frame_index = first_frame

    while frame_index < last_frame:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok:
            break
        height, width = frame.shape[:2]
        scale = min(1.0, 720.0 / max(width, height))
        small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = _detect_faces(small, gray, yunet, detectors)
        scene_cut = False
        if previous_small is not None and previous_small.shape == gray.shape:
            scene_cut = float(cv2.absdiff(gray, previous_small).mean()) / 255.0 > 0.18
            if scene_cut:
                last_face = None
                face_misses = 0

        target: np.ndarray | None = None
        best_score = -1e9
        for x, y, face_w, face_h in faces:
            center = np.array([(x + face_w / 2) / scale, (y + face_h / 2) / scale])
            area_score = (face_w * face_h) / max(1.0, gray.shape[0] * gray.shape[1])
            anchor = last_face if last_face is not None else smoothed
            distance = np.linalg.norm(center - anchor) / max(width, height)
            centrality = 1.0 - abs(center[0] - width / 2) / max(1.0, width / 2)
            activity = 0.0
            if not scene_cut and previous_small is not None and previous_small.shape == gray.shape:
                mouth_y = min(gray.shape[0] - 1, y + int(face_h * 0.52))
                mouth = gray[mouth_y : min(gray.shape[0], y + face_h), x : x + face_w]
                old_mouth = previous_small[mouth_y : min(gray.shape[0], y + face_h), x : x + face_w]
                if mouth.size and mouth.shape == old_mouth.shape:
                    mouth_change = float(cv2.absdiff(mouth, old_mouth).mean()) / 255.0
                    upper = gray[y:mouth_y, x : x + face_w]
                    old_upper = previous_small[y:mouth_y, x : x + face_w]
                    upper_change = 0.0
                    if upper.size and upper.shape == old_upper.shape:
                        upper_change = float(cv2.absdiff(upper, old_upper).mean()) / 255.0
                    activity = max(0.0, mouth_change - upper_change * 0.35)
            score = area_score * 4.0 + centrality * 0.08 + activity * 7.0 - distance * 0.35
            if score > best_score:
                best_score = score
                target = center

        if target is not None:
            last_face = target.copy()
            face_misses = 0
        else:
            face_misses += 1
            hold_samples = max(2, int(round(1.4 / sample_interval)))
            if not scene_cut and last_face is not None and face_misses <= hold_samples:
                target = last_face.copy()

        if (
            target is None
            and not scene_cut
            and previous_small is not None
            and previous_small.shape == gray.shape
        ):
            difference = cv2.absdiff(gray, previous_small)
            difference = cv2.GaussianBlur(difference, (15, 15), 0)
            _, mask = cv2.threshold(difference, 24, 255, cv2.THRESH_BINARY)
            moments = cv2.moments(mask)
            changed = moments["m00"] / 255.0
            if moments["m00"] > 0 and changed > gray.size * 0.008:
                target = np.array([
                    (moments["m10"] / moments["m00"]) / scale,
                    (moments["m01"] / moments["m00"]) / scale,
                ])

        if target is not None:
            movement_ratio = np.linalg.norm(target - smoothed) / max(width, height)
            if not locked or scene_cut:
                smoothed = target.copy()
                locked = True
            else:
                if movement_ratio > 0.26:
                    alpha = 0.72
                elif movement_ratio > 0.12:
                    alpha = 0.52
                else:
                    alpha = 0.30
                smoothed = smoothed * (1.0 - alpha) + target * alpha
        relative_time = (frame_index - first_frame) / fps
        points.append(CropPoint(relative_time, float(smoothed[0]), float(smoothed[1])))
        previous_small = gray
        frame_index += step_frames

    capture.release()
    if not points:
        points.append(CropPoint(0.0, media.width / 2, media.height / 2))
    return _reduce_points(points, minimum_gap=0.7)


def _load_face_detectors() -> list[_FaceDetector]:
    base = Path(cv2.data.haarcascades)
    definitions = [
        ("haarcascade_frontalface_default.xml", False),
        ("haarcascade_frontalface_alt2.xml", False),
        ("haarcascade_profileface.xml", False),
        ("haarcascade_profileface.xml", True),
    ]
    result: list[_FaceDetector] = []
    for filename, mirrored in definitions:
        classifier = cv2.CascadeClassifier(str(base / filename))
        if not classifier.empty():
            result.append(_FaceDetector(classifier, mirrored))
    return result


def _load_yunet_detector():
    model = Path(__file__).resolve().parent / "assets" / "face_detection_yunet_2023mar.onnx"
    if not model.is_file() or not hasattr(cv2, "FaceDetectorYN"):
        return None
    try:
        return cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.18, 0.3, 5000)
    except cv2.error:
        return None


def _detect_faces(
    frame: np.ndarray,
    gray: np.ndarray,
    yunet,
    detectors: list[_FaceDetector],
) -> list[tuple[int, int, int, int]]:
    prepared = cv2.equalizeHist(gray)
    min_side = max(20, int(round(min(gray.shape[:2]) * 0.035)))
    height, width = gray.shape[:2]
    candidates: list[tuple[int, int, int, int]] = []
    if yunet is not None:
        try:
            yunet.setInputSize((width, height))
            _, faces = yunet.detect(frame)
            if faces is not None:
                for detected in faces:
                    candidate = _clamp_face(detected[:4], width, height, min_side)
                    if candidate is not None:
                        candidates.append(candidate)
        except cv2.error:
            pass
    for detector in detectors:
        image = cv2.flip(prepared, 1) if detector.mirrored else prepared
        faces = detector.classifier.detectMultiScale(
            image,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(min_side, min_side),
        )
        for x, y, face_w, face_h in faces:
            if detector.mirrored:
                x = width - x - face_w
            candidate = _clamp_face((x, y, face_w, face_h), width, height, min_side)
            if candidate is not None:
                candidates.append(candidate)
    return _deduplicate_faces(candidates)


def _clamp_face(values, width: int, height: int, min_side: int) -> tuple[int, int, int, int] | None:
    x, y, face_w, face_h = (float(value) for value in values)
    x1 = max(0, min(width - 1, int(round(x))))
    y1 = max(0, min(height - 1, int(round(y))))
    x2 = max(0, min(width, int(round(x + face_w))))
    y2 = max(0, min(height, int(round(y + face_h))))
    face_w = x2 - x1
    face_h = y2 - y1
    if face_w < min_side or face_h < min_side:
        return None
    return x1, y1, face_w, face_h


def _deduplicate_faces(faces: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for face in sorted(faces, key=lambda item: item[2] * item[3], reverse=True):
        if all(_intersection_over_union(face, other) < 0.35 for other in kept):
            kept.append(face)
    return kept


def _intersection_over_union(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> float:
    ax1, ay1, aw, ah = first
    bx1, by1, bw, bh = second
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    intersection = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0.0


def _reduce_points(points: list[CropPoint], minimum_gap: float) -> list[CropPoint]:
    if not points:
        return []
    reduced: list[CropPoint] = [points[0]]
    for point in points[1:]:
        if point.time - reduced[-1].time >= minimum_gap:
            reduced.append(point)
    last = points[-1]
    if last.time - reduced[-1].time >= max(0.15, minimum_gap * 0.35):
        reduced.append(last)
    return reduced


def crop_filter(media: MediaInfo, points: list[CropPoint]) -> str:
    target_aspect = 9 / 16
    if media.width / media.height >= target_aspect:
        crop_h = media.height
        crop_w = int(round(crop_h * target_aspect / 2) * 2)
        # A transparent half-crop border lets a face near the source edge stay
        # truly centred. The renderer fills that border with a blurred copy of
        # the source instead of duplicating the face or adding a black stripe.
        border = crop_w // 2
        x_values = [max(0.0, min(media.width, point.center_x)) for point in points]
        expression_points, x_values = _limit_expression_points(points, x_values)
        x_expression = _interpolation_expression(expression_points, x_values)
        return (
            f"format=rgba,pad=iw+{crop_w}:ih:{border}:0:color=black@0,"
            f"crop={crop_w}:{crop_h}:x='{x_expression}':y=0,"
            "scale=1080:1920:flags=lanczos,setsar=1"
        )
    crop_w = media.width
    crop_h = int(round((crop_w / target_aspect) / 2) * 2)
    y_values = [max(0.0, min(media.height - crop_h, point.center_y - crop_h * 0.40)) for point in points]
    expression_points, y_values = _limit_expression_points(points, y_values)
    y_expression = _interpolation_expression(expression_points, y_values)
    return (
        f"crop={crop_w}:{crop_h}:x=0:y='{y_expression}',"
        "scale=1080:1920:flags=lanczos,setsar=1"
    )


def _limit_expression_points(
    points: list[CropPoint],
    values: list[float],
    *,
    maximum: int = 48,
) -> tuple[list[CropPoint], list[float]]:
    """Keep a long tracking path inside FFmpeg's expression-parser limits.

    FFmpeg 9 rejects very long crop expressions (a 90-second clip can easily
    produce 130+ ramps).  Repeatedly remove the point whose removal introduces
    the smallest interpolation error.  This keeps large speaker/scene changes
    and discards the tiny camera corrections that are visually redundant.
    """
    if len(points) <= maximum:
        return list(points), list(values)
    kept = list(range(len(points)))
    while len(kept) > maximum:
        best_position = 1
        best_error = float("inf")
        for position in range(1, len(kept) - 1):
            left_index = kept[position - 1]
            index = kept[position]
            right_index = kept[position + 1]
            span = points[right_index].time - points[left_index].time
            if span <= 0:
                error = 0.0
            else:
                ratio = (points[index].time - points[left_index].time) / span
                interpolated = values[left_index] + (values[right_index] - values[left_index]) * ratio
                error = abs(values[index] - interpolated)
            if error < best_error:
                best_error = error
                best_position = position
        del kept[best_position]
    return [points[index] for index in kept], [values[index] for index in kept]


def _interpolation_expression(points: list[CropPoint], values: list[float]) -> str:
    if len(points) <= 1:
        return f"{values[0]:.2f}"
    # A sum of clipped ramps is the same piecewise-linear path as nested
    # if(lt(...)) clauses, but it does not overflow FFmpeg's expression parser
    # on 60–90 second clips with many tracking points.
    parts = [f"{values[0]:.2f}"]
    for index in range(len(points) - 1):
        left = points[index]
        right = points[index + 1]
        span = max(0.001, right.time - left.time)
        delta = values[index + 1] - values[index]
        if abs(delta) < 0.005:
            continue
        parts.append(
            f"+({delta:.2f})*clip((t-{left.time:.3f})/{span:.3f},0,1)"
        )
    expression = "".join(parts)
    # FFmpeg 9 validates crop coordinates once before the first frame, when
    # the time variable is still NaN. Supply a numeric initial coordinate so
    # the filter can configure, then use the animated path for real frames.
    return f"if(isnan(t),{values[0]:.2f},{expression})"
