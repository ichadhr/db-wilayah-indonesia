"""
SNI Abbreviation Image Downloader

Downloads SNI (Standar Nasional Indonesia) abbreviation images from bsn.go.id
and converts them to PDF format for OCR processing.

Key Features:
- Intelligent retry logic based on error types (network vs server errors)
- Full process re-run strategy for failed downloads
- Comprehensive error reporting and validation
- Progress tracking and rate limiting
"""

import os
import time
from typing import List, Optional, Tuple

import img2pdf
import requests
from PIL import Image
from utils.paths import ensure_output_dirs, get_datas_dir, get_image_output_path
from utils.progress import progress_manager

# Configuration
SNI_DOC_ID = "SNI_7657-2023"
DOWNLOAD_DELAY = 1.0  # seconds between downloads
RETRY_DELAY = 1.0     # seconds between retries
MAX_NETWORK_RETRIES = 5  # Network errors: more tolerant
MAX_SERVER_RETRIES = 3   # Server errors: less tolerant


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
        print(f"Failed to validate image: {e}")
        return False


def classify_error(error: Exception, response: Optional[requests.Response] = None) -> str:
    """
    Classify the type of error that occurred during download.

    Args:
        error: The exception that occurred
        response: The HTTP response (if available)

    Returns:
        Error classification: 'network', 'server', or 'unknown'
    """
    if response is not None:
        # HTTP status code indicates server error
        if 400 <= response.status_code < 600:
            return 'server'

    # Check exception types for network errors
    if isinstance(error, (requests.ConnectionError, requests.Timeout, requests.TooManyRedirects)):
        return 'network'

    # DNS resolution failures
    if isinstance(error, requests.RequestException):
        error_msg = str(error).lower()
        if any(keyword in error_msg for keyword in ['name resolution', 'dns', 'connection', 'timeout']):
            return 'network'

    return 'unknown'


def should_retry_error(error_type: str, current_attempt: int) -> bool:
    """
    Determine if an error should be retried based on its type and current attempt count.

    Args:
        error_type: The classified error type ('network', 'server', 'unknown')
        current_attempt: Current attempt number (0-based)

    Returns:
        True if the error should be retried, False otherwise
    """
    if error_type == 'network':
        return current_attempt < MAX_NETWORK_RETRIES
    elif error_type == 'server':
        return current_attempt < MAX_SERVER_RETRIES
    else:
        # Unknown errors get minimal retries
        return current_attempt < 1


def download_singkatan_images() -> Tuple[bool, List[str]]:
    """
    Download all 45 SNI abbreviation images with intelligent retry logic.

    This function implements a full-process retry strategy where failed downloads
    trigger a complete re-run of the entire download process, allowing previously
    failed images another chance to download.

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

    # Execute download process with full retries
    success, failed_images = _execute_download_process(base_url, images_dir)

    # Convert to PDF if download succeeded
    if success:
        pdf_success = _convert_images_to_pdf(images_dir)
        if not pdf_success:
            return False, ["PDF conversion failed"]

    return success, failed_images


def _execute_download_process(base_url: str, images_dir: str) -> Tuple[bool, List[str]]:
    """
    Execute the complete download process with full-process retry logic.

    Args:
        base_url: Base URL for image downloads
        images_dir: Directory to save downloaded images

    Returns:
        Tuple[bool, List[str]]: (all_succeeded, failed_images)
    """
    failed_images: List[str] = []
    max_process_attempts = 5

    for process_attempt in range(max_process_attempts):
        attempt_num = process_attempt + 1

        if process_attempt > 0:
            print(f"\nRetrying complete download process (attempt {attempt_num}/{max_process_attempts})")
            failed_images = []  # Reset for new attempt

        # Download all images in this attempt
        attempt_failed = _download_all_images_in_attempt(
            base_url, images_dir, attempt_num, failed_images
        )

        # Check success
        if not attempt_failed:
            print("All images downloaded successfully!")
            return True, []

        # Prepare for next attempt or give up
        if attempt_num < max_process_attempts:
            print(f"Failed to download {len(failed_images)} images: {', '.join(failed_images)}")
            print(f"Will retry entire process in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
        else:
            print(f"Failed to download images after {max_process_attempts} complete attempts")
            print(f"Permanently failed images: {', '.join(failed_images)}")

    return False, failed_images


def _download_all_images_in_attempt(
    base_url: str, images_dir: str, attempt_num: int, failed_images: List[str]
) -> bool:
    """
    Download all 45 images in a single attempt.

    Returns:
        True if any images failed (need to retry process), False if all succeeded
    """
    has_failures = False

    with progress_manager.download_progress(
        total_items=45, description=f"Downloading images (attempt {attempt_num})"
    ) as progress_ctx:
        for i in range(1, 46):
            filename = f"{i}.jpg"
            filepath = os.path.join(images_dir, filename)

            # Skip already downloaded valid images
            if os.path.exists(filepath) and validate_image(filepath):
                progress_ctx.advance(1)
                continue

            # Attempt download
            success = _download_single_image_with_retry(base_url, filename, filepath)
            progress_ctx.advance(1)

            if not success:
                failed_images.append(filename)
                has_failures = True

            # Rate limiting
            time.sleep(DOWNLOAD_DELAY)

    return has_failures


def _download_single_image_with_retry(base_url: str, filename: str, filepath: str) -> bool:
    """
    Download a single image with intelligent retry logic based on error classification.

    Network errors (connection issues, timeouts) get up to 5 retries.
    Server errors (4xx/5xx HTTP codes) get up to 3 retries.

    Args:
        base_url: Base URL for downloads
        filename: Image filename (e.g., "1.jpg")
        filepath: Full path where to save the image

    Returns:
        True if download and validation succeeded, False otherwise
    """
    url = f"{base_url}{filename}"
    attempt = 0

    while True:
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
                error_type = 'validation'
                error_msg = f"Downloaded {filename} is invalid (corrupted file)"

        except requests.RequestException as e:
            error_type = classify_error(e, getattr(e, 'response', None))
            error_msg = str(e)

        # Check if we should retry this error
        if should_retry_error(error_type, attempt):
            attempt += 1
            print(f"Failed to download {filename} ({error_type} error, attempt {attempt}): {error_msg}")
            time.sleep(RETRY_DELAY)
            continue
        else:
            print(f"Giving up on {filename} after {attempt + 1} attempts ({error_type} error): {error_msg}")
            # Clean up failed download
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass  # Ignore cleanup errors
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
