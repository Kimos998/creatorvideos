from flask import Flask, render_template, request, jsonify, send_from_directory
import edge_tts
import asyncio
import openai
import os

app = Flask(__name__)

# Set up Google Gemini API with the given key
GEMINI_API_KEY = "AIzaSyAqcEMlllTBC6PISYrHNKx1mPSAPKVte9w"
openai.api_key = GEMINI_API_KEY

# Function to generate text using Gemini API
async def generate_text_from_topic(topic):
    prompt = f"Generate a detailed script about {topic}."
    response = openai.Completion.create(
        engine="text-davinci-003",  # Use the appropriate engine
        prompt=prompt,
        max_tokens=150,  # Adjust token count as necessary
        temperature=0.7
    )
    return response.choices[0].text.strip()

# Function to convert text to speech using edge_tts
async def text_to_speech(text, output_path):
    if not text.strip():
        return None, "Please enter the text to convert into voice."
    
    voice_short_name = "en-US-AriaNeural"  # Select a default voice
    rate_str = "+0%"  # Adjust rate as needed
    pitch_str = "+0Hz"  # Adjust pitch as needed
    
    communicate = edge_tts.Communicate(text, voice_short_name, rate=rate_str, pitch=pitch_str)
    
    # Save to the specified output path
    await communicate.save(output_path)
    return output_path, None

# Flask route to handle topic submission
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
async def generate():
    data = request.get_json()
    topic = data.get("topic")

    if not topic:
        return jsonify({"warning": "Topic cannot be empty."})

    try:
        # Generate text based on the topic using Gemini API
        generated_text = await generate_text_from_topic(topic)
        
        # Save the generated text to a file
        with open("script.txt", "w") as file:
            file.write(generated_text)

        # Convert the generated text to speech
        audio_path = "static/voice.mp3"
        _, warning = await text_to_speech(generated_text, audio_path)

        if warning:
            return jsonify({"warning": warning})

        return jsonify({"audio_url": f"/{audio_path}"})
    except Exception as e:
        return jsonify({"warning": f"An error occurred: {str(e)}"})

# Route to serve the generated audio file
@app.route("/static/<filename>")
def serve_file(filename):
    return send_from_directory("static", filename)

if __name__ == "__main__":
    # Ensure 'static' folder exists for serving the audio file
    if not os.path.exists("static"):
        os.makedirs("static")
    
    app.run(debug=True)
