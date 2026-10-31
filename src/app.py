# Streamlit UI. Temporary - this gets replaced by the FastAPI + React app.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import streamlit as st

from src.config import setup_logging
from src.pipeline import PlatePipeline
from src.sheets import save_to_sheets

setup_logging()


@st.cache_resource
def load_pipeline():
    return PlatePipeline().load()


pipeline = load_pipeline()

st.title("Car Number Plate Detection System")

option = st.radio("Choose input method:", ["Upload Image", "Use Camera"])

upload = None
if option == "Upload Image":
    upload = st.file_uploader("Upload an image", type=["jpg", "png", "jpeg"])
else:
    upload = st.camera_input("Take a picture")

if upload is not None:
    image = cv2.imdecode(np.frombuffer(upload.getvalue(), dtype=np.uint8), cv2.IMREAD_COLOR)

    if image is None:
        st.error("Could not read that image")
    else:
        st.image(image, channels="BGR", caption="Input Image")
        plates = [p for p in pipeline.detect(image) if not p.needs_review]

        if not plates:
            st.error("No valid plate detected")

        for i, p in enumerate(plates):
            st.success(f"Detected Plate: {p.text}")
            # Only save on click; saving inline ran again on every rerun
            if st.button(f"Save {p.text}", key=f"save_{i}_{p.text}"):
                save_to_sheets(p.text, "streamlit_capture")
                st.toast(f"Saved {p.text}")
