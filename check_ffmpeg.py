import shutil
import sys

def check_ffmpeg_installed():
    """
    Checks if ffmpeg is installed and in the system's PATH.
    If not, it prints an error message and exits the script.
    """
    print("--- Checking for FFmpeg ---")
    if shutil.which("ffmpeg") is None:
        print("\nError: FFmpeg is not installed or not found in your system's PATH.")
        print("FFmpeg is required for audio processing (e.g., converting video to MP3).")
        print("\nPlease install FFmpeg and ensure it's accessible from your terminal.")
        print("  - On macOS: `brew install ffmpeg` (if using Homebrew)")
        print("  - On Windows: Download from https://ffmpeg.org/download.html and add the bin directory to your system's PATH.")
        sys.exit(1)
    else:
        print("✅ FFmpeg found successfully.")
        # Optional: print the path
        # print(f"FFmpeg path: {shutil.which('ffmpeg')}")

if __name__ == "__main__":
    check_ffmpeg_installed()
    print("\nTest complete.")

