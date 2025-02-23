import os
import re
import json
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from geopy.geocoders import Nominatim
from io import BytesIO
from datetime import datetime
import base64
from groq import Groq

# Initialize Flask app
app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/roadmap')
def roadmap():
    return render_template('roadmap.html')

@app.route('/milestones')
def milestones():
    return render_template('milestones.html')


# Cloudflare AI configuration (replace these placeholders with your actual details)
CLOUDFLARE_ACCOUNT_ID = '3132b6001d2da3390c463648de7e3b80'
CLOUDFLARE_API_TOKEN = 'JHJFOUxR0RyIyJ0KiZrPh4KAm47oMEBg0rr_AzkT'
# Endpoints for Chat and Whisper models (adjust endpoint paths if needed)

CLOUDFLARE_CHAT_MODEL_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/meta/llama-3-8b-instruct"

CLOUDFLARE_WHISPER_MODEL_URL = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/openai/whisper-large-v3-turbo"
GROQ_API_KEY =  "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"

client = Groq(api_key=GROQ_API_KEY)

# Constants
MODEL_NAME = "llama-3.3-70b-versatile"

HEADERS = {
    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
    "Content-Type": "application/json"
}

# Constants
MODEL_NAME = "llama-3.3-70b-versatile"
WHISPER_MODEL = "whisper-large-v3-turbo"  # For reference

def get_coordinates(location_name):
    """Get latitude and longitude for a given location name using Nominatim."""
    geolocator = Nominatim(user_agent="location_finder")
    location = geolocator.geocode(location_name)
    if location:
        return {"latitude": location.latitude, "longitude": location.longitude}
    return None

def extract_date_time_location(response_text):
    """Extract Date, Time, and Location from the response text using regex."""
    date_match = re.search(r"Date:\s*(.*)", response_text)
    time_match = re.search(r"Time:\s*(.*)", response_text)
    location_match = re.search(r"Location:\s*(.*)", response_text)
    return {
        "Date": date_match.group(1) if date_match else None,
        "Time": time_match.group(1) if time_match else None,
        "Location": location_match.group(1) if location_match else None
    }


def transcribe_audio_file(audio_data):
    """Transcribe audio file content using Cloudflare's Whisper model by sending a JSON payload with a base64-encoded audio."""
    encoded_audio = base64.b64encode(audio_data).decode('utf-8')
    payload = {
        "audio": encoded_audio,
    }
    try:
        response = requests.post(
            CLOUDFLARE_WHISPER_MODEL_URL,
            headers=HEADERS,  # Ensure headers include "Content-Type": "application/json"
            json=payload
        )
        response.raise_for_status()
        data = response.json()
        print(data)
        # Adjust the key names based on Cloudflare's API response structure.
        return data["result"]["text"]
    except Exception as e:
        return str(e)


