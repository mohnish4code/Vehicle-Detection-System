from ultralytics import YOLO
import cv2
import os
import re
import easyocr

# -------------------- LOAD --------------------
model = YOLO("models/best.pt")
reader = easyocr.Reader(['en'])


# -------------------- PREPROCESS --------------------
def preprocess_variants(crop):
    variants = []

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # 1. Resize
    v1 = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(v1)

    # 2. Histogram equalization (good for shiny plates)
    v2 = cv2.equalizeHist(gray)
    v2 = cv2.resize(v2, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(v2)

    # 3. Adaptive threshold
    v3 = cv2.adaptiveThreshold(gray, 255,
                               cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 11, 2)
    v3 = cv2.resize(v3, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(v3)

    # 4. Blur + threshold
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, v4 = cv2.threshold(blur, 120, 255, cv2.THRESH_BINARY)
    v4 = cv2.resize(v4, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(v4)

    return variants


# -------------------- OCR --------------------
def extract_text(variants):
    best_text = ""
    best_score = 0

    for img in variants:
        results = reader.readtext(img)

        for (_, text, prob) in results:
            text = text.upper()
            text = re.sub(r'[^A-Z0-9]', '', text)

            # ❌ Ignore IND completely
            if text == "IND":
                continue

            score = len(text) * prob

            if score > best_score:
                best_score = score
                best_text = text

    return best_text


# -------------------- CORRECTION --------------------
def smart_correct(text):
    mapping = {
        "O": "0",
        "I": "1",
        "L": "1",
        "Z": "2"
    }

    return "".join([mapping.get(c, c) for c in text])


# -------------------- VALIDATION --------------------
def is_valid_plate(text):
    if len(text) < 6:
        return False

    if len(text) > 12:
        return False

    if not any(c.isalpha() for c in text):
        return False

    if not any(c.isdigit() for c in text):
        return False

    return True


# -------------------- DETECTION --------------------
def detect_plate(image_path):
    img = cv2.imread(image_path)

    if img is None:
        print(f"❌ Could not read {image_path}")
        return []

    results = model(img, conf=0.25)[0]

    plates = []

    for box in results.boxes.xyxy:
        x1, y1, x2, y2 = map(int, box)

        h, w, _ = img.shape

        # 🔥 IMPORTANT: more padding improves OCR
        pad = 25
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)

        crop = img[y1:y2, x1:x2]

        if crop.size == 0:
            continue

        variants = preprocess_variants(crop)

        raw_text = extract_text(variants)
        print("🔍 RAW OCR:", raw_text)

        if raw_text:
            text = smart_correct(raw_text)
            print("🛠 Corrected:", text)

            if is_valid_plate(text):
                plates.append(text)

    return plates


# -------------------- MAIN --------------------
if __name__ == "__main__":
    folder = "test_images"

    for file in os.listdir(folder):
        path = os.path.join(folder, file)

        print(f"\n📷 Image: {file}")

        plates = detect_plate(path)

        if plates:
            for p in plates:
                print(f"✅ Final Plate: {p}")
        else:
            print("❌ No valid plate detected")