import os
import sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, PngImagePlugin
import piexif
import shutil

def extract_png_metadata(png_file):
    """Extracts metadata from a PNG file."""
    try:
        with Image.open(png_file) as img:
            if isinstance(img, PngImagePlugin.PngImageFile):
                metadata = img.info.get("parameters", "") #1:sd1111 or forge png
                #--------
                #T.B.C.:変換後のファイルはComfyUIで開けないが、一応exifコメントには格納しておく用に対応
                #--------
                if not metadata:
                    metadata = img.info.get("prompt", "") #2:comfyUI png
                return metadata
    except Exception as e:
        print(f"Error reading PNG metadata: {e}")
    return ""

def add_exif_user_comment(output_file, metadata):
    """Adds metadata to the Exif UserComment field of a JPEG file."""
    try:
        exif_dict = piexif.load(output_file)

        if "Exif" not in exif_dict:
            exif_dict["Exif"] = {}
        #--------
        #T.B.C.:現在の動作合わせの良くない対応。本来はJpgのExifタグのデファクトスタンダードをもっと調査する必要あり
        #--------
        # 先頭8バイトが文字コードを示す
        prefix_ASCII = b"\x41\x53\x43\x49\x49\x00\x00\x00" #ASCII:英語圏ならあるのかな？
        prefix_JIS = b"\x4A\x49\x53\x00\x00\x00\x00\x00" #JIS:流石に古すぎ
        prefix_uni = b"\x55\x4E\x49\x43\x4F\x44\x45\x00" #Unicode:続くBOMで判定？めんどい
        prefix_undef = b"\x00\x00\x00\x00\x00\x00\x00\x00" #Undefined:未定義でutf-8、BOMなしが楽かも
        # BOM
        bom_utf8 = b"\xEF\xBB\xBF"
        bom_utf16be = b"\xFE\xFF" #bigエンディアン
        bom_utf16le = b"\xFF\xFE" #littleエンディアン
        #exif_dict["Exif"][piexif.ExifIFD.UserComment] = prefix_undef + metadata.encode("utf-8")
        #exif_dict["Exif"][piexif.ExifIFD.UserComment] = prefix_undef + bom_utf8 + metadata.encode("utf-8")
        #exif_dict["Exif"][piexif.ExifIFD.UserComment] = prefix_uni + metadata.encode("utf-8")
        #exif_dict["Exif"][piexif.ExifIFD.UserComment] = prefix_uni + bom_utf8 + metadata.encode("utf-8")
        #ASCIIとJIS、utf16は試してないが上記の4通りを試したところ、
        # IrfanViewだと「prefix_undefでBOMなし/あり」しかうまく表示出来なかった。一番シンプルなprefix_undefのみでの実装とする
        #exif_dict["Exif"][piexif.ExifIFD.UserComment] = prefix_undef + metadata.encode("utf-8")
        #と思ったが、ForgeのPNG Infoで読み込むと先頭8byteを無視してくれないので8byte分文字化けする
        #IrfanViewなど外部のツールでExif情報を読むと先頭8byteが捨てられる事になるが、SD1111やForgeで読み込める方を優先し、prefixすらなしにする
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = metadata.encode("utf-8")

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, output_file)

    except Exception as e:
        print(f"Error adding EXIF UserComment: {e}")

def convert_to_jpg(png_file, output_dir, quality, keeptimestamp):
    """Converts a PNG file to a JPEG file and embeds metadata."""
    try:
        metadata = extract_png_metadata(png_file)
        with Image.open(png_file) as img:
            rgb_img = img.convert("RGB")
            output_file = os.path.join(output_dir, os.path.splitext(os.path.basename(png_file))[0] + ".jpg")

            # Save the image as JPEG
            rgb_img.save(output_file, "JPEG", quality=quality)

            if metadata:
                # Add metadata to Exif UserComment
                add_exif_user_comment(output_file, metadata)

            if keeptimestamp:
                # Match the timestamp of the output file to the input file
                shutil.copystat(png_file, output_file)

    except Exception as e:
        print(f"Error converting {png_file}: {e}")

def process_files(input_path, output_dir, quality, max_workers, keeptimestamp):
    """Processes files or directories and converts PNG to JPEG."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    png_files = []

    if os.path.isfile(input_path):
        png_files = [input_path] if input_path.lower().endswith(".png") else []
    elif os.path.isdir(input_path):
        for root, _, files in os.walk(input_path):
            png_files.extend([os.path.join(root, f) for f in files if f.lower().endswith(".png")])

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(convert_to_jpg, png_file, output_dir, quality, keeptimestamp) for png_file in png_files]
        for future in futures:
            future.result()

def main():
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(description="Convert PNG to JPG with metadata.")
    parser.add_argument("input", type=str, help="Input file or directory containing PNG files.")
    parser.add_argument("output", type=str, help="Output directory for JPEG files.")
    parser.add_argument("--quality", type=int, default=85, help="JPEG quality (1-100). Default is 85.")
    parser.add_argument("--threads", type=int, default=os.cpu_count() - 1, help="Number of threads for parallel processing. Default is CPU Max Thread - 1.")
    parser.add_argument("--keeptimestamp", action="store_true", help="keep the original timestamp of PNG files.")

    args = parser.parse_args()
    quality = args.quality
    threads = args.threads
    if quality < 1 or quality > 100:
        quality = 85
        print(f"JPEG quality (1-100). Runs at the default value of 85.")
    if threads > os.cpu_count():
        threads = os.cpu_count() - 1
        print(f"The maximum number of threads on the CPU has been exceeded.")
    if threads < 1:
        threads = 1
        print(f"Runs with a minimum of 1 thread.")
    process_files(args.input, args.output, quality, threads, args.keeptimestamp)

if __name__ == "__main__":
    main()
