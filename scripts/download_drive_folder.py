import sys
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.request


MAX_SIZE = 2 * 1024 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def get_folder_id(url):
    parsed = urlparse(url)

    if parsed.netloc not in (
        "drive.google.com",
        "www.drive.google.com",
    ):
        raise ValueError("This is not a Google Drive URL.")

    parts = parsed.path.strip("/").split("/")

    if "folders" in parts:
        index = parts.index("folders")

        if index + 1 < len(parts):
            return parts[index + 1]

    query = parse_qs(parsed.query)

    if "id" in query and query["id"]:
        return query["id"][0]

    raise ValueError("Could not find a Google Drive folder ID.")


def download_folder_zip(folder_id, output_path):
    urls = [
        (
            "https://drive.google.com/"
            "uc?export=download&id="
            + folder_id
        ),
        (
            "https://drive.usercontent.google.com/"
            "download?id="
            + folder_id
            + "&export=download&confirm=t"
        ),
    ]

    last_error = None

    for url in urls:
        print(f"Trying Google Drive download endpoint...")

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120 Safari/537.36"
                )
            },
        )

        downloaded = 0

        try:
            with urllib.request.urlopen(
                request,
                timeout=120,
            ) as response:

                content_type = (
                    response.headers
                    .get("Content-Type", "")
                    .lower()
                )

                content_length = response.headers.get(
                    "Content-Length"
                )

                if content_length:
                    if int(content_length) > MAX_SIZE:
                        raise ValueError(
                            "Google Drive folder download "
                            "exceeds the 2 GB limit."
                        )

                with open(output_path, "wb") as output:
                    while True:
                        chunk = response.read(CHUNK_SIZE)

                        if not chunk:
                            break

                        downloaded += len(chunk)

                        if downloaded > MAX_SIZE:
                            raise ValueError(
                                "Google Drive folder download "
                                "exceeded the 2 GB limit."
                            )

                        output.write(chunk)

                if downloaded == 0:
                    raise ValueError(
                        "Google Drive returned an empty response."
                    )

                if "text/html" in content_type:
                    raise ValueError(
                        "Google Drive returned a webpage "
                        "instead of a folder archive."
                    )

                print(
                    f"Folder archive downloaded: {output_path}"
                )
                print(
                    f"Downloaded bytes: {downloaded}"
                )

                return

        except Exception as error:
            output_path.unlink(missing_ok=True)
            last_error = error
            print(f"Endpoint failed: {error}")

    raise RuntimeError(
        "Google Drive folder download failed. "
        f"Last error: {last_error}"
    )


def extract_videos(zip_path, output_directory):
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    video_extensions = {
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
        ".avi",
        ".m4v",
    }

    extracted = []

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():

            if member.is_dir():
                continue

            source_name = Path(member.filename)

            if source_name.suffix.lower() not in video_extensions:
                continue

            filename = source_name.name

            if not filename:
                continue

            output_path = output_directory / filename

            with archive.open(member) as source:
                with open(output_path, "wb") as target:

                    while True:
                        chunk = source.read(CHUNK_SIZE)

                        if not chunk:
                            break

                        target.write(chunk)

            extracted.append(output_path)

    return extracted


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/"
            "download_drive_folder.py "
            "<google_drive_folder_url> "
            "<output_directory>"
        )
        sys.exit(1)

    folder_url = sys.argv[1]
    output_directory = Path(sys.argv[2])

    folder_id = get_folder_id(folder_url)

    print(f"Google Drive folder ID: {folder_id}")

    archive_path = (
        output_directory.parent / "drive_folder.zip"
    )

    download_folder_zip(
        folder_id,
        archive_path,
    )

    videos = extract_videos(
        archive_path,
        output_directory,
    )

    archive_path.unlink(
        missing_ok=True
    )

    if not videos:
        raise ValueError(
            "No supported video files were found "
            "inside the Google Drive folder."
        )

    print(
        f"Found {len(videos)} video(s):"
    )

    for video in videos:
        print(f"  {video}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            f"Folder download failed: {error}"
        )
        sys.exit(1)
