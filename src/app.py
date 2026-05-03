import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import streamlit as st
import cv2
import numpy as np
from ultralytics import YOLO
import easyocr
import re
from sheets import save_to_sheets


# -------------------- LOAD MODEL --------------------
@st.cache_resource
def load_model():
    return YOLO("models/best.pt")

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['en'])

model = load_model()
reader = load_ocr()


# -------------------- PREPROCESS --------------------
def preprocess_variants(crop):
    variants = []

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # resize
    v1 = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(v1)

    # histogram equalization
    v2 = cv2.equalizeHist(gray)
    v2 = cv2.resize(v2, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(v2)

    # adaptive threshold
    v3 = cv2.adaptiveThreshold(gray, 255,
                               cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 11, 2)
    v3 = cv2.resize(v3, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    variants.append(v3)

    # blur + threshold
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

            # ignore IND
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
    if len(text) < 6 or len(text) > 12:
        return False
    if not any(c.isalpha() for c in text):
        return False
    if not any(c.isdigit() for c in text):
        return False
    return True


# -------------------- DETECTION --------------------
def detect_plate(image):
    results = model(image, conf=0.25)[0]
    plates = []

    for box in results.boxes.xyxy:
        x1, y1, x2, y2 = map(int, box)

        h, w, _ = image.shape

        # padding
        pad = 25
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)

        crop = image[y1:y2, x1:x2]

        if crop.size == 0:
            continue

        variants = preprocess_variants(crop)
        raw_text = extract_text(variants)

        if raw_text:
            text = smart_correct(raw_text)

            if is_valid_plate(text):
                plates.append(text)

    return plates


# -------------------- UI --------------------
st.title("🚗 License Plate Detection System")

option = st.radio("Choose input method:", ["Upload Image", "Use Camera"])

image = None

if option == "Upload Image":
    uploaded_file = st.file_uploader("Upload an image", type=["jpg", "png", "jpeg"])
    if uploaded_file is not None:
        file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
        image = cv2.imdecode(file_bytes, 1)

elif option == "Use Camera":
    camera_image = st.camera_input("Take a picture")
    if camera_image is not None:
        file_bytes = np.asarray(bytearray(camera_image.read()), dtype=np.uint8)
        image = cv2.imdecode(file_bytes, 1)


# -------------------- PROCESS --------------------
if image is not None:
    st.image(image, channels="BGR", caption="Input Image")

    plates = detect_plate(image)

    if plates:
        for p in plates:
            st.success(f"Detected Plate: {p}")
            save_to_sheets(p, "streamlit_capture")
    else:
        st.error("No valid plate detected")