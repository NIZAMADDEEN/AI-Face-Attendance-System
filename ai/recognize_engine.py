import cv2
import pickle
import numpy as np
import os
from deepface import DeepFace
from .anti_spoofing import is_spoof

MODEL_PATH = "model/encodings.pickle"
RECOGNITION_MODEL = "ArcFace"
DETECTOR_BACKEND = "opencv"  # Switched from retinaface (download was corrupt) - opencv needs no extra weights
DETECTOR_FALLBACKS = ["opencv", "ssd", "mtcnn"]  # Fallback chain if primary fails
DISTANCE_METRIC = "cosine"
THRESHOLD = 0.685 # ArcFace threshold for cosine

# Load the known faces and embeddings globally to avoid reloading on every request
known_data = None

def load_encodings():
    global known_data
    if os.path.exists(MODEL_PATH):
        print(f"[INFO] Loading DeepFace encodings from {MODEL_PATH}...")
        with open(MODEL_PATH, "rb") as f:
            known_data = pickle.load(f)
    else:
        print(f"[WARNING] {MODEL_PATH} not found. Please train the model first.")
        known_data = {"encodings": [], "names": []}

def recognize_faces_in_frame(frame, enforce_anti_spoofing=True):
    """
    Process a single BGR OpenCV frame using DeepFace (RetinaFace + ArcFace).
    
    Returns a list of dicts:
    [
      { "name": "student_123", "box": (top, right, bottom, left), "spoof": False }
    ]
    """
    global known_data
    if known_data is None:
        load_encodings()
        
    results = []
    
    # We now continue detection even if known_data is empty, so users see "Unknown" boxes.

    try:
        # Detect and represent faces using DeepFace with fallback backends
        face_objs = None
        last_error = None
        
        for backend in [DETECTOR_BACKEND] + DETECTOR_FALLBACKS:
            try:
                face_objs = DeepFace.represent(
                    img_path=frame,
                    model_name=RECOGNITION_MODEL,
                    detector_backend=backend,
                    enforce_detection=True,
                    align=True
                )
                break  # Success - stop trying fallbacks
            except Exception as e:
                last_error = e
                continue

        # If all backends fail, try once more with enforce_detection=False to get any result
        if face_objs is None:
            try:
                face_objs = DeepFace.represent(
                    img_path=frame,
                    model_name=RECOGNITION_MODEL,
                    detector_backend=DETECTOR_BACKEND,
                    enforce_detection=False,
                    align=True
                )
            except Exception as e:
                print(f"[ERROR] All detection backends failed: {e}")
                return results

        if not face_objs:
            return results

        for face in face_objs:
            # DeepFace returns box as {'x', 'y', 'w', 'h'}
            facial_area = face["facial_area"]
            x, y, w, h = facial_area["x"], facial_area["y"], facial_area["w"], facial_area["h"]
            # Convert to (top, right, bottom, left) for consistency with existing UI/rendering
            box = (y, x + w, y + h, x)
            
            embedding = face["embedding"]
            name = "Unknown"
            
            # Find best match using cosine distance
            best_dist = float("inf")
            best_idx = -1
            
            # Using numpy for faster vector distance calculation
            known_encodings = np.array(known_data["encodings"])
            if len(known_encodings) > 0:
                # Cosine distance = 1 - Cosine Similarity
                dot_product = np.dot(known_encodings, embedding)
                norms = np.linalg.norm(known_encodings, axis=1) * np.linalg.norm(embedding)
                distances = 1 - (dot_product / norms)
                
                best_idx = np.argmin(distances)
                best_dist = distances[best_idx]
                
                if best_dist < THRESHOLD:
                    name = known_data["names"][best_idx]

            # Extract padded face crop for liveness analysis (dlib needs context)
            padding = int(0.20 * max(w, h))
            py1, py2 = max(0, y - padding), min(frame.shape[0], y + h + padding)
            px1, px2 = max(0, x - padding), min(frame.shape[1], x + w + padding)
            face_crop = frame[py1:py2, px1:px2] if (h > 0 and w > 0) else None
            
            face_id = name if name != "Unknown" else f"unknown_{x}_{y}"

            # Anti-spoofing check
            spoof_detected = False
            spoof_message = "Liveness verified."
            if enforce_anti_spoofing:
                # Note: CNN-based liveness might be integrated inside is_spoof or as a separate call
                spoof_detected, spoof_message = is_spoof(
                    None, # Landmarks not directly provided by represent() without extra work, 
                          # but is_spoof can be updated to use modern CNN detection
                    face_crop_bgr=face_crop,
                    face_id=face_id
                )
                
            results.append({
                "name": name,
                "box": box,
                "spoof": spoof_detected,
                "spoof_message": spoof_message,
                "confidence": 1 - best_dist if best_dist != float("inf") else 0
            })
            
    except Exception as e:
        print(f"[ERROR] Recognition failed: {e}")
        
    return results

def reload_model():
    """Force reload the encodings into memory"""
    load_encodings()
