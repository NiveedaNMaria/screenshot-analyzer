from flask import Flask, jsonify
from PIL import ImageGrab, Image, ImageEnhance, ImageFilter  # Python Imaging Library to capture screenshots
import os  # interact with the operating system
import time  # get the current time
import json
from apscheduler.schedulers.background import BackgroundScheduler  # scheduling tasks to run at regular intervals
import easyocr  # Optical Character Recognition library for extracting text from images
from transformers import pipeline  # Hugging Face pipeline for summarization
import re
import datetime
from textblob import TextBlob
import warnings

warnings.simplefilter(action='ignore', category=FutureWarning)

app = Flask(__name__)

# Directory to store screenshots
SCREENSHOT_DIR = "screenshots"
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

# Initialize the EasyOCR reader to recognize English text
reader = easyocr.Reader(['en'])  # Can add more languages as needed, e.g., ['en', 'fr']

# Initialize the Hugging Face summarizer
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# Function to take a screenshot
def take_screenshot():
    timestamp = int(time.time())
    screenshot_path = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
    
    # Take a screenshot
    screenshot = ImageGrab.grab()
    screenshot.save(screenshot_path)
    
    print(f"Screenshot saved at {screenshot_path}")
    return screenshot_path

def preprocess_image(image_path):
    # Open image using PIL
    image = Image.open(image_path)

    # Convert image to grayscale
    image = image.convert('L')
    
    # Enhance the contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2)  # Increase contrast

    # Apply sharpening filter
    image = image.filter(ImageFilter.SHARPEN)
    
    # Save preprocessed image
    preprocessed_path = image_path.replace('.png', '_preprocessed.png')
    image.save(preprocessed_path)
    
    return preprocessed_path

def analyze_screenshot(screenshot_path):
    # Preprocess the image
    preprocessed_path = preprocess_image(screenshot_path)
    
    # Run OCR on the preprocessed image
    result = reader.readtext(preprocessed_path)
    analysis_report = {
        "analysis": {
            "text": ' '.join([text[1] for text in result]),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        }
    }
    
    # Remove the preprocessed image
    if os.path.exists(preprocessed_path):
        os.remove(preprocessed_path)
    
    return analysis_report


def preprocess_text(text):
    # Remove URLs and query parameters
    text = re.sub(r'https?://\S+|www\.\S+', '', text)  # Remove URLs
    text = re.sub(r'\?.*$', '', text)  # Remove query parameters
    
    # Remove special characters and extra spaces
    text = re.sub(r'[^\w\s]', '', text)  # Remove special characters
    text = re.sub(r'\s+', ' ', text).strip()  # Replace multiple spaces with a single space
    
    return text

def get_username():
    try:
        # Fetch the username
        username = os.getlogin()
    except OSError:
        # Fallback if os.getlogin() fails
        username = os.environ.get('USER') or os.environ.get('USERNAME') or 'User'
    return username

def frame_sentence(text):
    # Correct grammar and rephrase the text
    blob = TextBlob(text)
    corrected_text = blob.correct()
    return str(corrected_text)

def generate_readable_report(reports):
    formatted_entries = []
    username = get_username()  # Get the username

    for report in reports:
        text = report["analysis"]["text"]
        timestamp = report["analysis"]["timestamp"]
        time_difference = report.get("total_time", "N/A")

        # Preprocess the text to remove unnecessary content
        cleaned_text = preprocess_text(text)

        # Generate a detailed summary
        summary_response = summarizer(cleaned_text, max_length=150, min_length=50, do_sample=False)
        
        if summary_response:
            summarized_text = summary_response[0]['summary_text']
            # Frame the sentence
            framed_text = frame_sentence(summarized_text)
        else:
            framed_text = "Summary could not be generated."

        # Reframe the sentence for readability
        formatted_entry = (f"On {timestamp},\n {username} was reviewing information related to: {framed_text}.\n"
                           f"Total time since the first report: {time_difference}.")
        
        formatted_entries.append(formatted_entry)
    
    # Join all entries with new lines
    readable_report = "\n".join(formatted_entries)

    # Save the readable report to a text file
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    summary_file = os.path.join(SCREENSHOT_DIR, f"readable_report_{today_date}.txt")
    
    with open(summary_file, "w") as f:
        f.write(readable_report)

    print(f"Readable report saved at {summary_file}")

# Function to process a screenshot and generate a report
def process_screenshot():
    screenshot_path = take_screenshot()
    report = analyze_screenshot(screenshot_path)

    # Get the current date and format it
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Path for the combined JSON report
    report_file = os.path.join(SCREENSHOT_DIR, f"combined_report_{current_date}.json")
    
    # Read existing data
    if os.path.exists(report_file):
        with open(report_file, "r") as f:
            existing_reports = json.load(f)
    else:
        existing_reports = []

    # Append new report
    existing_reports.append(report)
    
    # Calculate time difference between first and most recent report
    if len(existing_reports) > 1:
        first_report_time = datetime.datetime.strptime(existing_reports[0]["analysis"]["timestamp"], "%Y-%m-%d %H:%M:%S")
        latest_report_time = datetime.datetime.strptime(report["analysis"]["timestamp"], "%Y-%m-%d %H:%M:%S")
        time_difference = latest_report_time - first_report_time
        time_difference_str = str(time_difference)
        
        # Add time difference to the most recent report
        existing_reports[-1]["total_time"] = time_difference_str

    # Save the updated reports
    with open(report_file, "w") as f:
        json.dump(existing_reports, f, indent=4)

    print(f"Analysis report saved at {report_file}")

    # Generate the readable report
    generate_readable_report(existing_reports)

    os.remove(screenshot_path)

    return report

# Schedule screenshot-taking every 4 minutes
scheduler = BackgroundScheduler()
scheduler.add_job(process_screenshot, 'interval', minutes=4, max_instances=1)
scheduler.start()

# Flask route to get the latest report
@app.route('/report', methods=['GET'])
def get_latest_report():
    report_file = os.path.join(SCREENSHOT_DIR, "combined_report.json")
    if not os.path.exists(report_file):
        return jsonify({"error": "No reports available"}), 404
    
    with open(report_file, "r") as f:
        report_data = json.load(f)
    
    return jsonify(report_data)

# Start the Flask server
if __name__ == '__main__':
    app.run(debug=False)