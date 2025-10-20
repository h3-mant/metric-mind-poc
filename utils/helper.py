import json
import os
import base64
from utils.logger import get_logger

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

def save_img(img_bytes: str) -> str:
    """save base64 image str to PNG file"""
    #set default result to FAILURE
    result = 'FAILURE'
    if img_bytes:
        os.makedirs("images", exist_ok=True)
        # Add base64 padding if needed
        missing_padding = len(img_bytes) % 4
        if missing_padding:
            img_bytes += '=' * (4 - missing_padding)
        try:
            decoded_bytes = base64.b64decode(img_bytes)
            with open("images/img.png", "wb") as f:
                f.write(decoded_bytes)
            logger.info("Saved image to images/img.png")
            result = 'SUCCESS'
        except Exception as e:
            logger.error(f"Failed to decode/save image: {e}")
    else:
        logger.error('No image bytes to save')
    return result