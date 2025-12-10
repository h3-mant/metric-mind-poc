import os
from pathlib import Path
from typing import List
import streamlit as st

def apply_sky_style():
    """Apply a lightweight Sky-inspired style to matplotlib when called from local plotting code.

    This doesn't force agent-generated code to use the style (agents run their own executors),
    but local plotting code can call this helper to get consistent visuals.
    """
    try:
        import matplotlib as mpl
        mpl.rcParams.update({
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#0B2D5A",
            "axes.labelcolor": "#0B2D5A",
            "xtick.color": "#0B2D5A",
            "ytick.color": "#0B2D5A",
            "text.color": "#0B2D5A",
            "lines.linewidth": 2.0,
            "lines.markeredgewidth": 0.5,
            "font.size": 10,
            "axes.titleweight": "bold",
        })
    except Exception:
        # Matplotlib may not be available in all runtimes; fail silently.
        pass


def display_image_gallery(path: str = "images", cols: int = 3, caption_prefix: str = "Generated Visualization"):
    """Display PNG images from `path` in a tiled gallery using `cols` columns.

    Images are sorted by modification time (newest first).
    """
    p = Path(path)
    if not p.exists() or not p.is_dir():
        st.warning("Visualization directory not found.")
        return

    png_files = sorted([f for f in p.glob("img_*.png") if f.is_file()], key=lambda f: f.stat().st_mtime, reverse=True)
    if not png_files:
        st.warning("No visualization images found in the images directory.")
        return

    # Create rows of columns
    row = []
    for i, img in enumerate(png_files):
        if i % cols == 0:
            row = st.columns(cols)

        col = row[i % cols]
        with col:
            try:
                st.image(str(img), caption=f"{caption_prefix} ({img.name})", use_column_width=True)
            except Exception:
                st.image(str(img))

    # Optionally add a small legend / credit
    st.markdown("<div style='font-size:12px;color:#6b7177'>Visuals styled with Sky-inspired palette.</div>", unsafe_allow_html=True)
