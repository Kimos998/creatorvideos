from flask import Flask, render_template, request, jsonify, send_file, Response
import google.generativeai as genai
import os
from googletrans import Translator
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageFilter
import io
import time
import random
import re
import json
import subprocess
from urllib.parse import quote
from io import BytesIO
import glob
import logging
from pathlib import Path

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# قراءة مفاتيح API من الملف
with open('api_keys.txt', 'r') as file:
    for line in file:
        if line.startswith('GEMINI_API_KEY'):
            gemini_api_key = line.split('=')[1].strip()
        elif line.startswith('ELEVEN_LABS_API_KEY'):
            eleven_labs_api_key = line.split('=')[1].strip()

# تهيئة Gemini
genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel('gemini-pro')
translator = Translator()

# Functions
def get_language_prompt(language):
    prompts = {
        'ar': """اكتب نصاً سلساً وطبيعياً لفيديو مدته ستين ثانية. اكتب النص باللغة العربية الفصحى.
        
        متطلبات مهمة:
        - اكتب النص مع التشكيل الكامل (الفتحة والضمة والكسرة والسكون والشدة)
        - استخدم علامات الترقيم بشكل صحيح
        - اكتب الأرقام بالحروف العربية (مثل: خَمْسَةٌ وَعِشْرُونَ)
        - تأكد من تشكيل الأسماء والأفعال والحروف
        - اجعل النص سهل القراءة والنطق
        - تجنب الكلمات الصعبة أو المعقدة
        - استخدم جملاً قصيرة وواضحة""",
        
        'en': "Write a flowing, natural 60-second video script in English.",
        'fr': "Écrivez un script vidéo naturel et fluide de 60 secondes en français."
    }
    return prompts.get(language, prompts['en'])

