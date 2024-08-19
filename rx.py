import pyaudio
import wave
import time
import audioop
import os
import asyncio
import aiohttp
import logging
from pydub import AudioSegment
from pydub.silence import split_on_silence
from pydub.effects import low_pass_filter, high_pass_filter, compress_dynamic_range
from threading import Thread
import queue


# Adjust this value based on your environment
THRESHOLD = int(os.getenv("THRESHOLD", 10))
FADE_OUT_DURATION = int(os.getenv("FADE_OUT_DURATION", 250))
GAIN = int(os.getenv("GAIN", 20))
CHUNK = int(os.getenv("CHUNK", 1024))
FORMAT = pyaudio.paInt16
CHANNELS = int(os.getenv("CHANNELS", 1))
RATE = int(os.getenv("RATE", 44100))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "recordings")
# Silence duration threshold in ms to split files
SILENCE_MIN_DURATION = int(os.getenv("SILENCE_MIN_DURATION", 1000))
# Minimum speech duration to keep in ms
MIN_SPEECH_DURATION = int(os.getenv("MIN_SPEECH_DURATION", 1000))
# Lowpass filter frequency in Hz
LOWPASS_FREQ = int(os.getenv("LOWPASS_FREQ", 3000))
# Highpass filter frequency in Hz
HIGHPASS_FREQ = int(os.getenv("HIGHPASS_FREQ", 300))
# Replace with your Telegram bot token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Replace with your chat ID
CHAT_ID = os.getenv("CHAT_ID")
# Replace with the topic ID (if applicable)
MESSAGE_THREAD_ID = os.getenv("MESSAGE_THREAD_ID", None)


# Initialize audio
audio = pyaudio.PyAudio()

# Queue to handle audio chunks
q = queue.Queue()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# Function to continuously record audio
def record_audio():
    stream = audio.open(
        format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK
    )

    while True:
        data = stream.read(CHUNK)
        q.put(data)


# Async function to upload files as Telegram voice messages
async def upload_file(filepath):
    try:
        logging.info(f"Starting upload for {filepath}...")
        async with aiohttp.ClientSession() as session:
            with open(filepath, "rb") as f:
                form_data = aiohttp.FormData()
                form_data.add_field("chat_id", CHAT_ID)
                if MESSAGE_THREAD_ID:
                    form_data.add_field("message_thread_id", str(MESSAGE_THREAD_ID))
                form_data.add_field("voice", f, filename=os.path.basename(filepath))
                form_data.add_field("disable_notification", "true")

                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVoice"
                async with session.post(url, data=form_data) as response:
                    if response.status == 200:
                        logging.info(
                            f"Uploaded {os.path.basename(filepath)} successfully as a voice message."
                        )
                        os.remove(filepath)  # Delete file after successful upload
                        logging.info(f"Deleted {filepath} after upload.")
                    else:
                        logging.error(
                            f"Failed to upload {os.path.basename(filepath)}. Status: {response.status}"
                        )
    except Exception as e:
        logging.error(f"Error uploading {filepath}: {e}")


# Async function to process audio
async def process_audio():
    audio_frames = []

    while True:
        try:
            if not q.empty():
                data = q.get()
                rms = audioop.rms(data, 2)  # Calculate volume level

                if rms >= THRESHOLD:
                    audio_frames.append(data)
                else:
                    if len(audio_frames) > 0:
                        # Save raw audio to file
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        raw_filename = f"{timestamp}.wav"
                        raw_filepath = os.path.join(OUTPUT_DIR, raw_filename)

                        wf = wave.open(raw_filepath, "wb")
                        wf.setnchannels(CHANNELS)
                        wf.setsampwidth(audio.get_sample_size(FORMAT))
                        wf.setframerate(RATE)
                        wf.writeframes(b"".join(audio_frames))
                        wf.close()

                        logging.info(f"Saved raw audio to {raw_filepath}.")

                        # Process audio to remove silence, apply filters, and split
                        audio_segment = AudioSegment.from_wav(raw_filepath)

                        # Apply highpass and lowpass filters (twice for 12db/oct)
                        audio_segment = high_pass_filter(audio_segment, HIGHPASS_FREQ)
                        audio_segment = high_pass_filter(audio_segment, HIGHPASS_FREQ)
                        audio_segment = low_pass_filter(audio_segment, LOWPASS_FREQ)
                        audio_segment = low_pass_filter(audio_segment, LOWPASS_FREQ)

                        # Apply fade out to reduce noise burst at the end
                        audio_segment = audio_segment.fade_out(FADE_OUT_DURATION)

                        # Apply dynamic range compression (including peak compression)
                        audio_segment = compress_dynamic_range(
                            audio_segment,
                            attack=0.1,
                            release=10,
                            threshold=-10,
                            ratio=20,
                        )

                        # Apply gain
                        audio_segment = audio_segment.apply_gain(GAIN)

                        # Split audio based on silence
                        chunks = split_on_silence(
                            audio_segment,
                            min_silence_len=SILENCE_MIN_DURATION,
                            silence_thresh=audio_segment.dBFS - 16,
                            keep_silence=200,
                        )

                        logging.info(f"Split audio into {len(chunks)} chunks.")

                        # Save each chunk separately, convert to OGG, and upload
                        for i, chunk in enumerate(chunks):
                            if len(chunk) >= MIN_SPEECH_DURATION:
                                output_filename = f"{timestamp}_part_{i}.ogg"
                                output_filepath = os.path.join(
                                    OUTPUT_DIR, output_filename
                                )
                                chunk.export(
                                    output_filepath, format="ogg", codec="libopus"
                                )

                                logging.info(
                                    f"Converted and saved chunk to {output_filepath}."
                                )

                                # Asynchronously upload the file
                                asyncio.create_task(upload_file(output_filepath))

                        # Clean up raw file after processing
                        os.remove(raw_filepath)
                        logging.info(f"Deleted raw file {raw_filepath}.")

                        # Clear frames for next segment
                        audio_frames = []
            await asyncio.sleep(
                0.01
            )  # Non-blocking sleep to yield control to the event loop

        except Exception as e:
            logging.error(f"Error processing audio: {e}")


# Main function to start recording and processing
async def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # Start recording in a separate thread
    record_thread = Thread(target=record_audio)
    record_thread.start()

    # Run the processing loop in the event loop
    await process_audio()


if __name__ == "__main__":
    # Create and run the event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Recording stopped.")
