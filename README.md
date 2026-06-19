# Medofast Scraper Pro

A Python-based web scraper for Medofast with a user-friendly graphical interface.

## Features

- **English GUI**: Easy-to-use interface for managing scraping tasks.
- **Adjustable Delays**: Customizable sliders for click and load delays to handle AJAX and prevent rate-limiting.
- **Skip Explanations**: Option to skip detailed answer explanations for faster scraping.
- **Manual Login**: Safely handle authentication by logging in manually and then starting the scraper.
- **Real-time Logs**: Monitor progress and errors as they happen.
- **Persistent Settings**: Saves your configuration (URL, delays, output path) for future use.

## Installation

1. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```

## Usage

1. **Run the GUI**:
   ```bash
   python gui.py
   ```

2. **Configuration**:
   - Enter the **Start URL** of the question bank.
   - Adjust the **Delay Sliders** according to your internet speed and site behavior.
   - Choose whether to **Skip Explanatory Answers**.
   - Select an **Output Path** for the JSON results.

3. **Execution**:
   - Click **Start Scraper**. A browser window will open at the login page.
   - Perform the login manually in the browser.
   - Once logged in, click the **Confirm Login** button in the GUI to start scraping questions.
   - Use **Pause** or **Stop** at any time.

## Requirements

- Python 3.7+
- Playwright
- Tkinter (usually included with Python)
