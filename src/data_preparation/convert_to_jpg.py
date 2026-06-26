from pathlib import Path
import argparse
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
register_heif_opener()

SUPPORTED_EXTENSIONS = {
    ".heic",
}

def convert_images_to_jpg(input_dir: Path, quality: int = 95) -> None:
    base_dir = input_dir.resolve()

    input_heic_dir = base_dir / "heic"
    output_dir = base_dir / "jpg"
    output_dir.mkdir(exist_ok=True)

    image_paths = [
        path for path in input_heic_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    print(f"Input directory: {input_heic_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Found {len(image_paths)} image(s).")

    converted = 0
    failed = 0

    for image_path in sorted(image_paths):
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")

            output_path = output_dir / f"{image_path.stem}.jpg"

            img.save(
                output_path,
                format="JPEG",
                quality=quality,
                optimize=True,
            )

            converted += 1
            print(f"Converted: {image_path.name} -> jpg/{output_path.name}")

    print("\nDone.")
    print(f"Converted: {converted}")
    print(f"Failed: {failed}")

def main():
    parser = argparse.ArgumentParser(
        description="Convert all images in a directory to JPG."
    )

    parser.add_argument(
        "input_dir",
        type=str,
        help="Path to the directory containing images.",

    )

    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="JPG quality from 1 to 100. Default: 95.",
    )

    args = parser.parse_args()
    convert_images_to_jpg(
        input_dir=Path(args.input_dir),
        quality=args.quality,
    )

if __name__ == "__main__":
    main()