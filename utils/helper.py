import json
import os
import base64
from utils.logger import get_logger
import io
import re
from PIL import Image
import requests
from PIL import Image

logger = get_logger(__name__)

def json_to_dict(path: str) -> dict:
    """convert data schema from JSON to dictionary"""
    try:
        with open(path, 'r') as f:
            return json.load(f) 
        logger.info(f"Loaded JSON file from {path}")

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in file {path}: {e}")
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {path}")

def save_img(image_url: str) -> None:
    """Download image from signed GCS URL and save to a uniquely named PNG file."""
    
    if not image_url:
        logger.error("No image URL provided")
        return

    os.makedirs("images", exist_ok=True)

    try:
        # Download image
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        image_bytes = resp.content

        # Validate image
        try:
            Image.open(io.BytesIO(image_bytes)).verify()
        except Exception as e:
            raise ValueError(f"Downloaded data is not a valid image: {e}")

        # Determine next available filename
        existing = [
            f for f in os.listdir("images")
            if f.startswith("img_") and f.endswith(".png")
        ]
        next_index = len(existing) + 1
        output_path = os.path.join("images", f"img_{next_index}.png")

        # Save image
        with open(output_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"Saved image to {output_path}")

    except Exception as e:
        logger.error(f"Failed to download/save image: {e}")



