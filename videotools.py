import yt_dlp
import argparse
import os
import sys
import shutil

def download_audio(stream_url, output_filename):
    """
    Downloads audio from a stream, saving to a temporary file first,
    and then renaming upon successful completion.
    Redirects all yt-dlp output to progress.log.
    """
    log_file_path = 'progress.log'
    base_filename = output_filename.rsplit('.', 1)[0]
    temp_filename = f"{base_filename}.part"
    final_filename = f"{base_filename}.mp3"

    # If the final file already exists, we're done.
    if os.path.exists(final_filename):
        print(f"'{final_filename}' already exists. Skipping download.")
        return final_filename
        
    # If a partial file exists, remove it to start fresh.
    if os.path.exists(temp_filename):
        os.remove(temp_filename)

    with open(log_file_path, 'a', encoding='utf-8') as log_file:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = log_file
        sys.stderr = log_file

        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{temp_filename}',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'noplaylist': True,
                'progress': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([stream_url])
            
            # After download, the temp file will have an extension like .mp3 or .webm
            # We need to find it and rename it to the final mp3 filename.
            # Note: The postprocessor ensures the final output is mp3.
            temp_output_file = f"{temp_filename}.mp3"

            if os.path.exists(temp_output_file):
                shutil.move(temp_output_file, final_filename)
                # Restore stdout to print success message
                sys.stdout = original_stdout
                print(f"Successfully downloaded and moved audio to {final_filename}")
                return final_filename
            else:
                # This case might happen if the downloaded file had a different extension
                # before ffmpeg converted it. Let's try to find it.
                for ext in ['.webm', '.m4a', '.ogg']:
                    if os.path.exists(f"{temp_filename}{ext}"):
                        shutil.move(f"{temp_filename}{ext}", final_filename)
                        sys.stdout = original_stdout
                        print(f"Successfully downloaded and moved audio to {final_filename}")
                        return final_filename
                
                # If we still can't find it, something went wrong.
                print(f"Error: Post-processing failed. Could not find temp file for {temp_filename}")
                return None

        except Exception as e:
            print(f"An error occurred during download: {e}")
            return None
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Download audio from a video stream.")
    parser.add_argument(
        '--url',
        type=str,
        default="https://archive-stream.granicus.com/OnDemand/_definst_/mp4:archive/sanfrancisco/sanfrancisco_df708991-dcbb-4e71-bc38-cbd85d20743c.mp4/playlist.m3u8",
        help="The URL of the video stream to download."
    )
    parser.add_argument(
        '--output',
        type=str,
        default="temp_audio.mp3",
        help="The desired final output filename (with extension)."
    )
    args = parser.parse_args()

    print(f"--- Testing Audio Download ---")
    print(f"URL: {args.url}")
    print(f"Output will be saved to {args.output}")
    print(f"All verbose download output is being redirected to progress.log")

    result_path = download_audio(args.url, args.output)

    if result_path:
        print(f"\n--- SUCCESS ---")
        print(f"Audio successfully downloaded to: {result_path}")
    else:
        print(f"\n--- FAILURE ---")
        print(f"Audio download failed. Check progress.log for details.")
