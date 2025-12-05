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

        # Attempt to extract base64 content from common wrappers (markdown/data URL)
        # Accept newlines/whitespace inside the base64 block.
        m = re.search(r"data:image\/(?:png|jpeg|jpg);base64,([A-Za-z0-9+/=\n\r]+)", img_bytes, flags=re.IGNORECASE)
        if m:
            img_b64 = m.group(1)
        else:
            # If the input looks like a markdown image link: ![...](data:image/png;base64,XXX)
            m2 = re.search(r"\(data:image\/(?:png|jpeg|jpg);base64,([A-Za-z0-9+/=\n\r]+)\)", img_bytes, flags=re.IGNORECASE)
            if m2:
                img_b64 = m2.group(1)
            else:
                # Fallback: maybe the input is already the base64 payload or a raw bytes repr.
                img_b64 = str(img_bytes)

        # Remove whitespace/newlines that can be introduced when printing large base64 blobs
        img_b64 = re.sub(r"\s+", "", img_b64)

        # Strip common Python bytes repr markers if present (e.g. "b'...'")
        if img_b64.startswith("b'") and img_b64.endswith("'"):
            img_b64 = img_b64[2:-1]
        if img_b64.startswith('b"') and img_b64.endswith('"'):
            img_b64 = img_b64[2:-1]

        # If the payload is obviously too small to be a real PNG, skip saving.
        if len(img_b64) < 100:
            logger.warning("Image payload too small to decode (len=%s). Skipping save. Preview: %s", len(img_b64), img_b64[:120])
            return

        # Add missing padding if needed
        missing_padding = len(img_b64) % 4
        if missing_padding:
            img_b64 += "=" * (4 - missing_padding)

        decoded_bytes = base64.b64decode(img_b64)

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


