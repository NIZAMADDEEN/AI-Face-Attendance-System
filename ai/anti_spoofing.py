import scipy.spatial.distance as dist
import numpy as np
import cv2

# ── Blink-tracking state ────────────────────────────────────────────────────
# Maps student_id → {'blink_count': int, 'last_ear': float, 'frames_seen': int}
_blink_state: dict = {}

EAR_BLINK_THRESHOLD = 0.22   # EAR below this → eye is closing
EAR_OPEN_THRESHOLD  = 0.26   # EAR above this → eye is open
REQUIRED_BLINKS     = 1      # at least 1 blink needed to pass
FRAMES_BEFORE_CHECK = 25     # only enforce blink check after N frames


def calculate_ear(eye):
    """Eye Aspect Ratio from 6 (x,y) landmark points."""
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    if C == 0:
        return 0.3  # safe default
    return (A + B) / (2.0 * C)


def _texture_score(face_crop_gray):
    """
    Laplacian variance — measures how much high-frequency detail is present.
    Real faces: lots of micro-texture (pores, hair, wrinkles).
    Printed photos / screens: much flatter, lower variance.
    """
    if face_crop_gray is None or face_crop_gray.size == 0:
        return 999.0  # can't judge — let it pass
    lap = cv2.Laplacian(face_crop_gray, cv2.CV_64F)
    return lap.var()


def _color_variance(face_crop_bgr):
    """
    Standard deviation of pixel values across the face crop.
    A printed photo held flat tends to have very uniform illumination.
    A real 3-D face shows natural shading variation.
    """
    if face_crop_bgr is None or face_crop_bgr.size == 0:
        return 999.0
    return float(np.std(face_crop_bgr.astype(np.float32)))


def reset_blink_state(face_id: str):
    """Call this when a new session starts for a face_id."""
    _blink_state[face_id] = {"blink_count": 0, "eye_closed": False, "frames_seen": 0}


def update_blink(face_id: str, ear: float):
    """
    Track blink transitions. A blink = EAR drops below threshold then rises above it.
    Returns True if the person has blinked enough times.
    """
    if face_id not in _blink_state:
        reset_blink_state(face_id)

    state = _blink_state[face_id]
    state["frames_seen"] += 1

    if ear < EAR_BLINK_THRESHOLD:
        state["eye_closed"] = True
    elif state["eye_closed"] and ear >= EAR_OPEN_THRESHOLD:
        state["blink_count"] += 1
        state["eye_closed"] = False

    # Only enforce blink requirement after enough frames have been collected
    if state["frames_seen"] < FRAMES_BEFORE_CHECK:
        return True   # give benefit of doubt early on
    return state["blink_count"] >= REQUIRED_BLINKS


def is_spoof(landmarks, face_crop_bgr=None, face_id: str = "default"):
    """
    Multi-factor liveness check.

    Checks (in order):
      1. Texture sharpness  — Laplacian variance of face region
      2. Color variance     — illumination uniformity of face region
      3. EAR sanity         — eyes look plausible (not a mask / extreme distortion)
      4. Blink detection    — person must have blinked at least once

    Returns (is_spoof: bool, reason: str)
    """
    try:
        # ── 1. Texture analysis ────────────────────────────────────────────
        if face_crop_bgr is not None:
            gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)
            tex = _texture_score(gray)
            # Printed photos / phone screens typically score < 80
            if tex < 60:
                return True, f"Low texture detail detected (score={tex:.1f}). Possible photo spoof."

        # ── 2. Color / illumination variance ──────────────────────────────
        if face_crop_bgr is not None:
            col_var = _color_variance(face_crop_bgr)
            if col_var < 12:
                return True, f"Unnaturally uniform face detected (var={col_var:.1f}). Possible flat image."

        # ── 3. EAR sanity check ───────────────────────────────────────────
        if 'left_eye' not in landmarks or 'right_eye' not in landmarks:
            return True, "Face landmarks missing. Cannot verify liveness."

        left_eye  = landmarks['left_eye']
        right_eye = landmarks['right_eye']
        left_EAR  = calculate_ear(left_eye)
        right_EAR = calculate_ear(right_eye)
        avg_EAR   = (left_EAR + right_EAR) / 2.0

        # Extreme EAR values suggest mask / distorted image / non-face
        if avg_EAR < 0.08 or avg_EAR > 0.50:
            return True, "Abnormal eye aspect ratio. Liveness check failed."

        # ── 4. Blink detection ────────────────────────────────────────────
        blinked = update_blink(face_id, avg_EAR)
        if not blinked:
            frames = _blink_state.get(face_id, {}).get("frames_seen", 0)
            return True, f"No blink detected yet (frame {frames}/{FRAMES_BEFORE_CHECK}). Please blink naturally."

        return False, "Liveness verified."

    except Exception as e:
        return True, f"Anti-spoofing error: {str(e)}"
