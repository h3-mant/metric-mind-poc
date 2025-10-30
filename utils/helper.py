import json
import os
import base64
from utils.logger import get_logger
import io
import re
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

def save_img(img_bytes: str) -> None:
    """Save base64 image string (possibly wrapped in Markdown/data URL) to a uniquely named PNG file."""
    if not img_bytes:
        logger.error("No image bytes to save")
        return

    os.makedirs("images", exist_ok=True)

    try:
        # Extract base64 content if Markdown or data URL is present
        match = re.search(r"data:image\/png;base64,([A-Za-z0-9+/=]+)", img_bytes)
        if match:
            img_bytes = match.group(1)

        # Add missing padding if needed
        missing_padding = len(img_bytes) % 4
        if missing_padding:
            img_bytes += "=" * (4 - missing_padding)

        decoded_bytes = base64.b64decode(img_bytes)

        # Validate before saving
        try:
            Image.open(io.BytesIO(decoded_bytes)).verify()
        except Exception as e:
            raise ValueError(f"Invalid image data: {e}")

        # Determine next available filename (e.g., img_1.png, img_2.png, ...)
        existing = [f for f in os.listdir("images") if f.startswith("img_") and f.endswith(".png")]
        next_index = len(existing) + 1
        output_path = os.path.join("images", f"img_{next_index}.png")

        # Save image
        with open(output_path, "wb") as f:
            f.write(decoded_bytes)

        logger.info(f"Saved image to {output_path}")

    except Exception as e:
        logger.error(f"Failed to decode/save image: {e}")


