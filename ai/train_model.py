import os
import cv2
import face_recognition
import pickle

DATASET_DIR = "dataset"
MODEL_PATH = "model/encodings.pickle"

def train_model():
    """
    Iterates through the dataset directory, reads student photos,
    extracts face encodings, and saves them to a pickle file.
    Assumes dataset folder structure: dataset/student_id/*.jpg
    """
    print("[INFO] Start processing faces...")
    
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
                
                # Load image
                image = cv2.imread(image_path)
                if image is None:
                    continue
                
                # Convert image from BGR (OpenCV) to RGB (face_recognition)
                rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                
                # Detect bounding boxes for faces
                boxes = face_recognition.face_locations(rgb_image, model="hog")
                
                # Compute facial embeddings
                encodings = face_recognition.face_encodings(rgb_image, boxes)
                
                for encoding in encodings:
                    known_encodings.append(encoding)
                    known_names.append(student_id)

    print(f"[INFO] Serializing {len(known_encodings)} encodings...")
    data = {"encodings": known_encodings, "names": known_names}
    
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(data, f)
        
    print(f"[INFO] Training completed. Saved to {MODEL_PATH}")
    return True

if __name__ == "__main__":
    train_model()
