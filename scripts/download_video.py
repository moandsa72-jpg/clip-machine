import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


MAX_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB
CHUNK_SIZE = 1024 * 1024  # 1 MB


def download_video(url, output_path):
    parsed = urlparse(url)

    if parsed.scheme != "https":
        raise ValueError("Only HTTPS video URLs are accepted.")

    if not parsed.hostname:
        raise ValueError("The supplied URL is invalid.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ClipMachine/1.0"},
    )

    downloaded = 0

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if (
                "text/html" in content_type
                or "application/json" in content_type
            ):
                raise ValueError(
                    "This URL returned a webpage, not a direct video. "
                    "Use a direct video download URL."
                )

            content_length = response.headers.get("Content-Length")

            if content_length and int(content_length) > MAX_SIZE:
                raise ValueError("Video exceeds the 2 GB limit.")

            with open(output_path, "wb") as output:
                while True:
                    chunk = response.read(CHUNK_SIZE)

                    if not chunk:
                        break

                    downloaded += len(chunk)

                    if downloaded > MAX_SIZE:
                        raise ValueError(
                            "Video exceeded the 2 GB download limit."
                        )

                    output.write(chunk)

    except Exception:
        if output_path.exists():
            output_path.unlink()
        raise

    if downloaded == 0:
        output_path.unlink(missing_ok=True)
        raise ValueError("The downloaded file is empty.")

    print(f"Download complete: {output_path}")
    print(f"Downloaded bytes: {downloaded}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/download_video.py "
            "<https_video_url> <output_path>"
        )
        sys.exit(1)

    download_video(sys.argv[1], sys.argv[2])
