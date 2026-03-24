import scipy.spatial.distance as dist

def calculate_ear(eye):
    """
    Calculates the Eye Aspect Ratio (EAR) given a list of 6 eye landmarks.
    """
    # compute the euclidean distances between the two sets of
    # vertical eye landmarks (x, y)-coordinates
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])

    # compute the euclidean distance between the horizontal
    # eye landmark (x, y)-coordinates
    C = dist.euclidean(eye[0], eye[3])

    # compute the eye aspect ratio
    ear = (A + B) / (2.0 * C)

    # return the eye aspect ratio
    return ear

def is_spoof(landmarks):
    """
    Basic liveness/anti-spoofing check using Eye Aspect Ratio (EAR).
    Returns (bool, str): (is_spoof_detected, reason_message)
    """
    try:
        if 'left_eye' not in landmarks or 'right_eye' not in landmarks:
            # Missing landmarks usually means the face is too far or blurry
            return True, "Face too far or low quality, cannot verify liveness."
            
        left_eye = landmarks['left_eye']
        right_eye = landmarks['right_eye']
        
        left_EAR = calculate_ear(left_eye)
        right_EAR = calculate_ear(right_eye)
        average_EAR = (left_EAR + right_EAR) / 2.0
        
        # A normal human EAR is typically between 0.15 and 0.35
        if average_EAR < 0.1 or average_EAR > 0.45:
            return True, "Liveness anomaly detected (Check lighting or distance)."
            
        return False, "Liveness verified."
    except Exception as e:
        return True, f"Anti-spoofing error: {str(e)}"

