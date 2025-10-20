# facerec.py
import cv2, os
import numpy as np
from PIL import Image

size = 2
# Load cascade relative to this file, so it works on any machine
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CASCADE_PATH = os.path.join(_BASE_DIR, "face_cascade.xml")
haar_cascade = cv2.CascadeClassifier(_CASCADE_PATH)


def _preprocess_face(gray_img, target_size):
    # Resize, histogram equalization to reduce lighting variability, then L2 normalize
    if gray_img.shape[1] != target_size[0] or gray_img.shape[0] != target_size[1]:
        gray_img = cv2.resize(gray_img, target_size)
    # Histogram equalization
    eq = cv2.equalizeHist(gray_img)
    vec = eq.astype('float32') / 255.0
    vec = vec.reshape(1, -1)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return eq, vec

# Part 1: Prepare training data (custom simple nearest-neighbor recognizer)
def train_model():
    model = None
    names = {}
    fn_dir = os.path.join(_BASE_DIR, 'face_samples')

    print('Training...')

    training_vectors = []  # list of row vectors (flattened faces) float32 L2-normalized
    training_labels = []   # numeric labels aligned with vectors
    label_id = 0

    for (root, dirs, files) in os.walk(fn_dir, topdown=True):
        for subdir in dirs:
            # Skip temporary/incomplete registration folder and hidden dirs
            if subdir.lower() == 'temp_criminal' or subdir.startswith('.'):
                continue
            names[label_id] = subdir
            subject_path = os.path.join(root, subdir)
            for filename in os.listdir(subject_path):
                path = os.path.join(subject_path, filename)
                # Skip nested directories and non-image files
                if os.path.isdir(path):
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext not in {'.png', '.jpg', '.jpeg', '.bmp'}:
                    continue
                # Read image
                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if img is None:
                    print(f"Skipping {path}, unable to read image")
                    continue
                # Ensure correct size (registration saves 112x92)
                target_size = (112, 92)
                _, vec = _preprocess_face(img, target_size)
                training_vectors.append(vec)
                training_labels.append(label_id)
            label_id += 1

    if len(training_vectors) == 0:
        # No training data available
        return {"vectors": None, "labels": None, "names": names}, names

    X = np.vstack(training_vectors)        # N x D
    y = np.array(training_labels)          # N

    # Optionally precompute per-class centroids for speed and adaptive thresholds
    centroids = {}
    class_thresholds = {}
    for lid in np.unique(y):
        class_vectors = X[y == lid]
        c = class_vectors.mean(axis=0)
        cnorm = np.linalg.norm(c)
        c = c / cnorm if cnorm > 0 else c
        centroids[int(lid)] = c
        # Similarity distribution to centroid for this class
        sims = (class_vectors @ c.T).ravel()
        mu = float(np.mean(sims))
        sigma = float(np.std(sims))
        # Adaptive minimum acceptance similarity per class
        class_thresholds[int(lid)] = max(0.5, mu - 1.5 * sigma)

    model = {"vectors": X, "labels": y, "centroids": centroids, "names": names, "class_thresholds": class_thresholds}
    return model, names






# Part 2: Use fisherRecognizer on camera stream
def detect_faces(gray_frame):
    global size, haar_cascade

    # Assuming `gray_frame` is a frame captured from DroidCam
    mini_frame = cv2.resize(gray_frame, (int(gray_frame.shape[1] / size), int(gray_frame.shape[0] / size)))

    # Detect faces with default params
    faces = haar_cascade.detectMultiScale(mini_frame)

    # If none found, try detection on a horizontally flipped frame (helps side poses)
    if len(faces) == 0:
        mini_flip = cv2.flip(mini_frame, 1)
        faces = haar_cascade.detectMultiScale(mini_flip)

    return faces



def recognize_face(model, frame, gray_frame, face_coords, names):
    (img_width, img_height) = (112, 92)
    recognized = []
    recog_names = []

    X = model.get("vectors")
    y = model.get("labels")
    centroids = model.get("centroids") or {}
    class_thresholds = model.get("class_thresholds") or {}
    if X is None or y is None or X.shape[0] == 0:
        return (frame, recognized)

    # Global cosine similarity threshold (0..1)
    SIM_THRESHOLD = 0.6
    # Require a margin between best and second-best match to avoid ambiguous hits
    MARGIN_THRESHOLD = 0.02  # Reduced from 0.05 to be more lenient

    for i in range(len(face_coords)):
        face_i = face_coords[i]
        (x, y0, w, h) = [v * size for v in face_i]
        face = gray_frame[y0:y0 + h, x:x + w]
        if face.size == 0:
            continue
        face_resize, vec = _preprocess_face(face, (img_width, img_height))
        # Also evaluate a horizontally flipped version to better match side faces
        face_flip = cv2.flip(face_resize, 1)
        _, vec_flip = _preprocess_face(face_flip, (img_width, img_height))

        # Compare to class centroids first (fast), then fallback to all samples
        best_label = None
        best_sim = -1.0

        # Always evaluate against all samples to compute margins
        sims = (X @ vec.T).ravel()
        sims_flip = (X @ vec_flip.T).ravel()
        if sims.size == 0:
            continue
        order = np.argsort(-sims)  # descending
        order_f = np.argsort(-sims_flip)
        idx = int(order[0])
        idx_f = int(order_f[0])
        best_sim_o = float(sims[idx])
        best_sim_f = float(sims_flip[idx_f])
        if best_sim_f > best_sim_o:
            best_sim = best_sim_f
            best_label = int(y[idx_f])
            second_sim = float(sims_flip[order_f[1]]) if sims_flip.size > 1 else -1.0
        else:
            best_sim = best_sim_o
            best_label = int(y[idx])
            second_sim = float(sims[order[1]]) if sims.size > 1 else -1.0

        # Optionally cross-check centroid to reduce noise
        if len(centroids) > 0 and best_label is not None:
            c_vec = centroids.get(best_label)
            if c_vec is not None:
                c_sim = float(np.dot(vec, c_vec.T))
                best_sim = max(best_sim, c_sim)

        label_name = names.get(best_label, str(best_label))
        # Combine global and per-class adaptive thresholds
        class_min = class_thresholds.get(best_label, SIM_THRESHOLD)
        min_required = max(SIM_THRESHOLD, class_min)
        
        # Debug output to see why recognition fails
        print(f"Face {i}: best_sim={best_sim:.3f}, min_required={min_required:.3f}, margin={best_sim - max(-1.0, second_sim):.3f}")
        print(f"  -> best_label={best_label}, name='{label_name}', threshold_met={best_sim >= min_required}, margin_met={best_sim - max(-1.0, second_sim) >= MARGIN_THRESHOLD}")
        
        if (best_sim >= min_required) and (label_name not in recog_names):
            cv2.rectangle(frame, (x, y0), (x + w, y0 + h), (0, 0, 255), 2)
            recog_names.append(label_name)
            # Map a pseudo-confidence (0..100) from similarity
            confidence = max(0.0, min(100.0, 100.0 * (best_sim)))
            recognized.append((label_name.capitalize(), confidence))
            print(f"  -> RECOGNIZED: {label_name} (confidence: {confidence:.1f}%)")
        else:
            cv2.rectangle(frame, (x, y0), (x + w, y0 + h), (0, 255, 0), 2)
            print(f"  -> NOT RECOGNIZED: {label_name}")

    return (frame, recognized)