def download_images(description_list):
    print("Starting image downloads...")
    os.makedirs("images", exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    for index, description in enumerate(description_list[:15], 1):
        print(f"Searching for images for: {description}")
        # تعديل معايير البحث للحصول على صور فوتوغرافية نقية
        search_filters = [
            "filterui:photo-photo",     # صور فوتوغرافية فقط
            "filterui:imagesize-large",  # صور كبيرة فقط
            "-filterui:face-face",       # تجنب التركيز على الوجوه
            "-filterui:graphics-graphics", # تجنب الرسومات
            "-filterui:illustration-illustration" # تجنب الرسوم التوضيحية
        ]
        
        # إضافة كلمات للبحث تساعد في الحصول على صور نقية
        enhanced_query = f"{quote(description)} photography -text -logo -watermark -template -poster -chart -infographic"
        search_url = f"https://www.bing.com/images/search?q={enhanced_query}&qft={'+'.join(search_filters)}&FORM=IRFLTR"
        
        try:
            response = requests.get(search_url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # البحث عن الصور عالية الجودة
            image_elements = soup.find_all('a', class_='iusc')
            if not image_elements:
                continue
                
            for img_element in image_elements:
                try:
                    img_data = json.loads(img_element.get('m', '{}'))
                    image_url = img_data.get('murl', '')
                    
                    if not image_url or not image_url.startswith('http'):
                        continue
                        
                    img_response = requests.get(image_url, headers=headers, timeout=10)
                    if 'image' not in img_response.headers.get('content-type', '').lower():
                        continue
                        
                    # معالجة الصورة
                    img = Image.open(BytesIO(img_response.content))
                    
                    # التحقق من نسبة العرض إلى الارتفاع للتأكد من أنها صورة طبيعية
                    aspect_ratio = img.width / img.height
                    if not (0.5 <= aspect_ratio <= 2.0):  # تجنب الصور الطويلة جداً أو العريضة جداً
                        continue
                    
                    # تحويل إلى RGB إذا لزم الأمر
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                    
                    # تغيير الحجم مع الحفاظ على النسبة
                    target_width = 1920
                    target_height = 1080
                    ratio = min(target_width/img.width, target_height/img.height)
                    new_size = (int(img.width * ratio), int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                    
                    # حفظ الصورة بجودة عالية
                    output_path = f"images/image_{index}.jpg"
                    img.save(output_path, 'JPEG', quality=95, optimize=True)
                    print(f"Successfully downloaded image {index}/15")
                    
                    # إضافة تأخير لتجنب الحظر
                    time.sleep(1)
                    break
                    
                except Exception as e:
                    print(f"Error processing image: {str(e)}")
                    continue
                    
        except Exception as e:
            print(f"Error during image search: {str(e)}")
            continue
            
    print("Image download process completed")
    return True

def generate_video_script(topic, language):
    base_prompt = get_language_prompt(language)
    prompt = f"""{base_prompt}
    Topic: {topic}
    
    Requirements:
    - Write a continuous, natural narrative
    - No headings, sections, or formatting
    - Content should take exactly 60 seconds to narrate
    - Keep the flow smooth and professional
    - Write ONLY in {language} language regardless of the input language
    - Make it engaging and suitable for video content
    - Write all numbers in words
    
    Additional Arabic requirements:
    - Add full diacritical marks (تشكيل) to ALL Arabic text
    - Use correct punctuation marks
    - Write numbers in Arabic words with diacritics
    - Make sure to add diacritics to nouns, verbs, and particles
    - Keep the text easy to read and pronounce
    - Avoid complex or difficult words
    - Use short and clear sentences"""
    
    response = model.generate_content(prompt)
    return response.text

def generate_descriptions(keyword):
    try:
        # قراءة نص السكربت
        with open('video_script.txt', 'r', encoding='utf-8') as file:
            script = file.read()
        
        # ترجمة الكلمة المفتاحية إلى الإنجليزية
        english_keyword = translate_to_english(keyword)
        
        # تقسيم النص إلى 15 جزء وإنشاء ملخص لكل جزء
        prompt = f"""Here's a video script. Split it into 15 equal segments and create a unique 2-3 word description for each segment that includes the word '{english_keyword}'. 
        Each description should capture the main idea of its segment.
        
        Rules:
        1. Each description MUST include '{english_keyword}'
        2. Make each description UNIQUE - no repetition
        3. Keep descriptions natural and clear
        4. Return ONLY the 15 descriptions, one per line
        5. NO numbers, bullets, or special characters
        6. NO punctuation marks
        
        Script:
        {script}"""
        
        response = model.generate_content(prompt)
        descriptions = [line.strip() for line in response.text.splitlines() if line.strip()]
        
        # تأكد من أن لدينا 15 وصفاً فريداً
        unique_descriptions = []
        seen = set()
        
        for desc in descriptions:
            desc = desc.strip().strip('-').strip('•').strip('*').strip()
            if desc and desc not in seen:
                seen.add(desc)
                unique_descriptions.append(desc)
        
        # إذا لم نحصل على 15 وصفاً فريداً، نطلب المزيد
        while len(unique_descriptions) < 15:
            additional_prompt = f"""Generate {15 - len(unique_descriptions)} more unique descriptions including the word '{english_keyword}'.
            Current descriptions:
            {chr(10).join(unique_descriptions)}
            
            Rules:
            1. Each description MUST include '{english_keyword}'
            2. Make each description UNIQUE - different from the ones above
            3. Keep descriptions natural and clear
            4. NO numbers, bullets, or special characters
            5. NO punctuation marks"""
            
            additional_response = model.generate_content(additional_prompt)
            additional_descriptions = [line.strip() for line in additional_response.text.splitlines() if line.strip()]
            
            for desc in additional_descriptions:
                desc = desc.strip().strip('-').strip('•').strip('*').strip()
                if desc and desc not in seen:
                    seen.add(desc)
                    unique_descriptions.append(desc)
                if len(unique_descriptions) >= 15:
                    break
        
        # نأخذ أول 15 وصفاً فقط
        return '\n'.join(unique_descriptions[:15])
        
    except Exception as e:
        app.logger.error(f"Error generating descriptions: {str(e)}")
        return ""

def translate_to_english(text):
    try:
        result = translator.translate(text, dest='en')
        return result.text
    except:
        return text

def text_to_speech(text, language):
    url = "https://api.elevenlabs.io/v1/text-to-speech/nPczCjzI2devNBz1zQrb"
    
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": eleven_labs_api_key
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.71,
            "similarity_boost": 0.5,
            "style": 0,
            "use_speaker_boost": True
        }
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            with open('voice.mp3', 'wb') as f:
                f.write(response.content)
            return True
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error generating audio: {str(e)}")
        return False

def get_audio_duration(audio_file):
    """Get the duration of the audio file using ffprobe."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        audio_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data['format']['duration'])

def center_crop_image(image_path, target_width, target_height):
    """Place the image in the center with a blurred version of itself as background."""
    with Image.open(image_path) as img:
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Create blurred background from the same image
        # First, resize the image to be larger than target to avoid black edges
        bg_scale = 1.5
        bg_width = int(target_width * bg_scale)
        bg_height = int(target_height * bg_scale)
        
        # Create background by resizing and blurring the original image
        background = img.copy()
        background = background.resize((bg_width, bg_height), Image.Resampling.LANCZOS)
        
        # Apply gaussian blur effect
        for _ in range(3):  # Apply blur multiple times for stronger effect
            background = background.filter(ImageFilter.GaussianBlur(radius=10))
            
        # Crop the background to target size from center
        left = (bg_width - target_width) // 2
        top = (bg_height - target_height) // 2
        background = background.crop((left, top, left + target_width, top + target_height))
            
        # Calculate dimensions to maintain aspect ratio for main image
        width, height = img.size
        img_aspect = width / height
        target_aspect = target_width / target_height
        
        if img_aspect > target_aspect:
            # Image is wider - scale by width
            new_width = target_width
            new_height = int(target_width / img_aspect)
        else:
            # Image is taller - scale by height
            new_height = target_height
            new_width = int(target_height * img_aspect)
            
        # Resize main image while maintaining aspect ratio
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Calculate position to paste the main image
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        
        # Paste the main image onto the blurred background
        background.paste(img, (paste_x, paste_y))
        
        # Save processed image
        output_path = f"{os.path.splitext(image_path)[0]}_processed.jpg"
        background.save(output_path, 'JPEG', quality=95)
        return output_path

def create_video_with_transitions():
    # Video settings
    target_width = 1920
    target_height = 1080
    fps = 30
    transition_duration = 1  # seconds for crossfade
    
    # Get audio duration
    audio_file = "voice.mp3"
    total_duration = get_audio_duration(audio_file)
    
    # Get all images with proper sorting
    image_patterns = ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']
    image_files = []
    for pattern in image_patterns:
        image_files.extend(glob.glob(os.path.join('images', pattern)))
    image_files = sorted(image_files, key=lambda x: os.path.basename(x))
    
    num_images = len(image_files)
    print(f"Found {num_images} images: {[os.path.basename(f) for f in image_files]}")
    
    if num_images == 0:
        print("No images found!")
        return
        
    # Calculate timing
    image_duration = (total_duration - (transition_duration * (num_images - 1))) / num_images
    print(f"Each image will be shown for {image_duration:.2f} seconds")
    
    # Process images
    processed_images = []
    for img_path in image_files:
        processed_path = center_crop_image(img_path, target_width, target_height)
        processed_images.append(processed_path)
    
    # Prepare ffmpeg command
    base_cmd = ['ffmpeg', '-y']
    
    # Add input files
    for img in processed_images:
        base_cmd.extend(['-loop', '1', '-t', str(total_duration), '-i', img])
    
    # Add audio input
    base_cmd.extend(['-i', audio_file])
    
    # Create complex filter for transitions
    filter_complex = []
    
    # Setup input streams
    for i in range(num_images):
        filter_complex.append(f'[{i}:v]setpts=PTS-STARTPTS,format=yuva420p[v{i}];')
    
    # Create overlays
    if num_images > 1:
        # First overlay
        filter_complex.append(f'[v0][v1]xfade=transition=fade:duration={transition_duration}:offset={image_duration}[xf1];')
        
        # Middle overlays
        for i in range(2, num_images):
            offset = image_duration * i + transition_duration * (i - 1)
            filter_complex.append(f'[xf{i-1}][v{i}]xfade=transition=fade:duration={transition_duration}:offset={offset}[xf{i}];')
    
    # Build final command
    filter_str = ''.join(filter_complex)
    if num_images > 1:
        filter_str = filter_str[:-1]  # Remove last semicolon
    else:
        filter_str = filter_str + '[v0]format=yuv420p[vout]'
    
    base_cmd.extend([
        '-filter_complex', filter_str,
        '-map', f'[xf{num_images-1}]' if num_images > 1 else '[vout]',
        '-map', f'{num_images}:a',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-pix_fmt', 'yuv420p',
        '-shortest',
        'video.mp4'
    ])
    
    # Execute command
    try:
        print("Running ffmpeg command...")
        subprocess.run(base_cmd, check=True)
        print("Video created successfully!")
        
        # Clean up processed images
        for img in processed_images:
            os.remove(img)
            
    except subprocess.CalledProcessError as e:
        print(f"Error creating video: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    try:
        # التحقق من وجود مفاتيح API
        if not gemini_api_key or not eleven_labs_api_key:
            return jsonify({
                'success': False,
                'error': 'مفاتيح API غير متوفرة'
            }), 500

        # الحصول على البيانات من النموذج
        topic = request.form.get('topic', '')
        keyword = request.form.get('keyword', '')
        language = request.form.get('language', 'en')
        
        if not topic or not keyword:
            return jsonify({
                'success': False,
                'error': 'الرجاء إدخال الموضوع والكلمة المفتاحية'
            }), 400

        def generate_stream():
            try:
                # توليد سكريبت الفيديو
                yield "data: Starting script generation...\n\n"
                video_script = generate_video_script(topic, language)
                if not video_script:
                    yield "data: Error: Failed to generate script\n\n"
                    return
                
                # حفظ النص في ملف
                with open('video_script.txt', 'w', encoding='utf-8') as f:
                    f.write(video_script)
                yield "data: Script generated successfully\n\n"
                
                # توليد الأوصاف باستخدام الكلمة المفتاحية
                yield "data: Generating image descriptions...\n\n"
                descriptions = generate_descriptions(keyword)
                if not descriptions:
                    yield "data: Error: Failed to generate descriptions\n\n"
                    return
                
                # حفظ الأوصاف في ملف
                with open('descriptions.txt', 'w', encoding='utf-8') as f:
                    f.write(descriptions)
                
                # تحميل الصور
                description_list = descriptions.split('\n')
                if len(description_list) > 15:
                    description_list = description_list[:15]
                
                yield "data: Starting image downloads...\n\n"
                images_downloaded = download_images(description_list)
                
                if not images_downloaded:
                    yield "data: Warning: Some images failed to download\n\n"
                else:
                    yield "data: Image download process completed\n\n"
                
                # تحويل النص إلى صوت
                yield "data: Starting voice generation...\n\n"
                audio_success = text_to_speech(video_script, language)
                
                if audio_success:
                    yield "data: Voice generation completed\n\n"
                    messages = {
                        'ar': 'تم إنشاء النص والصور والصوت بنجاح! يمكنك الآن إنشاء الفيديو.',
                        'en': 'Script, images, and audio generated successfully! You can now create the video.',
                        'fr': 'Script, images et audio générés avec succès! Vous pouvez maintenant créer la vidéo.'
                    }
                    yield f"data: {json.dumps({'success': True, 'message': messages.get(language, messages['en'])})}\n\n"
                else:
                    yield "data: Error: Failed to generate audio\n\n"
                    
            except Exception as e:
                app.logger.error(f'Error in generate_stream: {str(e)}')
                yield f"data: Error: {str(e)}\n\n"

        return Response(generate_stream(), mimetype='text/event-stream')
            
    except Exception as e:
        app.logger.error(f'Error in generate: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/create_video', methods=['POST'])
def create_video():
    try:
        create_video_with_transitions()
        messages = {
            'ar': 'تم إنشاء الفيديو بنجاح!',
            'en': 'Video created successfully!',
            'fr': 'Vidéo créée avec succès!'
        }
        return jsonify({
            'success': True,
            'message': messages.get(request.args.get('language', 'en'), messages['en']),
            'video_url': '/video'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/video')
def video():
    if os.path.exists('video.mp4'):
        return send_file('video.mp4', mimetype='video/mp4')
    else:
        return jsonify({
            'success': False,
            'error': 'Video file not found'
        }), 404

if __name__ == '__main__':
    app.run(debug=True)
