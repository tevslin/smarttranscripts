from tenacity import retry, stop_after_attempt, wait_fixed, after_log, before_log, RetryError
import functools

import httpx
from deepgram import DeepgramClient
import os
import pickle
import logging
import argparse

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),                  # Stop after 3 attempts
    wait=wait_fixed(2),                          # Wait 2 seconds between retries
    before=before_log(logger, logging.INFO),     # Log before each retry attempt
    after=after_log(logger, logging.INFO)        # Log after each retry attempt
    )
def call_deepgram(func, *args, **kwargs):
    logger.info(f"call deepgram called")
    response=func(*args,**kwargs)
    logger.info('good return')
    return response

def transcribe_audio(input_file, output_file=None, topics=False):
    """
    This version runs with deepgram-sdk>=5.0.0.
    """
    if 'DEEPGRAM_API_KEY' not in os.environ:
        from dotenv import load_dotenv
        load_dotenv()
    assert 'DEEPGRAM_API_KEY' in os.environ,"no API Key for Deepgram!"

    # Initialize the client (v5 style) with custom timeout via httpx_client
    deepgram: DeepgramClient = DeepgramClient(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        httpx_client=httpx.Client(timeout=httpx.Timeout(600.0, connect=100.0))
    )

    with open(input_file, "rb") as file:
        buffer_data = file.read()

    # Define the API call using v5 syntax
    # Note: Options are now passed as kwargs directly
    transcribe_func = functools.partial(
        deepgram.listen.v1.media.transcribe_file,
        request=buffer_data,
        model="nova-2-meeting",
        topics=topics,
        utterances=True,
        punctuate=True,
        diarize=True,
        smart_format=True,
        paragraphs=True,
    )

    response = call_deepgram(transcribe_func)
    logger.info("returned from deepgram")

    if output_file:
        with open(output_file,'w') as f:
            f.write(response.model_dump_json(indent=4))
    
    return response.model_dump_json(indent=4)
    
def main(audio: str, output: str = None, doprint: bool = False):
    """Main entry point."""
    result_json = transcribe_audio(audio, output)
    if doprint:
        print(result_json)
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio using Deepgram SDK v5.")
    parser.add_argument("--audio", required=True, help="Path to input audio file.")
    parser.add_argument("--output", help="Optional path to write JSON output.")
    parser.add_argument("--print",dest="doprint",action="store_true", help="Print the JSON result to stdout.")
    args = parser.parse_args()

    main(audio=args.audio, output=args.output, doprint=args.doprint)
