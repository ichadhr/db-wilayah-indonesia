"""
Singkatan Scraper - SNI Abbreviation Data Extractor

This module downloads and processes SNI (Standar Nasional Indonesia) abbreviation
images from bsn.go.id, converting them to PDF format for further processing.
"""

import os
import requests
import time
from utils.progress import progress_manager
from utils.paths import get_datas_dir, get_image_output_path, ensure_output_dirs
import img2pdf
from PIL import Image

# Constants
SNI_DOC_ID = "SNI_7657-2023"
DOWNLOAD_DELAY = 1  # seconds between downloads
RETRY_DELAY = 1     # seconds between retries


def validate_image(filepath: str) -> bool:
    """
    Validate if an image file can be opened and read correctly.

    Args:
        filepath: Path to the image file

    Returns:
        True if image is valid, False otherwise
    """
    try:
        with Image.open(filepath) as img:
            img.verify()  # Verify the image file
        return True
    except Exception:
        return False


def download_singkatan_images():
    base_url = "https://akses-sni.bsn.go.id/dokumen/2023/SNI%207657-2023/files/large/"
    # Ensure output directories exist
    ensure_output_dirs()
    images_dir = get_image_output_path(SNI_DOC_ID)  # Get the images directory path with subfolder
    print(images_dir)
    os.makedirs(images_dir, exist_ok=True)

    with progress_manager.download_progress(total_items=45, description="Downloading images") as progress_ctx:
        for i in range(1, 46):
            filename = f"{i}.jpg"
            filepath = os.path.join(images_dir, filename)

            # Skip if file exists and is valid
            if os.path.exists(filepath) and validate_image(filepath):
                progress_ctx.advance(1)
                continue

            # Download with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    url = f"{base_url}{i}.jpg"
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()

                    # Save the file
                    with open(filepath, 'wb') as f:
                        f.write(response.content)

                    # Validate the downloaded image
                    if validate_image(filepath):
                        break  # Success
                    else:
                        print(f"Downloaded {filename} is invalid, retrying... (attempt {attempt + 1}/{max_retries})")
                        if attempt == max_retries - 1:
                            print(f"Failed to download valid {filename} after {max_retries} attempts")
                        else:
                            time.sleep(RETRY_DELAY)  # Delay before retry
                        continue

                except requests.RequestException as e:
                    print(f"Failed to download {filename} (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        print(f"Giving up on {filename}")
                    else:
                        time.sleep(RETRY_DELAY)  # Delay before retry

            progress_ctx.advance(1)

            # Add delay between different images to be respectful to the server
            time.sleep(DOWNLOAD_DELAY)

    # Convert downloaded images to PDF
    image_files = []
    for i in range(1, 46):
        filepath = os.path.join(images_dir, f"{i}.jpg")
        if os.path.exists(filepath):
            image_files.append(filepath)

    image_files.sort(key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))

    if image_files:
        pdf_path = os.path.join(get_datas_dir(), f"{SNI_DOC_ID}.pdf")
        try:
            pdf_bytes = img2pdf.convert(image_files)
            if pdf_bytes is not None:
                with open(pdf_path, "wb") as f:
                    f.write(pdf_bytes)
                print(f"Successfully created PDF: {pdf_path}")
            else:
                print("Failed to convert images to PDF")
        except Exception as e:
            print(f"Failed to create PDF: {e}")
    else:
        print("No images found to convert to PDF")

if __name__ == "__main__":
    download_singkatan_images()