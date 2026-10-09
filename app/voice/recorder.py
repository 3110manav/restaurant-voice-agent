"""Push-to-talk mic recording: press Enter to start, Enter again to stop."""
import queue
import wave

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Whisper's native rate
CHANNELS = 1


def record_until_enter(output_path: str) -> None:
    frames_queue: queue.Queue = queue.Queue()

    def callback(indata, frames, time_info, status):
        frames_queue.put(indata.copy())

    input("Press Enter to start recording...")
    print("Recording... press Enter to stop.")
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", callback=callback):
        input()

    chunks = []
    while not frames_queue.empty():
        chunks.append(frames_queue.get())
    audio = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, CHANNELS), dtype="int16")

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
