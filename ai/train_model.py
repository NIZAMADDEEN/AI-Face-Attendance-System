import os
import cv2
import pickle
import numpy as np
from deepface import DeepFace

DATASET_DIR = "dataset"
MODEL_PATH = "model/encodings.pickle"
RECOGNITION_MODEL = "ArcFace"
DETECTOR_BACKEND = "opencv"  # Changed from retinaface (download was corrupt)
DETECTOR_FALLBACKS = ["opencv", "ssd", "mtcnn"]

def train_model():
    """
    Iterates through the dataset directory, reads student photos,
    extracts face encodings using DeepFace, and saves them to a pickle file.
    Assumes dataset folder structure: dataset/student_id/*.jpg
    """
    print("[INFO] Start processing faces with DeepFace...")
    
    known_encodings = []
    known_names = []
    
    if not os.path.exists(DATASET_DIR):
        os.makedirs(DATASET_DIR)
        print(f"[WARNING] {DATASET_DIR} directory created. Please add images before training.")
        return False
        
    if not os.path.exists("model"):
        os.makedirs("model")

    # Traverse dataset directory
    # Expected structure: dataset/{student_id}/{image_name}.jpg
    for student_id in os.listdir(DATASET_DIR):
        student_folder = os.path.join(DATASET_DIR, student_id)
        
        if not os.path.isdir(student_folder):
            continue
            
        print(f"[INFO] Processing images for student ID: {student_id}")
        
        for file in os.listdir(student_folder):
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_path = os.path.join(student_folder, file)
                
                try:
                    # Try primary backend, then fallbacks
                    face_objs = None
                    for backend in [DETECTOR_BACKEND] + DETECTOR_FALLBACKS:
                        try:
                            face_objs = DeepFace.represent(
                                img_path=image_path,
                                model_name=RECOGNITION_MODEL,
                                detector_backend=backend,
                                enforce_detection=True,
                                align=True
                            )
                            break
                        except Exception:
                            continue

                    # Last resort: enforce_detection=False
                    if not face_objs:
                        face_objs = DeepFace.represent(
                            img_path=image_path,
                            model_name=RECOGNITION_MODEL,
                            detector_backend=DETECTOR_BACKEND,
                            enforce_detection=False,
                            align=True
                        )
                    
                    for face in face_objs:
                        known_encodings.append(face["embedding"])
                        known_names.append(student_id)
                        
                except Exception as e:
                    print(f"[WARNING] Could not process {image_path}: {e}")
                    continue

    print(f"[INFO] Serializing {len(known_encodings)} encodings...")
    data = {"encodings": known_encodings, "names": known_names}
    
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(data, f)
        
    print(f"[INFO] Training completed. Saved to {MODEL_PATH}")
    return True

if __name__ == "__main__":
    train_model()
