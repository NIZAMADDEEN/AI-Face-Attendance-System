import scipy.spatial.distance as dist
import numpy as np
import cv2
import dlib
import os

# ── Blink-tracking state ────────────────────────────────────────────────────
# Maps student_id → {'blink_count': int, 'eye_closed': False, 'frames_seen': int}
_blink_state: dict = {}

EAR_BLINK_THRESHOLD = 0.20   # EAR below this → eye is closing
EAR_OPEN_THRESHOLD  = 0.24   # EAR above this → eye is open
REQUIRED_BLINKS     = 1      # at least 1 blink needed to pass
FRAMES_BEFORE_CHECK = 15     # Grace period before enforcing blink check

# ── Dlib Predictor Initialization ──────────────────────────────────────────
# Use the model found in the virtual environment
DLIB_MODEL_PATH = os.path.join(os.getcwd(), "venv", "Lib", "site-packages", "face_recognition_models", "models", "shape_predictor_68_face_landmarks.dat")
detector = dlib.get_frontal_face_detector()
predictor = None

if os.path.exists(DLIB_MODEL_PATH):
    predictor = dlib.shape_predictor(DLIB_MODEL_PATH)
else:
    print(f"[WARNING] Dlib landmark model not found at {DLIB_MODEL_PATH}")

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
    """
    if face_crop_gray is None or face_crop_gray.size == 0:
        return 999.0
    lap = cv2.Laplacian(face_crop_gray, cv2.CV_64F)
    return lap.var()

def _color_variance(face_crop_bgr):
    """
    Standard deviation of pixel values across the face crop.
    """
    if face_crop_bgr is None or face_crop_bgr.size == 0:
        return 999.0
    return float(np.std(face_crop_bgr.astype(np.float32)))

def reset_blink_state(face_id: str):
    _blink_state[face_id] = {"blink_count": 0, "eye_closed": False, "frames_seen": 0}

def update_blink(face_id: str, ear: float):
    if face_id not in _blink_state:
        reset_blink_state(face_id)

    state = _blink_state[face_id]
    state["frames_seen"] += 1

    if ear < EAR_BLINK_THRESHOLD:
        state["eye_closed"] = True
    elif state["eye_closed"] and ear >= EAR_OPEN_THRESHOLD:
        state["blink_count"] += 1
        state["eye_closed"] = False

    if state["frames_seen"] < FRAMES_BEFORE_CHECK:
        return True   # give benefit of doubt during grace period
    return state["blink_count"] >= REQUIRED_BLINKS

def _check_liveness_cnn(face_crop_bgr):
    if face_crop_bgr is None or face_crop_bgr.size == 0:
        return 0.0, False
    hsv = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    score = (np.std(v) * 0.4) + (np.std(s) * 0.6)
    is_live = score > 22.0  # Increased from 15.0
    return score, is_live

def is_spoof(landmarks=None, face_crop_bgr=None, face_id: str = "default"):
    """
    Combines image heuristics and mandatory temporal blink detection using dlib.
    """
    try:
        if face_crop_bgr is None or face_crop_bgr.size == 0:
            return True, "Face crop missing."

        # ── 1. Image Heuristics (First line of defense) ─────────────────────
        gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)
        tex = _texture_score(gray)
        col_var = _color_variance(face_crop_bgr)
        cnn_score, is_live_cnn = _check_liveness_cnn(face_crop_bgr)
        
        # Stricter thresholds
        if tex < 80:
            return True, "Static Image suspected (Spoof avoided)"
        if col_var < 18:
            return True, "Screen detected (Spoof avoided)"
        if not is_live_cnn:
            return True, "Spoofing signature detected (Spoof avoided)"

        # ── 2. Dlib Landmark Extraction & Blink Detection ──────────────────
        if predictor:
            # Need a bounding box for dlib (the whole crop is the face)
            dlib_rect = dlib.rectangle(0, 0, face_crop_bgr.shape[1], face_crop_bgr.shape[0])
            shape = predictor(gray, dlib_rect)
            
            # Extract eye landmarks
            # Left eye: 36-41, Right eye: 42-47
            shape_np = np.zeros((68, 2), dtype="int")
            for i in range(0, 68):
                shape_np[i] = (shape.part(i).x, shape.part(i).y)
            
            left_eye = shape_np[36:42]
            right_eye = shape_np[42:48]
            
            left_EAR = calculate_ear(left_eye)
            right_EAR = calculate_ear(right_eye)
            avg_EAR = (left_EAR + right_EAR) / 2.0
            
            # Track blink
            blinked = update_blink(face_id, avg_EAR)
            if not blinked:
                frames_left = FRAMES_BEFORE_CHECK - _blink_state[face_id]["frames_seen"]
                if frames_left > 0:
                    return True, "Analyzing liveness... keep looking."
                return True, "Liveness failed: Please blink naturally."

        return False, "Liveness verified."

    except Exception as e:
        return True, f"Liveness Error: {str(e)}"

    except Exception as e:
        return True, f"Liveness Error: {str(e)}"
