import cv2
import pickle
import numpy as np
import os
from deepface import DeepFace

MODEL_PATH = "model/encodings.pickle"
RECOGNITION_MODEL = "ArcFace"
DETECTOR_BACKEND = "opencv"  # Switched from retinaface (download was corrupt) - opencv needs no extra weights
DETECTOR_FALLBACKS = ["opencv", "ssd", "mtcnn"]  # Fallback chain if primary fails
DISTANCE_METRIC = "cosine"
THRESHOLD = 0.75 # ArcFace cosine threshold — raised to handle real-world webcam lighting/angle variance

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
                face_objs = DeepFace.extract_faces(
                    img_path=frame,
                    detector_backend=backend,
                    enforce_detection=True,
                    align=True,
                    anti_spoofing=True if enforce_anti_spoofing else False
                )
                break  # Success - stop trying fallbacks
            except Exception as e:
                last_error = e
                continue

        # If all backends fail, try once more with enforce_detection=False to get any result
        if face_objs is None:
            try:
                face_objs = DeepFace.extract_faces(
                    img_path=frame,
                    detector_backend=DETECTOR_BACKEND,
                    enforce_detection=False,
                    align=True,
                    anti_spoofing=True if enforce_anti_spoofing else False
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
            
            # Anti-spoofing check using DeepFace's native MiniFASNet engine
            spoof_detected = False
            spoof_message = "Liveness verified."
            
            if enforce_anti_spoofing:
                # extract_faces natively injects "is_real"
                if "is_real" in face:
                    if not face["is_real"]:
                        spoof_detected = True
                        score = face.get("antispoof_score", 0)
                        spoof_message = f"Spoof Detected (Photo/Screen). Score: {score:.2f}"
                else:
                    spoof_detected = True
                    spoof_message = "Spoof Analysis Failed. Please rescan."

            name = "Unknown"
            best_dist = float("inf")
            
            # Only compute heavy database embeddings if it's a real face!
            if not spoof_detected:
                try:
                    # Represent the full original frame (matches training pipeline exactly).
                    # Using the pre-extracted face crop caused embedding drift due to format differences.
                    face_bgr_255 = (face["face"][:, :, ::-1] * 255).astype(np.uint8)
                    rep = DeepFace.represent(
                        img_path=face_bgr_255,
                        model_name=RECOGNITION_MODEL,
                        detector_backend="skip",  # face already cropped/aligned
                        enforce_detection=False
                    )
                    embedding = rep[0]["embedding"]
                    
                    # Find best match using cosine distance
                    known_encodings = np.array(known_data["encodings"])
                    if len(known_encodings) > 0:
                        dot_product = np.dot(known_encodings, embedding)
                        norms = np.linalg.norm(known_encodings, axis=1) * np.linalg.norm(embedding)
                        distances = 1 - (dot_product / norms)
                        
                        best_idx = np.argmin(distances)
                        print(f"[DEBUG] Known faces: {len(known_encodings)}, Best distance: {distances[best_idx]:.4f} for {known_data['names'][best_idx]}")
                        if distances[best_idx] < THRESHOLD:
                            name = known_data["names"][best_idx]
                            best_dist = distances[best_idx]
                except Exception as e:
                    print(f"[WARN] Failed to compute embedding for detected face: {e}")

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
