import asyncio
import argparse
import os
import sys
from pathlib import Path
from scraper import MedofastScraper

def get_default_download_dir():
    # Common path for Android internal storage in Termux
    sdcard = Path("/sdcard/Download/medofast_robot")
    if os.access("/sdcard", os.W_OK):
        return sdcard
    return Path("./downloads")

async def main():
    parser = argparse.ArgumentParser(description="Medofast Scraper for Termux")
    parser.add_argument("--url", required=True, help="Start URL of the question bank")
    parser.add_argument("--output", default="questions.json", help="Output JSON filename")
    parser.add_argument("--csv", default="questions.csv", help="Output CSV filename")
    parser.add_argument("--session", default="session.json", help="Path to save/load session")
    parser.add_argument("--images-dir", default=str(get_default_download_dir()), help="Directory to save images")
    parser.add_argument("--delay", type=float, default=2.0, help="Click delay in seconds")
    parser.add_argument("--headless", action="store_true", default=True, help="Run in headless mode (default: True)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run with browser visible")
    parser.add_argument("--skip-exp", action="store_true", help="Skip waiting for explanations")

    args = parser.parse_args()

    # Create output directory if it doesn't exist
    images_path = Path(args.images_dir)
    images_path.mkdir(parents=True, exist_ok=True)

    scraper = MedofastScraper(session_path=args.session)
    scraper.url = args.url
    scraper.output_path = args.output
    scraper.csv_output_path = args.csv
    scraper.click_delay = args.delay
    scraper.skip_explanation = args.skip_exp

    # Set directories to the user-specified download path
    scraper.set_dirs(args.images_dir)

    print("\n" + "="*40)
    print("🚀 Medofast Scraper - Termux Edition")
    print("="*40)
    print(f"🔗 URL: {args.url}")
    print(f"📁 Output: {args.output} & {args.csv}")
    print(f"🖼️ Images: {args.images_dir}")
    print(f"👤 Session: {args.session}")
    print(f"🕶️ Headless: {args.headless}")
    print("="*40 + "\n")

    try:
        await scraper.run(headless=args.headless)
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