def extract_info_from_sentence(sentence):
    """
    Extract date, time, and location from the sentence using Cloudflare's chat AI.
    """
    payload = {
        "messages": [
            {"role": "user", "content": f"{sentence}. Give me the date time [Proper readable format dd:mm:yy hh:mm], location only like Date: , Time: , Location: "}
        ],
        "temperature": 0.1,
        "max_tokens": 160,
        "top_p": 0.95
    }
    try:
        response = requests.post(CLOUDFLARE_CHAT_MODEL_URL, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        print(data)
        # Assuming the API returns a structure similar to:
        # { "result": { "choices": [ { "message": { "content": "Your response text" } } ] } }
        response_text = data["result"]['response']
        return extract_date_time_location(response_text)
    except Exception as e:
        return {"error": f"Failed to extract information: {str(e)}"}

@app.route('/extract_info_and_coordinates', methods=['POST'])
def extract_info_and_coordinates_route():
    """
    Extracts date, time, location from the sentence and returns coordinates for the location.
    """
    data = request.get_json()
    sentence = data.get('sentence')
    if not sentence:
        return jsonify({'error': 'Sentence is required'}), 400

    structured_data = extract_info_from_sentence(sentence)
    location_name = structured_data.get("Location")
    if location_name:
        coordinates = get_coordinates(location_name)
        structured_data["Coordinates"] = coordinates if coordinates else {"error": "Location not found"}
    else:
        structured_data["Coordinates"] = {"error": "No location found in sentence"}

    return jsonify(structured_data), 200

@app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    """
    Accepts an audio file and returns the transcription text.
    """
    if "audio" not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    audio_file = request.files["audio"]
    audio_data = audio_file.read()
    transcription_text = transcribe_audio_file(audio_data)
    return jsonify({"transcription": transcription_text})

@app.route('/subtask', methods=['POST'])
def subtask():
    """
    Returns a subtask based on the input task using Cloudflare's chat AI.
    """
    data = request.json
    task_input = data.get("task")
    if not task_input:
        return jsonify({"error": "Task is required"}), 400

    prompt = f"""Here are some examples of tasks and their subtasks:

Example 1:
Task: "I need to go to the gym in the evening."
Subtask: "Do you want to prepare your gym bag?"

Example 2:
Task: "I need to finish my homework."
Subtask: "Do you want to open your laptop?"

Example 3:
Task: "I need to go for a run in the morning"
Subtask: "Do you want to wear your running shoes?"

Example 4:
Task: "So you want to go somewhere"
Subtask: "Do you wanna go out?"

Example 5:
Task: "I need to go to Columbia University in the evening"
Subtask: "Do you wanna leave the house?"

Now, for this task: {task_input} Just state a subtask with no other words but like a polite question, do you want to ... ?"""

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 160,
        "top_p": 0.95
    }
    try:
        response = requests.post(CLOUDFLARE_CHAT_MODEL_URL, headers=HEADERS, json=payload)
        response.raise_for_status()
        data_resp = response.json()
        print(data_resp)
        subtask_text = data_resp["result"]["response"]
        return jsonify({"task": task_input, "subtask": subtask_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/algo', methods=['POST'])
def algo():
  #Case1
    data = request.get_json()
    cur_task_list = data.get('task_list')
# Get current date and time
    now = datetime.now()
    current_date = now.date()
    print("Current Date:", current_date)
    current_time = now.time()
    print("Current Time:", current_time)
    # Convert dictionary to string
    task_string = json.dumps(cur_task_list)
    completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                    "role": "user",
        "content": f"""I have a list of tasks that have the following format, <task_id> : "task".  Can you help me get <task id>: prority_number by chronologically sorting them. The criterion for sorting are-if the task implies today, then consider it to be done today atleast 15 mins before the time mentioned. The actual time now is {current_time} if the task has a date, the current date should be compared to. The actual date is {current_date} and then the task is prioritized in accordance with others.
        Generic tasks like "Go to the gym" or "cook food" should be today at approprite times taking into consideration the current time. 
        The task list is as follows
    The tasks are {task_string} 
    Just give a chronological sort and return in the form of <task_id>/<task_name>/<Priority>/<task time>/<endtime> separated by a slash dont return anything else The end time can be approximated by you. 
    prority 1 means it is the most important and now mean most priority, And please make sure the the task_ids are consistent with the input task_ids
        DONT MAKE MISTAKES IN PRIORITIZING TAsk WITH NOW!!!!
        """
                    }
                ],
                temperature=0.7,
                max_completion_tokens=10000
                ,
                top_p=0.95,
                stream=True,
                
            )
    priority = ""
    for chunk in completion:
        priority += chunk.choices[0].delta.content or ""
    print(priority)
    # Split into lines and process each line
    tasks = []
    for line in priority.split("\n"):
        task_id, task_name, priority_val, start_time, end_time = line.split("/")
        tasks.append({
            "task_id": task_id,
            "task_name": task_name,
            "priority": int(priority_val),
            "start_time": start_time,
            "end_time": end_time
        })
    return jsonify(tasks)

if __name__ == '__main__':
    # Run the Flask app on port 5001
    app.run(debug=True, port=5001)
