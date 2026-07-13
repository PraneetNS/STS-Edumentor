import os
import site
import ctypes

import spaces
import torch
from faster_whisper import WhisperModel


def _configure_cuda_libraries():
    site_packages = site.getsitepackages()[0]

    library_dirs = [
        os.path.join(site_packages, "nvidia", "cublas", "lib"),
        os.path.join(site_packages, "nvidia", "cudnn", "lib"),
    ]

    existing = os.environ.get("LD_LIBRARY_PATH", "")

    os.environ["LD_LIBRARY_PATH"] = ":".join(
        library_dirs + ([existing] if existing else [])
    )

    for directory in library_dirs:
        if not os.path.isdir(directory):
            continue

        for filename in os.listdir(directory):
            if (
                filename.startswith("libcublas.so")
                or filename.startswith("libcudnn.so")
            ):
                try:
                    ctypes.CDLL(
                        os.path.join(directory, filename),
                        mode=ctypes.RTLD_GLOBAL,
                    )
                except OSError:
                    pass


_configure_cuda_libraries()


@spaces.GPU(duration=120)
def transcribe_audio(audio_path: str) -> dict:
    if not audio_path:
        return {
            "text": "",
            "language": "unknown",
        }

    model = WhisperModel(
        "base.en",
        device="cuda",
        compute_type="float16",
    )

    segments, info = model.transcribe(
        audio_path,
        language="en",
        task="transcribe",
        beam_size=2,
        vad_filter=True,
        condition_on_previous_text=False,
    )

    text = " ".join(
        segment.text.strip()
        for segment in segments
        if segment.text.strip()
    )

    del model
    torch.cuda.empty_cache()

    return {
        "text": text,
        "language": info.language,
    }