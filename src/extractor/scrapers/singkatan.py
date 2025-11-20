"""
SNI Abbreviation Image Downloader

Downloads SNI (Standar Nasional Indonesia) abbreviation images from bsn.go.id
and converts them to PDF format for OCR processing.

Key Features:
- Multiple retry loops: up to 5 attempts with 3-second waits between retries
- Each retry loop only attempts currently failed images
- Comprehensive error reporting and validation
- Progress tracking and rate limiting
"""

import os
import time
from typing import List, Tuple

import img2pdf
import requests
from PIL import Image
from utils.paths import ensure_output_dirs, get_datas_dir, get_image_output_path
from utils.progress import progress_manager

# Configuration
SNI_DOC_ID = "SNI_7657-2023"
DOWNLOAD_DELAY = 1.0  # seconds between downloads


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
    except Exception as e:
        print(f"\nFailed to validate image: {e}")
        return False




def download_singkatan_images() -> Tuple[bool, List[str]]:
    """
    Download all 45 SNI abbreviation images with multiple retry loops.

    First pass: Download all images.
    If any failed, wait 3 seconds and retry failed images.
    If still any failed, wait 3 seconds and retry again.
    Continue up to max 5 loops total.
    Each retry loop only attempts the currently failed images.

    Returns:
        Tuple[bool, List[str]]: (success, failed_images)
        - success: True if all 45 images downloaded and converted to PDF successfully
        - failed_images: List of image filenames that ultimately failed to download
    """
    base_url = "https://akses-sni.bsn.go.id/dokumen/2023/SNI%207657-2023/files/large/"

    # Setup directories
    ensure_output_dirs()
    images_dir = get_image_output_path(SNI_DOC_ID)
    print(f"Downloading SNI images to: {images_dir}")
    os.makedirs(images_dir, exist_ok=True)

    # Execute download process with two-pass retry logic
    success, failed_images = _execute_download_process(base_url, images_dir)

    # Convert to PDF if download succeeded
    if success:
        pdf_success = _convert_images_to_pdf(images_dir)
        if not pdf_success:
            return False, ["PDF conversion failed"]

    return success, failed_images


def _execute_download_process(base_url: str, images_dir: str) -> Tuple[bool, List[str]]:
    """
    Execute the download process with multiple retry loops:
    1. First pass: Download all images
    2. If any failed, wait 3 seconds and retry failed images
    3. If still any failed, wait 3 seconds and retry again
    4. Continue up to max 5 loops total
    5. Each retry loop only attempts the currently failed images

    Args:
        base_url: Base URL for image downloads
        images_dir: Directory to save downloaded images

    Returns:
        Tuple[bool, List[str]]: (all_succeeded, failed_images)
    """
    max_retries = 5
    failed_images = []

    for attempt in range(max_retries):
        if attempt == 0:
            # First pass: download all images
            print("Starting first pass: downloading all images...")
            images_to_download = [f"{i}.jpg" for i in range(1, 46)]
            description = "Downloading images (first pass)"
        else:
            # Subsequent passes: retry only failed images
            if not failed_images:
                break  # No more failures, success
            print(f"\nRetry loop {attempt}: waiting 3 seconds then retrying {len(failed_images)} failed images...")
            time.sleep(3)
            images_to_download = failed_images.copy()
            description = f"Retrying failed images (attempt {attempt})"

        failed_images = []  # Reset for this attempt

        with progress_manager.download_progress(
            total_items=len(images_to_download), description=description
        ) as progress_ctx:
            for filename in images_to_download:
                filepath = os.path.join(images_dir, filename)

                # Skip already downloaded valid images (only for first pass)
                if attempt == 0 and os.path.exists(filepath) and validate_image(filepath):
                    progress_ctx.advance(1)
                    continue

                # Attempt download
                success = _download_single_image(base_url, filename, filepath)
                progress_ctx.advance(1)

                if not success:
                    failed_images.append(filename)

                # Rate limiting
                time.sleep(DOWNLOAD_DELAY)

        if not failed_images:
            print(f"All images downloaded successfully in {'first pass' if attempt == 0 else f'retry loop {attempt}'}!")
            return True, []

    # If we get here, all retries exhausted
    print(f"Failed to download {len(failed_images)} images after {max_retries} attempts: {', '.join(failed_images)}")
    return False, failed_images




def _download_single_image(base_url: str, filename: str, filepath: str) -> bool:
    """
    Download a single image.

    Args:
        base_url: Base URL for downloads
        filename: Image filename (e.g., "1.jpg")
        filepath: Full path where to save the image

    Returns:
        True if download and validation succeeded, False otherwise
    """
    url = f"{base_url}{filename}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Save the file
        with open(filepath, "wb") as f:
            f.write(response.content)

        # Validate the downloaded image
        if validate_image(filepath):
            return True  # Success
        else:
            print(f"\nDownloaded {filename} is invalid (corrupted file)")
            # Clean up failed download
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass  # Ignore cleanup errors
            return False

    except requests.RequestException as e:
        print(f"\nFailed to download {filename}: {e}")
        return False


def _convert_images_to_pdf(images_dir: str) -> bool:
    """
    Convert downloaded images to PDF format.

    Args:
        images_dir: Directory containing the downloaded images

    Returns:
        True if PDF conversion succeeded, False otherwise
    """
    image_files = []
    for i in range(1, 46):
        filepath = os.path.join(images_dir, f"{i}.jpg")
        if os.path.exists(filepath):
            image_files.append(filepath)

    image_files.sort(key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))

    if not image_files:
        print("No images found to convert to PDF")
        return False

    pdf_path = os.path.join(get_datas_dir(), f"{SNI_DOC_ID}.pdf")
    try:
        pdf_bytes = img2pdf.convert(image_files)
        if pdf_bytes is not None:
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            print(f"Successfully created PDF: {pdf_path}")
            return True
        else:
            print("Failed to convert images to PDF")
            return False
    except Exception as e:
        print(f"Failed to create PDF: {e}")
        return False


if __name__ == "__main__":
    success, failed = download_singkatan_images()
    if success:
        print("Download completed successfully!")
    else:
        print(f"Download failed. Failed images: {failed}")
        exit(1)
