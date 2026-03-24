import cv2
import face_recognition
import pickle
import numpy as np
import os
from .anti_spoofing import is_spoof

MODEL_PATH = "model/encodings.pickle"

# Load the known faces and embeddings globally to avoid reloading on every request
known_data = None

def load_encodings():
    global known_data
    if os.path.exists(MODEL_PATH):
        print(f"[INFO] Loading encodings from {MODEL_PATH}...")
        with open(MODEL_PATH, "rb") as f:
            known_data = pickle.load(f)
    else:
        print(f"[WARNING] {MODEL_PATH} not found. Please train the model first.")
        known_data = {"encodings": [], "names": []}

def recognize_faces_in_frame(frame, enforce_anti_spoofing=True):
    """
    Process a single BGR OpenCV frame, find faces, perform liveness check,
    and recognize the known identities.
    
    Returns a list of dicts:
    [
      { "name": "student_123", "box": (top, right, bottom, left), "spoof": False }
    ]
    """
    global known_data
    if known_data is None:
        load_encodings()
        
    results = []
    
    if len(known_data["encodings"]) == 0:
        return results

    # Use cv2 for reliable BGR to RGB conversion
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    # Detect face boxes - upsample=1 or 2 helps detect smaller faces from a distance
    boxes = face_recognition.face_locations(rgb_frame, number_of_times_to_upsample=2, model="hog")
    
    # Compute encodings for face boxes
    encodings = face_recognition.face_encodings(rgb_frame, boxes)
    
    # Anti-spoofing check: need face landmarks
    landmarks_list = []
    if enforce_anti_spoofing:
        landmarks_list = face_recognition.face_landmarks(rgb_frame, face_locations=boxes)

    for i, encoding in enumerate(encodings):
        # Attempt to match each face to known encodings
        matches = face_recognition.compare_faces(known_data["encodings"], encoding, tolerance=0.5)
        name = "Unknown"
        
        # Calculate distances to find the best match
        face_distances = face_recognition.face_distance(known_data["encodings"], encoding)
        
        if len(face_distances) > 0:
            best_match_index = np.argmin(face_distances)
            if matches[best_match_index]:
                name = known_data["names"][best_match_index]
                
        # Perform anti-spoofing logic
        spoof_detected = False
        spoof_message = "Liveness verified."
        if enforce_anti_spoofing and i < len(landmarks_list):
            spoof_detected, spoof_message = is_spoof(landmarks_list[i])
            
        results.append({
            "name": name,
            "box": boxes[i],
            "spoof": spoof_detected,
            "spoof_message": spoof_message
        })
        
    return results

def reload_model():
    """Force reload the encodings into memory"""
    load_encodings()
