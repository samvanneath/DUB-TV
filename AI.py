import os
import sys
import math
import asyncio
import tempfile
import time
import threading
import requests
import subprocess
import urllib.parse
import re
import html
import shutil
from pathlib import Path
import winsound
import numpy as np
import hashlib

# ---------------------------------------------------------
# Configure FFmpeg & FFprobe Executables & PATH for Whisper/Pydub/Subprocess
# ---------------------------------------------------------
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception as e:
    print(f"[Warning] static_ffmpeg initialization: {e}")

import imageio_ffmpeg

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FFMPEG = os.path.join(APP_DIR, "ffmpeg.exe")
LOCAL_FFPROBE = os.path.join(APP_DIR, "ffprobe.exe")

try:
    img_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if img_ffmpeg and os.path.exists(img_ffmpeg):
        if not os.path.exists(LOCAL_FFMPEG):
            shutil.copyfile(img_ffmpeg, LOCAL_FFMPEG)
except Exception as e:
    print(f"[Warning] Failed to copy local ffmpeg: {e}")

if os.path.exists(LOCAL_FFMPEG):
    FFMPEG_EXE = LOCAL_FFMPEG
else:
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

ffmpeg_dir = os.path.dirname(FFMPEG_EXE)
os.environ["PATH"] = APP_DIR + os.path.pathsep + ffmpeg_dir + os.path.pathsep + os.environ.get("PATH", "")

import pydub
from pydub import AudioSegment
AudioSegment.converter = FFMPEG_EXE
AudioSegment.ffmpeg = FFMPEG_EXE
if os.path.exists(LOCAL_FFPROBE):
    AudioSegment.ffprobe = LOCAL_FFPROBE
elif shutil.which("ffprobe"):
    AudioSegment.ffprobe = shutil.which("ffprobe")

import whisper
import edge_tts
from deep_translator import MyMemoryTranslator, GoogleTranslator
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import cv2
from PIL import Image, ImageTk, ImageDraw, ImageFont
import ctypes
from ctypes import wintypes
from google import genai
from google.genai import types
from copyright_detector import CopyrightScannerDialog


# Ensure UTF-8 output on Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ---------------------------------------------------------
# Windows Short Path Helper (Supports Unicode/Khmer Paths in OpenCV)
# ---------------------------------------------------------
def get_short_path(path: str) -> str:
    if sys.platform == 'win32' and path and os.path.exists(path):
        try:
            _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
            _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
            _GetShortPathNameW.restype = wintypes.DWORD
            buf = ctypes.create_unicode_buffer(500)
            res = _GetShortPathNameW(path, buf, 500)
            if res > 0:
                return buf.value
        except Exception:
            pass
    return path

# ---------------------------------------------------------
# Khmer PIL Font Finder Helper
# ---------------------------------------------------------
def get_khmer_pil_font(size: int):
    candidates = [
        "C:/Windows/Fonts/Kantumruy.ttf",
        "C:/Windows/Fonts/Kantumruy Bold.ttf",
        "C:/Windows/Fonts/Kantumruy Light.ttf",
        "C:/Windows/Fonts/NotoSansKhmer-Bold.ttf",
        "C:/Windows/Fonts/NotoSansKhmer-Regular.ttf",
        "C:/Windows/Fonts/Khmer OS Battambang.ttf",
        "C:/Windows/Fonts/arial.ttf"
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass

    try:
        return ImageFont.load_default()
    except Exception:
        return None

# ---------------------------------------------------------
# Helper to Open Folder Safely
# ---------------------------------------------------------
def safe_open_folder(folder_path: str):
    try:
        norm_path = os.path.normpath(folder_path)
        if os.path.exists(norm_path):
            if sys.platform == 'win32':
                os.startfile(norm_path)
            elif sys.platform == 'darwin':
                subprocess.run(["open", norm_path], env=os.environ)
            else:
                subprocess.run(["xdg-open", norm_path], env=os.environ)
    except Exception as e:
        print(f"[Warning] Failed to open folder '{folder_path}': {e}")

# ---------------------------------------------------------
# Locate Video File in Windows Explorer (Highlighted)
# ---------------------------------------------------------
def safe_locate_file(file_path: str):
    try:
        if not file_path:
            return
        norm_path = os.path.normpath(file_path)
        if os.path.exists(norm_path):
            if sys.platform == 'win32':
                subprocess.run(f'explorer.exe /select,"{norm_path}"')
            elif sys.platform == 'darwin':
                subprocess.run(["open", "-R", norm_path], env=os.environ)
            else:
                safe_open_folder(os.path.dirname(norm_path))
        else:
            parent = os.path.dirname(norm_path)
            if os.path.exists(parent):
                safe_open_folder(parent)
    except Exception as e:
        print(f"[Warning] Failed to locate file '{file_path}': {e}")

# ---------------------------------------------------------
# Play Video File with Default Media Player
# ---------------------------------------------------------
def play_video_file(video_path: str):
    try:
        if not video_path:
            return
        norm_path = os.path.normpath(video_path)
        if os.path.exists(norm_path):
            if sys.platform == 'win32':
                os.startfile(norm_path)
            elif sys.platform == 'darwin':
                subprocess.run(["open", norm_path], env=os.environ)
            else:
                subprocess.run(["xdg-open", norm_path], env=os.environ)
        else:
            messagebox.showwarning("រកមិនឃើញ", f"រកមិនឃើញឯកសារវីដេអូ៖\n{video_path}")
    except Exception as e:
        print(f"[Warning] Failed to play video: {e}")

# ---------------------------------------------------------
# Get Video Metadata (Duration, Dimensions, File Size)
# ---------------------------------------------------------
def get_video_info(video_path: str) -> dict:
    info = {'duration': 0.0, 'width': 0, 'height': 0, 'size_mb': 0.0}
    try:
        if not os.path.exists(video_path):
            return info
        info['size_mb'] = round(os.path.getsize(video_path) / (1024 * 1024), 2)
        sp = get_short_path(video_path)
        cap = cv2.VideoCapture(sp)
        if cap.isOpened():
            info['width'] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            info['height'] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if fps > 0 and frames > 0:
                info['duration'] = round(frames / fps, 1)
            cap.release()
    except Exception as e:
        print(f"[Warning] get_video_info: {e}")
    return info

# ---------------------------------------------------------
# Extract Video Thumbnail Frame
# ---------------------------------------------------------
def extract_video_thumbnail(video_path: str, max_size=(110, 65)):
    try:
        temp_thumb = os.path.join(tempfile.gettempdir(), f"vthumb_{int(time.time()*1000)}.jpg")
        cmd = [
            FFMPEG_EXE, "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            "-vf", f"scale={max_size[0]}:{max_size[1]}:force_original_aspect_ratio=decrease",
            temp_thumb
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)
        if res.returncode == 0 and os.path.exists(temp_thumb):
            img = Image.open(temp_thumb)
            return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)

        sp = get_short_path(video_path)
        cap = cv2.VideoCapture(sp)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 1))
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
    except Exception as e:
        print(f"[Warning] extract_video_thumbnail: {e}")
    return None


# ---------------------------------------------------------
# Gemini AI Localization & Dubbing Translation Config
# ---------------------------------------------------------
GEMINI_KEY_FILE = os.path.join(APP_DIR, "gemini_key.txt")

def get_saved_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key and os.path.exists(GEMINI_KEY_FILE):
        try:
            with open(GEMINI_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
        except Exception:
            pass
    return key

def save_gemini_key(key: str):
    try:
        with open(GEMINI_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key.strip())
    except Exception as e:
        print(f"[Warning] Failed to save Gemini key: {e}")

SYSTEM_INSTRUCTION = """
You are a professional movie localization and dubbing script translator specializing in English to Khmer translation.

Translation Rules:
1. Tone & Flow: Translate naturally into spoken conversational Khmer (ភាសានិយាយ). Do NOT translate word-by-word literally.
2. Character Dynamics: Choose proper Khmer pronouns matching scene context (e.g., ឯង/យើង, ខ្ញុំ/លោក, បង/អូន).
3. Timing: Keep translations concise so the spoken voice matches original timestamps.
4. Output: Return ONLY the translated Khmer dialogue without notes or romanization.
"""

_GEMINI_CLIENTS = {}

def get_gemini_client(api_key: str):
    k = api_key.strip()
    if k not in _GEMINI_CLIENTS:
        _GEMINI_CLIENTS[k] = genai.Client(api_key=k)
    return _GEMINI_CLIENTS[k]

def translate_dialogue_gemini(text: str, api_key: str = "") -> str:
    """បញ្ជូនអត្ថបទដើមទៅ Gemini ហើយទទួលយកអត្ថបទបកប្រែជាភាសាខ្មែរ"""
    if not text or not text.strip():
        return ""
    
    key = api_key.strip() or get_saved_gemini_key()
    if not key:
        raise ValueError("Missing GEMINI_API_KEY")
        
    client = get_gemini_client(key)
    generation_config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.3,
    )
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=text.strip(),
        config=generation_config
    )
    res_text = response.text.strip() if response.text else ""
    return res_text

# ---------------------------------------------------------
# Khmer Mojibake Auto-Healer (Fixes áž... UTF-8 encoded as ANSI/CP1252)
# ---------------------------------------------------------
_BYTE_MAP = {}
for _b in range(256):
    _BYTE_MAP[chr(_b)] = _b
for _b in range(128, 256):
    try:
        _ch = bytes([_b]).decode('windows-1252')
        _BYTE_MAP[_ch] = _b
    except Exception:
        pass

def restore_mojibake(s: str) -> str:
    """Detects and automatically converts broken Khmer mojibake (e.g. áž...) into proper Unicode."""
    if not s or ('áž' not in s and '\xe1' not in s and 'á' not in s):
        return s
    res = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] in _BYTE_MAP and _BYTE_MAP[s[i]] >= 0xC0:
            chunk = []
            j = i
            while j < n and s[j] in _BYTE_MAP:
                chunk.append(_BYTE_MAP[s[j]])
                j += 1
            decoded = None
            for k in range(j, i, -1):
                try:
                    decoded = bytes(chunk[:k - i]).decode('utf-8')
                    res.append(decoded)
                    i = k
                    break
                except UnicodeDecodeError:
                    continue
            if decoded is not None:
                continue
        res.append(s[i])
        i += 1
    return ''.join(res)

def clean_translation_text(text: str, orig_input: str = "") -> str:
    """សម្អាតកូដភាសាដូចជា zh-CN, zh-TW, en, ja, ko ... និងកែកំហុសអក្សរ Mojibake (áž...)"""
    if not text:
        return ""
    cleaned = restore_mojibake(str(text).strip())
    
    # 1. Remove bracketed / parenthesized language tags e.g. [zh-CN], (zh-CN), {zh-CN}
    cleaned = re.sub(
        r'[\(\[\{]\s*(?:zh-CN|zh-TW|zh_CN|zh_TW|zh|en|ja|ko|th|vi|ru|fr|es|de|id|ms)\s*[\)\]\}]',
        '',
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    # 2. Remove language codes at the end of the text (e.g. '...zh-CN', '... zh-CN', '... - zh-CN')
    cleaned = re.sub(
        r'[\s\-_/\\\[\(\]]*(?:zh-CN|zh-TW|zh_CN|zh_TW|zh|en|ja|ko|th|vi|ru|fr|es|de|id|ms)[\s\]\)]*$',
        '',
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    return cleaned


# ---------------------------------------------------------
# Robust Multi-Engine Translation Function for Khmer (km)
# ---------------------------------------------------------
def translate_text(text: str, source_lang: str = "auto", target_lang: str = "km", api_key: str = "", use_gemini: bool = True) -> str:
    if not text or not text.strip():
        return ""

    raw_input = text.strip()

    # 1. Primary Engine: Gemini 2.5 Flash (Movie Localization & Dubbing)
    if use_gemini:
        try:
            key = api_key.strip() or get_saved_gemini_key()
            if key:
                gemini_res = translate_dialogue_gemini(raw_input, api_key=key)
                if gemini_res and gemini_res.strip():
                    return clean_translation_text(gemini_res.strip(), raw_input)
        except Exception as e:
            print(f"[Warning] Gemini 2.5 Flash translation: {e}. Falling back to standard engines...")

    # 2. Secondary Engine: Clients5 Google Translate API
    try:
        url = f"https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl={source_lang}&tl={target_lang}&q={urllib.parse.quote(raw_input)}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            res = r.json()
            if isinstance(res, list) and len(res) > 0:
                parts = []
                for item in res:
                    if isinstance(item, list) and len(item) > 0:
                        # item[0] is the translated string, item[1] is the source lang code (e.g. 'zh-CN')
                        parts.append(str(item[0]))
                    elif isinstance(item, str):
                        parts.append(item)
                        break
                trans = "".join(parts).strip()
                trans = clean_translation_text(trans, raw_input)
                if trans and trans.lower() != raw_input.lower():
                    return trans
    except Exception as e:
        print(f"[Warning] Clients5 Engine failed: {e}")

    # 3. Third Engine: MyMemory Direct API
    try:
        src = "en" if source_lang == "auto" else source_lang
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(raw_input)}&langpair={src}|{target_lang}"
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            res = r.json()
            trans = res.get('responseData', {}).get('translatedText', '')
            if trans and trans.strip() and trans.strip().lower() != raw_input.lower():
                return clean_translation_text(html.unescape(trans.strip()), raw_input)
    except Exception as e:
        print(f"[Warning] MyMemory Engine failed: {e}")

    # 4. Fourth Engine: Google Mobile Scraper
    try:
        url = f"https://translate.google.com/m?sl={source_lang}&tl={target_lang}&q={urllib.parse.quote(raw_input)}"
        headers = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X)'}
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            m = re.search(r'class="result-container">(.*?)</div>', r.text)
            if m:
                trans = html.unescape(m.group(1)).strip()
                trans = clean_translation_text(trans, raw_input)
                if trans and trans.lower() != raw_input.lower():
                    return trans
    except Exception as e:
        print(f"[Warning] Google Mobile Engine failed: {e}")

    # 5. Fallback Engine: Deep Translator
    try:
        trans = GoogleTranslator(source=source_lang, target=target_lang).translate(raw_input)
        if trans and trans.strip():
            return clean_translation_text(trans.strip(), raw_input)
    except Exception as e:
        print(f"[Warning] DeepTranslator fallback failed: {e}")

    return clean_translation_text(raw_input)

# ---------------------------------------------------------
# Precision Multi-Factor Voice Gender Classifier (Acoustic + Formant Analysis)
# ---------------------------------------------------------
def detect_voice_gender(audio_seg: AudioSegment, text_hint: str = "") -> str:
    """
    ប្រព័ន្ធវិភាគភេទសំឡេងកម្រិតខ្ពស់ (Precision Vocal Gender Classifier):
    1. Bandpass Filter (75Hz - 4000Hz) កម្ចាត់សំឡេងរំខាន Sub-bass/BGM/Air-con
    2. Voiced Pitch Harmonic Auto-Correlation & Parabolic Interpolation
    3. Vocal Tract Length (Formant Energy Ratio 1400-3600Hz vs 200-1250Hz)
    4. Spectral Centroid & Spectral Rolloff (85% energy slope)
    5. Torchaudio pitch tracking
    6. Multi-lingual Dialogue Clues (Khmer, English, Chinese pronouns & honorifics)
    ត្រឡប់: 'male' ឬ 'female'
    """
    try:
        # 1. Multi-lingual Contextual Semantic Dialogue Clues
        text_bias = 0.0 # -0.25 (Male bias) to +0.25 (Female bias)
        if text_hint:
            th = f" {text_hint.lower()} "
            female_cues = [
                " she ", " her ", " hers ", " mom ", " mother ", " mrs ", " miss ", " ms ", " lady ", " woman ", " women ",
                " girl ", " girls ", " sister ", " wife ", " queen ", " pregnant ", " aunt ", " grandma ", " daughter ", " mommy ", " mama ",
                " princess ", " actress ", " madam ", " female ",
                " នាង ", " ស្រី ", " ម៉ាក់ ", " ម្តាយ ", " ម្ដាយ ", " បងស្រី ", " ប្អូនស្រី ", " អ្នកស្រី ", " កញ្ញា ", " មីង ", " អ្នកមីង ",
                " យាយ ", " លោកយាយ ", " ប្រពន្ធ ", " ព្រះនាង ", " កូនស្រី ", " ចៅស្រី ",
                "她", "她的", "妈", "妈妈", "母亲", "姐", "姐姐", "妹", "妹妹", "女", "女人", "女士", "夫人", "小姐", "太太", "媳妇",
                "老婆", "姑娘", "少女", "闺女", "女儿", "娘", "大妈", "阿姨", "婆婆", "公主", "王妃", "皇后", "师姐", "师妹", "女侠",
                "เธอ", "แม่", "พี่สาว", "น้องสาว", "ผู้หญิง", "ลูกสาว", "คุณแม่", "คะ", "ค่ะ"
            ]
            male_cues = [
                " he ", " his ", " him ", " dad ", " father ", " mr ", " mister ", " sir ", " man ", " men ",
                " guy ", " guys ", " brother ", " husband ", " king ", " uncle ", " grandpa ", " boy ", " boys ", " son ", " daddy ", " papa ",
                " prince ", " actor ", " lord ", " male ",
                " គាត់ ", " ប្រុស ", " ប៉ា ", " ឪពុក ", " ឪ ", " បងប្រុស ", " ប្អូនប្រុស ", " លោក ", " លោកតា ", " ពូ ", " អ្នកពូ ",
                " តា ", " ប្តី ", " ស្វាមី ", " ព្រះអង្គ ", " ស្ដេច ", " កូនប្រុស ", " ចៅប្រុស ",
                "他", "他的", "爸", "爸爸", "父亲", "哥", "哥哥", "弟", "弟弟", "男", "男人", "男士", "先生", "老公", "丈夫",
                "兄弟", "少爷", "公子", "小伙", "男孩", "儿子", "爷爷", "大叔", "叔叔", "伯伯", "国王", "王子", "皇帝", "师兄", "师弟", "大侠",
                "เขา", "พ่อ", "พี่ชาย", "น้องชาย", "ผู้ชาย", "ลูกชาย", "คุณพ่อ", "ครับ"
            ]
            has_f = any(c in th for c in female_cues)
            has_m = any(c in th for c in male_cues)
            if has_f and not has_m:
                text_bias = 0.25
            elif has_m and not has_f:
                text_bias = -0.25

        if not audio_seg or len(audio_seg) < 180:
            return "female" if text_bias > 0.05 else "male"

        # Convert to mono 16kHz
        seg_16k = audio_seg.set_frame_rate(16000).set_channels(1)
        samples = np.array(seg_16k.get_array_of_samples(), dtype=np.float32)
        if len(samples) < 1600 or np.max(np.abs(samples)) < 25:
            return "female" if text_bias > 0.05 else "male"

        samples = samples / (np.max(np.abs(samples)) + 1e-6)
        sr = 16000

        # 2. Bandpass filter via FFT to isolate speech vocal band (75 Hz - 4000 Hz)
        fft_all = np.fft.rfft(samples)
        freqs_all = np.fft.rfftfreq(len(samples), 1.0 / sr)
        filter_mask = (freqs_all >= 75) & (freqs_all <= 4000)
        fft_filtered = fft_all * filter_mask
        clean_samples = np.fft.irfft(fft_filtered, n=len(samples))

        # Frame parameters (50ms window with 25ms step)
        frame_len = int(sr * 0.05) # 800 samples
        hop_len = int(sr * 0.025)  # 400 samples
        min_lag = int(sr / 360)    # ~44 (360 Hz)
        max_lag = int(sr / 75)     # ~213 (75 Hz)
        window = np.hanning(frame_len)

        voiced_f0 = []
        formant_ratios = []
        centroids = []
        spectral_rolloffs = []

        for i in range(0, len(clean_samples) - frame_len, hop_len):
            frame = clean_samples[i:i + frame_len]
            energy = np.mean(frame ** 2)
            if energy < 0.001:
                continue

            w_frame = frame * window
            corr = np.correlate(w_frame, w_frame, mode='full')
            corr = corr[len(corr)//2:]
            e0 = corr[0]
            if e0 <= 1e-6:
                continue

            search_corr = corr[min_lag:max_lag]
            peak_idx = np.argmax(search_corr)
            peak_lag = min_lag + peak_idx
            peak_val = search_corr[peak_idx]
            harm_ratio = peak_val / e0

            # Spectral Formant and Tract Analysis
            mag = np.abs(np.fft.rfft(w_frame))
            freqs = np.fft.rfftfreq(frame_len, 1.0 / sr)

            idx_low = (freqs >= 200) & (freqs < 1250)
            idx_high = (freqs >= 1400) & (freqs < 3600)
            e_low = np.sum(mag[idx_low]**2) + 1e-6
            e_high = np.sum(mag[idx_high]**2) + 1e-6
            formant_ratios.append(e_high / e_low)

            # Spectral Centroid
            sum_mag = np.sum(mag) + 1e-6
            centroids.append(np.sum(freqs * mag) / sum_mag)

            # Spectral Rolloff (85% energy point)
            cum_energy = np.cumsum(mag**2)
            rolloff_idx = np.searchsorted(cum_energy, 0.85 * cum_energy[-1])
            spectral_rolloffs.append(freqs[min(rolloff_idx, len(freqs)-1)])

            # Voiced Harmonic Pitch with Parabolic Interpolation
            if harm_ratio >= 0.30:
                f0 = sr / peak_lag
                if 0 < peak_idx < len(search_corr) - 1:
                    alpha = search_corr[peak_idx - 1]
                    beta = search_corr[peak_idx]
                    gamma = search_corr[peak_idx + 1]
                    denom = 2 * (alpha - 2 * beta + gamma)
                    if abs(denom) > 1e-6:
                        delta = (alpha - gamma) / denom
                        f0 = sr / (peak_lag + delta)
                if 75 <= f0 <= 360:
                    voiced_f0.append(f0)

        # Torchaudio auxiliary pitch confirmation
        torchaudio_f0 = None
        try:
            import torch
            import torchaudio.functional as F
            tensor_wave = torch.from_numpy(clean_samples).unsqueeze(0)
            tpitch = F.detect_pitch_frequency(tensor_wave, sample_rate=16000)
            valid_t = tpitch[(tpitch >= 75) & (tpitch <= 360)]
            if len(valid_t) >= 4:
                torchaudio_f0 = float(valid_t.median().item())
        except Exception:
            pass

        if not voiced_f0 and torchaudio_f0 is None and not formant_ratios:
            return "female" if text_bias > 0.05 else "male"

        if voiced_f0:
            med_f0 = float(np.median(voiced_f0))
            if torchaudio_f0 is not None:
                med_f0 = 0.65 * med_f0 + 0.35 * torchaudio_f0
        elif torchaudio_f0 is not None:
            med_f0 = torchaudio_f0
        else:
            med_f0 = 150.0

        med_formant = float(np.median(formant_ratios)) if formant_ratios else 0.25
        med_sc = float(np.median(centroids)) if centroids else 1500.0
        med_rolloff = float(np.median(spectral_rolloffs)) if spectral_rolloffs else 2200.0

        # Multi-factor Normalized Scoring:
        # 1. Pitch F0 Score (Male ~80-130Hz, Female ~165-260Hz)
        if med_f0 <= 130:
            p_score = 0.0
        elif med_f0 >= 165:
            p_score = 1.0
        else:
            p_score = (med_f0 - 130) / (165 - 130)

        # 2. Vocal Tract Length / Formant Ratio Score (Higher in females due to shorter tract)
        if med_formant <= 0.15:
            f_score = 0.0
        elif med_formant >= 0.35:
            f_score = 1.0
        else:
            f_score = (med_formant - 0.15) / (0.35 - 0.15)

        # 3. Spectral Centroid Score
        if med_sc <= 1250:
            sc_score = 0.0
        elif med_sc >= 1850:
            sc_score = 1.0
        else:
            sc_score = (med_sc - 1250) / (1850 - 1250)

        # 4. Spectral Rolloff Score (Aspiration & high harmonics)
        if med_rolloff <= 1800:
            ro_score = 0.0
        elif med_rolloff >= 2650:
            ro_score = 1.0
        else:
            ro_score = (med_rolloff - 1800) / (2650 - 1800)

        # Composite Weighted Score: Pitch (45%), Vocal Tract Formants (25%), Centroid (15%), Rolloff (15%)
        composite = (0.45 * p_score + 0.25 * f_score + 0.15 * sc_score + 0.15 * ro_score) + text_bias

        # Decisive Classification Rule:
        # If fundamental pitch is clearly in female territory (>=165 Hz) or composite >= 0.46
        if med_f0 >= 165 or composite >= 0.46:
            return "female"
        return "male"

    except Exception as e:
        print(f"[Warning] Gender detection error: {e}")

    return "male"

# ---------------------------------------------------------
# TTS Text Cleaner & Synthesis Helper
# ---------------------------------------------------------
def clean_tts_text(text: str) -> str:
    """Prepares text for Edge-TTS Khmer synthesis to ensure crystal clear pronunciation."""
    if not text:
        return ""
    t = str(text).strip()
    # 1. Clean bracketed / parenthesized language tags e.g. [zh-CN]
    t = clean_translation_text(t)
    # 2. Remove emojis and surrogate symbols that confuse neural TTS
    t = re.sub(r'[\U00010000-\U0010ffff]', '', t)
    # 3. Remove markdown / special symbols
    t = re.sub(r'[*_~`#|<>\[\]\(\)\{\}\\\/]', ' ', t)
    # 4. Normalize multiple punctuation or ellipses to a single Khmer khan '។'
    t = re.sub(r'\.{2,}', '។', t)
    t = re.sub(r'[-—_]{2,}', ' ', t)
    t = re.sub(r'["\'`“”‘’«»]', '', t)
    # 5. Clean whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t

async def generate_tts_async(text: str, voice: str, output_path: str, rate: str = "+0%", pitch: str = "+0Hz"):
    """Generate Edge-TTS audio with automatic retries, backoff, and timeouts."""
    cleaned = clean_tts_text(text)
    if not cleaned:
        cleaned = " "
    last_err = None
    backoffs = [0.4, 1.0, 2.0, 3.5]
    for attempt in range(len(backoffs)):
        try:
            communicate = edge_tts.Communicate(
                cleaned, voice, 
                rate=rate, pitch=pitch,
                connect_timeout=8,
                receive_timeout=30
            )
            await communicate.save(output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return
        except Exception as e:
            last_err = e
            wait_t = backoffs[attempt]
            print(f"[TTS Attempt {attempt+1}/{len(backoffs)}] Warning: {e}. Retrying in {wait_t}s...")
            await asyncio.sleep(wait_t)
    if last_err:
        raise last_err

def generate_tts(text: str, voice: str, output_path: str, rate: str = "+0%", pitch: str = "+0Hz"):
    asyncio.run(generate_tts_async(text, voice, output_path, rate=rate, pitch=pitch))

# ---------------------------------------------------------
# Audio Playback Helper (MCI + winsound Async)
# ---------------------------------------------------------
_GLOBAL_AUDIO_ALIAS = "app_audio_player"

def stop_audio_playback():
    try:
        winmm = ctypes.windll.winmm
        winmm.mciSendStringW(f'stop {_GLOBAL_AUDIO_ALIAS}', None, 0, 0)
        winmm.mciSendStringW(f'close {_GLOBAL_AUDIO_ALIAS}', None, 0, 0)
    except Exception:
        pass
    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass

def play_audio_file(audio_path: str):
    """Play any audio file (MP3/WAV) asynchronously and loudly on Windows without freezing GUI."""
    if not audio_path or not os.path.exists(audio_path):
        return

    def _play_worker():
        try:
            stop_audio_playback()

            # Load and boost/normalize audio for clear playback
            sound = AudioSegment.from_file(audio_path)
            if sound.dBFS > -90 and sound.dBFS < -14:
                gain = min(12.0, -12.0 - sound.dBFS)
                sound = sound.apply_gain(gain)
            sound = sound.set_frame_rate(44100).set_channels(2).set_sample_width(2)

            temp_wav = os.path.join(tempfile.gettempdir(), f"play_cache_{int(time.time()*1000)}.wav")
            sound.export(temp_wav, format="wav")

            short_p = get_short_path(temp_wav)
            winmm = ctypes.windll.winmm
            r1 = winmm.mciSendStringW(f'open "{short_p}" type waveaudio alias {_GLOBAL_AUDIO_ALIAS}', None, 0, 0)
            r2 = winmm.mciSendStringW(f'play {_GLOBAL_AUDIO_ALIAS}', None, 0, 0)
            if r1 != 0 or r2 != 0:
                winsound.PlaySound(temp_wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            print(f"[Audio Error] Play error: {e}")
            try:
                os.startfile(audio_path)
            except Exception:
                pass

    threading.Thread(target=_play_worker, daemon=True).start()

# ---------------------------------------------------------
# Professional Pitch-Preserving Audio Time-Stretching (FFmpeg atempo)
# ---------------------------------------------------------
def change_audio_speed_atempo(audio: AudioSegment, speed: float) -> AudioSegment:
    """
    High-quality pitch-preserving time stretching using FFmpeg's WSOLA 'atempo' filter.
    Preserves 100% of the original pitch, formants, and natural voice timbre.
    """
    if abs(speed - 1.0) < 0.03:
        return audio
        
    speed = max(0.5, min(2.0, speed))
    
    try:
        import io
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        input_bytes = wav_io.getvalue()
        
        cmd = [
            FFMPEG_EXE, "-y",
            "-f", "wav", "-i", "pipe:0",
            "-filter:a", f"atempo={speed:.3f}",
            "-f", "wav", "pipe:1"
        ]
        proc = subprocess.run(
            cmd,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=os.environ
        )
        if proc.returncode == 0 and proc.stdout and len(proc.stdout) > 44:
            return AudioSegment.from_file(io.BytesIO(proc.stdout), format="wav")
    except Exception as e:
        print(f"[Warning] atempo speed adjustment fallback: {e}")
        
    return audio

def adjust_audio_speed(audio: AudioSegment, target_duration_ms: float, max_speed_factor: float = 1.25) -> AudioSegment:
    """
    Professional Audio Alignment for Video Narration / Dubbing:
    1. Trims dead silence at the beginning and end of generated TTS.
    2. NEVER slows down audio when speech is shorter than target duration
       (eliminating deep/muffled/demonic 'ក្ងួរ' voice distortion).
    3. If speech exceeds target duration, applies smooth FFmpeg 'atempo'
       time-stretching with 100% PITCH PRESERVATION, capped at max_speed_factor
       so speech never sounds frantically rushed.
    """
    if len(audio) == 0 or target_duration_ms <= 0:
        return audio
        
    # Trim excess dead silence from start & end (leaving 40ms safety padding)
    try:
        from pydub.silence import detect_leading_silence
        lead = max(0, detect_leading_silence(audio) - 40)
        trail = max(0, detect_leading_silence(audio.reverse()) - 40)
        if len(audio) > (lead + trail + 150):
            audio = audio[lead : len(audio) - trail]
    except Exception:
        pass
        
    current_dur = len(audio)
    
    # CRITICAL: If audio is shorter than or equal to target duration,
    # DO NOT SLOW DOWN! Keep natural 1.0x human speaking tempo.
    if current_dur <= target_duration_ms:
        return audio
        
    # If it slightly exceeds (within 5%), let it play naturally
    speed_factor = current_dur / target_duration_ms
    if speed_factor <= 1.05:
        return audio
        
    # Cap speedup to 1.25x (or custom max) to keep speech intelligible & natural
    speed_factor = min(max_speed_factor, speed_factor)
    
    return change_audio_speed_atempo(audio, speed_factor)

# ---------------------------------------------------------
# Ultra-Fast Timeline Audio Stitcher (NumPy Buffer - 1000x Faster than Pydub Overlay)
# ---------------------------------------------------------
def stitch_audio_segments_fast(aligned_segments: list, total_duration_ms: int, frame_rate: int = 44100, channels: int = 2) -> AudioSegment:
    """
    Ultra-fast NumPy-based audio timeline stitching:
    Replaces slow iterative Pydub AudioSegment.overlay() (which copies gigabytes of RAM in Python)
    with direct zero-copy 16-bit PCM buffer placement in milliseconds.
    """
    if total_duration_ms <= 0:
        return AudioSegment.silent(duration=1000, frame_rate=frame_rate).set_channels(channels)
        
    total_samples = int(math.ceil(frame_rate * (total_duration_ms / 1000.0)))
    master_buffer = np.zeros((total_samples, channels), dtype=np.float32)
    
    for seg_audio, start_ms in aligned_segments:
        if not seg_audio or len(seg_audio) == 0:
            continue
        try:
            seg = seg_audio.set_frame_rate(frame_rate).set_channels(channels).set_sample_width(2)
            raw = np.frombuffer(seg.raw_data, dtype=np.int16).astype(np.float32)
            seg_samples = raw.reshape(-1, channels)
            start_sample = max(0, int(frame_rate * (start_ms / 1000.0)))
            end_sample = min(total_samples, start_sample + len(seg_samples))
            if start_sample < total_samples and end_sample > start_sample:
                slice_len = end_sample - start_sample
                master_buffer[start_sample:end_sample] += seg_samples[:slice_len]
        except Exception as e:
            print(f"[Warning] Fast audio stitch segment error: {e}")
            
    np.clip(master_buffer, -32768.0, 32767.0, out=master_buffer)
    pcm_bytes = master_buffer.astype(np.int16).tobytes()
    return AudioSegment(pcm_bytes, frame_rate=frame_rate, sample_width=2, channels=channels)

# ---------------------------------------------------------
# Extract Audio via FFmpeg
# ---------------------------------------------------------
def extract_audio_from_video(video_path: str, temp_dir: str) -> str:
    audio_path = os.path.join(temp_dir, "extracted_audio.wav")
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, env=os.environ)
    return audio_path

def extract_high_quality_audio(video_path: str, temp_dir: str) -> str:
    hq_audio = os.path.join(temp_dir, "hq_original_audio.wav")
    cmd = [
        FFMPEG_EXE, "-y",
        "-i", video_path,
        "-vn", "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
        hq_audio
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, env=os.environ)
    return hq_audio

def extract_demucs_bgm(audio_path: str, temp_dir: str) -> str:
    """Run Demucs AI to separate clean background music (no_vocals.wav)."""
    try:
        out_dir = os.path.join(temp_dir, "demucs_sep")
        os.makedirs(out_dir, exist_ok=True)
        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems=vocals",
            "-n", "htdemucs",
            "-d", "cpu",
            "-j", "2",
            "-o", out_dir,
            audio_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            for root, dirs, files in os.walk(out_dir):
                if "no_vocals.wav" in files:
                    return os.path.join(root, "no_vocals.wav")
        else:
            print(f"[Demucs] Returncode: {res.returncode}, Stderr: {res.stderr[:200] if res.stderr else ''}")
    except Exception as e:
        print(f"[Warning] Demucs separation: {e}")
    return ""

def vol_to_gain_db(vol_factor: float) -> float:
    """Converts a linear volume factor (0.0 to 2.5) to decibel gain (dB)."""
    if vol_factor <= 0.01:
        return -999.0
    return 20.0 * math.log10(vol_factor)

def create_clean_background_track(
    orig_audio: AudioSegment, 
    segments_data: list, 
    bg_vol: float, 
    mute_original_speech: bool = True,
    has_isolated_bgm: bool = False,
    custom_bgm_path: str = "",
    bgm_segments: list = None
) -> AudioSegment:
    """
    Creates an authentic, clean background music & effects track:
    - Supports multi-segment volume modulation (bgm_segments) so user can customize
      where background music is loud (up to 200%) and where it is soft or muted!
    - If custom_bgm_path provided: uses user's selected pure background music.
    - If has_isolated_bgm (from AI Demucs): plays pure isolated background music/ambience 
      with ZERO original vocals across the entire video.
    - If mute_original_speech is True:
      Replaces dialogue segments with 100% DIGITAL SILENCE so ZERO original foreign language 
      speech leaks through, while smoothly cross-fading ambient sound effects between sentences!
    """
    total_len = len(orig_audio)
    if total_len <= 0:
        return AudioSegment.silent(duration=1000, frame_rate=44100).set_channels(2)

    # 1. Base background audio source
    base_audio = None
    if custom_bgm_path and os.path.exists(custom_bgm_path):
        try:
            bg_music = AudioSegment.from_file(custom_bgm_path).set_frame_rate(44100).set_channels(2)
            if len(bg_music) < total_len:
                loops = int(math.ceil(total_len / max(1, len(bg_music)))) + 1
                bg_music = bg_music * loops
            base_audio = bg_music[:total_len]
        except Exception as e:
            print(f"[Warning] Custom BGM loading failed: {e}")

    if base_audio is None:
        base_audio = orig_audio.set_frame_rate(44100).set_channels(2)

    # 2. Modulate volume across timeline (by BGM segments or master bg_vol)
    if bgm_segments and len(bgm_segments) > 0:
        chunks = []
        curr_ms = 0
        sorted_segs = sorted([s for s in bgm_segments if s.get('end', 0) > s.get('start', 0)], key=lambda x: x['start'])
        for seg in sorted_segs:
            s_ms = max(0, min(total_len, int(seg['start'] * 1000)))
            e_ms = max(s_ms, min(total_len, int(seg['end'] * 1000)))
            
            # Fill unsegmented gap before this segment
            if s_ms > curr_ms:
                gap = base_audio[curr_ms:s_ms]
                if bg_vol <= 0.01:
                    gap = AudioSegment.silent(duration=len(gap), frame_rate=44100).set_channels(2)
                else:
                    gap = gap.apply_gain(vol_to_gain_db(bg_vol))
                chunks.append(gap)
                curr_ms = s_ms
                
            if e_ms > curr_ms:
                chunk = base_audio[curr_ms:e_ms]
                seg_v = seg.get('vol', bg_vol)
                if seg_v <= 0.01:
                    chunk = AudioSegment.silent(duration=len(chunk), frame_rate=44100).set_channels(2)
                else:
                    chunk = chunk.apply_gain(vol_to_gain_db(seg_v))
                    if len(chunk) > 50:
                        chunk = chunk.fade_in(15).fade_out(15)
                chunks.append(chunk)
                curr_ms = e_ms
                
        if curr_ms < total_len:
            rest = base_audio[curr_ms:total_len]
            if bg_vol <= 0.01:
                rest = AudioSegment.silent(duration=len(rest), frame_rate=44100).set_channels(2)
            else:
                rest = rest.apply_gain(vol_to_gain_db(bg_vol))
            chunks.append(rest)
            
        if chunks:
            bg_normal = chunks[0]
            for c in chunks[1:]:
                bg_normal += c
        else:
            bg_normal = base_audio.apply_gain(vol_to_gain_db(bg_vol)) if bg_vol > 0.01 else AudioSegment.silent(duration=total_len, frame_rate=44100).set_channels(2)
    else:
        if bg_vol <= 0.01:
            bg_normal = AudioSegment.silent(duration=total_len, frame_rate=44100).set_channels(2)
        else:
            bg_normal = base_audio.apply_gain(vol_to_gain_db(bg_vol))

    # 3. If already isolated BGM (Demucs or custom audio) or no dialogue segments, return full modulated track!
    if has_isolated_bgm or not segments_data:
        return bg_normal

    # 4. Dialogue mute / ducking (when using original video audio without Demucs)
    intervals = []
    for seg in sorted(segments_data, key=lambda s: s['start']):
        s_ms = max(0, int(seg['start'] * 1000) - 60)
        e_ms = min(total_len, int(seg['end'] * 1000) + 80)
        if intervals and s_ms <= intervals[-1][1]:
            intervals[-1] = (intervals[-1][0], max(intervals[-1][1], e_ms))
        else:
            intervals.append((s_ms, e_ms))

    final_chunks = []
    curr_ms = 0
    for s_ms, e_ms in intervals:
        # Non-speech section: Ambient background plays at modulated volume
        if s_ms > curr_ms:
            part = bg_normal[curr_ms:s_ms]
            if len(part) > 60:
                part = part.fade_out(25)
            final_chunks.append(part)
            
        # Speech section: If mute_original_speech, replace with 100% digital silence so NO original vocal leaks!
        if e_ms > s_ms:
            d_dur = e_ms - s_ms
            if mute_original_speech:
                chunk = AudioSegment.silent(duration=d_dur, frame_rate=44100).set_channels(2)
            else:
                chunk = bg_normal[s_ms:e_ms].apply_gain(-12.0)
                if len(chunk) > 40:
                    chunk = chunk.fade_in(20).fade_out(20)
            final_chunks.append(chunk)
        curr_ms = e_ms
        
    if curr_ms < total_len:
        part = bg_normal[curr_ms:]
        if len(part) > 60:
            part = part.fade_in(25)
        final_chunks.append(part)

    if not final_chunks:
        return bg_normal
        
    result = final_chunks[0]
    for c in final_chunks[1:]:
        result += c
    return result

def format_time(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

# =========================================================
# Subtitle Styling & Generator Engine (ASS & FFmpeg drawtext)
# =========================================================

def hex_to_ass_color(hex_str: str, opacity_pct: int = 100) -> str:
    """Converts #RRGGBB hex color and opacity (0-100) to ASS &HAABBGGRR color format."""
    if not hex_str or hex_str == "transparent":
        return "&HFF000000"
    hex_str = hex_str.lstrip('#')
    if len(hex_str) != 6:
        hex_str = "FFFFFF"
    r = int(hex_str[0:2], 16)
    g = int(hex_str[2:4], 16)
    b = int(hex_str[4:6], 16)
    # In ASS format: alpha 0 = fully opaque, 255 = fully transparent
    alpha = int(round((1.0 - (max(0, min(100, opacity_pct)) / 100.0)) * 255))
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def format_ass_time(sec: float) -> str:
    """Formats seconds into ASS timestamp H:MM:SS.cs."""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_ass_subtitles(
    segments: list,
    video_w: int = 1280,
    video_h: int = 720,
    font_family: str = "Khmer OS Battambang",
    font_size: int = 24,
    text_color: str = "#FFFFFF",
    bg_color: str = "#000000",
    bg_opacity: int = 90,
    enable_subtitle_background: bool = True,
    pos_x_pct: float = 50.0,
    pos_y_pct: float = 85.0,
    box_full_width: bool = False
) -> str:
    """
    Generates Advanced SubStation Alpha (.ass) subtitle script text.
    Respects enable_subtitle_background:
      - When False: BorderStyle=1, Outline=1 (or 0), Shadow=0, and BackColour is fully transparent (&HFF000000).
      - When True: BorderStyle=3 (opaque bounding box) with BackColour set to chosen color/opacity.
    """
    pri_col = hex_to_ass_color(text_color, 100)

    # If font_size is given in UI preview pixels (typically 12..40), scale proportionally to video_h:
    # Baseline UI preview height is ~260px.
    if font_size <= 45:
        calc_font_size = max(24, int(round(font_size * (max(1, video_h) / 260.0))))
    else:
        calc_font_size = font_size

    if not enable_subtitle_background:
        # BorderStyle=1, Outline, Shadow=0, and BackColour fully transparent
        border_style = 1
        outline = max(1, int(round(calc_font_size * 0.08)))
        shadow = 0
        back_col = "&HFF000000"  # Fully transparent in ASS format (&HFF alpha)
        outl_col = "&H80000000"  # Subtle dark outline for high contrast readability
    else:
        # BorderStyle=3 (opaque bounding box)
        border_style = 3
        outline = 0
        shadow = 0
        back_col = hex_to_ass_color(bg_color, bg_opacity)
        outl_col = back_col

    # Vertical margin from bottom
    margin_v = max(10, int(video_h * (1.0 - (pos_y_pct / 100.0))))
    margin_lr = 10 if box_full_width else max(20, int(video_w * 0.04))

    ass_lines = [
        "[Script Info]",
        "Title: Khmer Dubbed Subtitles",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.601",
        f"PlayResX: {video_w}",
        f"PlayResY: {video_h}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_family},{calc_font_size},{pri_col},&H000000FF,{outl_col},{back_col},-1,0,0,0,100,100,0,0,{border_style},{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]

    for s in (segments or []):
        start_t = s.get('start', 0.0)
        end_t = s.get('end', 0.0)
        if end_t <= start_t:
            continue
        text = ""
        # 1. Check synced 'khmer' text first
        if s.get('khmer'):
            text = str(s['khmer']).strip()
        # 2. Check widget get() if khmer is empty
        elif 'widget' in s and hasattr(s['widget'], 'get'):
            try:
                text = s['widget'].get().strip()
            except Exception:
                pass
        # 3. Fallback to orig
        if not text:
            text = s.get('orig', '').strip()
        if not text:
            continue

        clean_text = text.replace('\\N', ' ').replace('\n', '\\N')
        start_str = format_ass_time(start_t)
        end_str = format_ass_time(end_t)
        ass_lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{clean_text}")

    return "\n".join(ass_lines) + "\n"


def generate_ass_subtitle_file(segments: list, output_ass_path: str, **kwargs) -> str:
    """Generates and writes .ass subtitle file with UTF-8 encoding."""
    content = generate_ass_subtitles(segments, **kwargs)
    with open(output_ass_path, "w", encoding="utf-8-sig") as f:
        f.write(content)
    return output_ass_path


def build_ffmpeg_drawtext_filter(
    text: str,
    fontfile: str = None,
    fontsize: int = 24,
    fontcolor: str = "white",
    enable_subtitle_background: bool = False,
    boxcolor: str = "black",
    boxopacity: float = 0.9,
    boxborderw: int = 6,
    x_expr: str = "(w-text_w)/2",
    y_expr: str = "h-th-40"
) -> str:
    """
    Builds an FFmpeg drawtext video filter string respecting enable_subtitle_background:
      - When False: box=0, borderw=0, shadowx=0, shadowy=0 (no dark blur behind text).
      - When True: box=1 with boxcolor and boxborderw.
    """
    params = []
    if fontfile and os.path.exists(fontfile):
        safe_font = fontfile.replace('\\', '/').replace(':', '\\:')
        params.append(f"fontfile='{safe_font}'")
    params.append(f"fontsize={fontsize}")
    params.append(f"fontcolor={fontcolor}")
    params.append(f"x={x_expr}")
    params.append(f"y={y_expr}")

    if not enable_subtitle_background:
        # User requirement: box=0, borderw=0, shadowx=0, shadowy=0
        params.append("box=0")
        params.append("borderw=0")
        params.append("shadowx=0")
        params.append("shadowy=0")
    else:
        params.append("box=1")
        params.append(f"boxcolor={boxcolor}@{boxopacity:.2f}")
        params.append(f"boxborderw={boxborderw}")
        params.append("shadowx=0")
        params.append("shadowy=0")

    safe_text = text.replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")
    params.append(f"text='{safe_text}'")
    return "drawtext=" + ":".join(params)

# ---------------------------------------------------------
# Embedded Video & Audio Player Component
# ---------------------------------------------------------
class EmbeddedVideoPlayer(ctk.CTkFrame):
    def __init__(self, master, on_time_update=None, on_size_change=None, get_khmer_audio_cb=None, on_request_generate_voice=None, on_play_state_change=None, on_audio_mode_change=None, on_remove_video=None, **kwargs):
        super().__init__(master, **kwargs)
        self.on_time_update = on_time_update
        self.on_size_change = on_size_change
        self.get_khmer_audio_cb = get_khmer_audio_cb
        self.on_request_generate_voice = on_request_generate_voice
        self.on_play_state_change = on_play_state_change
        self.on_audio_mode_change = on_audio_mode_change
        self.on_remove_video = on_remove_video
        
        self.video_path = ""
        self.audio_path = ""
        self.orig_audio_path = ""
        self.khmer_audio_path = ""
        self.active_audio_mode = "orig"
        self.cap = None
        self.is_playing = False
        self.is_paused = False
        self.fps = 25.0
        self.total_duration_sec = 0.0
        self.current_time_sec = 0.0
        self.total_frames = 0
        self._timer_id = None
        self._start_wall_time = 0.0
        self._start_pos_sec = 0.0
        self._mci_alias = f"emb_vplayer_{int(time.time()*1000) % 1000000}"
        self._has_audio = False
        self._display_w = 460
        self._display_h = 260
        self._is_seeking = False
        
        # Interactive Zoom & Pan State
        self.zoom_factor = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False
        self._last_frame = None

        # Subtitle & Hardsub Masking Configuration (Interactive Native Typography)
        self.cc_enabled = True
        self.cc_font_family = "Khmer OS Battambang"
        self.cc_font_size = 18
        self.cc_pos_x_pct = 50.0  # Horizontal position percentage (10% to 90%)
        self.cc_pos_y_pct = 85.0  # Vertical position percentage (10% to 95%)
        self.cc_box_full_width = False  # Fit to text length by default (ទំហំប្រហាក់ប្រហែលអក្សរ)
        self.cc_bg_enabled = True  # Toggle for subtitle background (បើក/បិទ ផ្ទៃខាងក្រោយអក្សរ)
        self.cc_base_bg_color = "#000000"
        self.cc_bg_opacity = 90  # Opacity: 0% (transparent) to 100% (solid)
        self.cc_text_color = "#FFFFFF"
        self.cc_subtitles = []
        self._sub_drag_origin_x = 0
        self._sub_drag_origin_y = 0
        self._sub_drag_init_x = 50.0
        self._sub_drag_init_y = 85.0
        
        # Video Transformation State (Flip & Crop)
        self.flip_horizontal = False
        self.flip_vertical = False
        self.crop_mode = "none"  # "none", "9:16", "16:9", "1:1", "4:3", "2.35:1", "custom"
        self.crop_margins = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        self._crop_dialog = None
        
        self._build_ui()
        self.bind("<Configure>", self._on_player_responsive_configure)

    def _build_ui(self):
        # Header / Status bar
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=6, pady=(4, 2))
        self.hdr = hdr
        
        self.hdr_title = ctk.CTkLabel(
            hdr, 
            text="🎥 ផ្ទាំងចាក់វីដេអូ (Video Player)", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#60A5FA"
        )
        self.hdr_title.pack(side="left")
        
        # Interactive Zoom Toolbar (➖, 100%, ➕, Fit, Fill)
        zoom_box = ctk.CTkFrame(hdr, fg_color="transparent")
        zoom_box.pack(side="left", padx=(4, 2))
        self.zoom_box = zoom_box
        
        self.btn_zoom_out = ctk.CTkButton(
            zoom_box, text="➖", width=24, height=20,
            fg_color="#1E293B", hover_color="#334155", font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.zoom_out(0.15)
        )
        self.btn_zoom_out.pack(side="left", padx=1)

        self.lbl_zoom_val = ctk.CTkLabel(
            zoom_box, text="100%", width=36, height=20,
            font=ctk.CTkFont(size=10, family="Consolas", weight="bold"),
            text_color="#38BDF8"
        )
        self.lbl_zoom_val.pack(side="left", padx=1)

        self.btn_zoom_in = ctk.CTkButton(
            zoom_box, text="➕", width=24, height=20,
            fg_color="#1E293B", hover_color="#334155", font=ctk.CTkFont(size=10, weight="bold"),
            command=lambda: self.zoom_in(0.15)
        )
        self.btn_zoom_in.pack(side="left", padx=1)

        self.btn_zoom_fit = ctk.CTkButton(
            zoom_box, text="Fit", width=30, height=20,
            fg_color="#334155", hover_color="#475569", font=ctk.CTkFont(size=10, weight="bold"),
            command=self.zoom_fit
        )
        self.btn_zoom_fit.pack(side="left", padx=1)

        self.btn_zoom_fill = ctk.CTkButton(
            zoom_box, text="Fill", width=34, height=20,
            fg_color="#0284C7", hover_color="#0369A1", font=ctk.CTkFont(size=10, weight="bold"),
            command=self.zoom_fill
        )
        self.btn_zoom_fill.pack(side="left", padx=1)
        
        # Player Size Preset Dropdown (Single Button to select Small / Medium / Large)
        self.size_dropdown = ctk.CTkOptionMenu(
            hdr,
            values=["📐 តូច", "📐 មធ្យម", "📐 ធំ"],
            width=84,
            height=20,
            fg_color="#1E293B",
            button_color="#334155",
            button_hover_color="#475569",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            command=self._on_size_preset_selected
        )
        self.size_dropdown.set("📐 មធ្យម")
        self.size_dropdown.pack(side="left", padx=2)

        # Interactive Video Transform Toolbar (✂️ Crop)
        tf_box = ctk.CTkFrame(hdr, fg_color="transparent")
        tf_box.pack(side="left", padx=(3, 2))
        self.tf_box = tf_box

        self.btn_crop = ctk.CTkButton(
            tf_box, text="✂️ Crop", width=52, height=20,
            fg_color="#1E293B", hover_color="#334155",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._open_crop_dialog
        )
        self.btn_crop.pack(side="left", padx=1)
        
        self.status_badge = ctk.CTkLabel(
            hdr,
            text="⏹️ មិនទាន់ចាក់",
            font=ctk.CTkFont(size=11),
            text_color="#9CA3AF"
        )
        self.status_badge.pack(side="right")
        
        # Seek slider & controls row: PINNED TO BOTTOM so it NEVER disappears when dragging timeline up/down!
        seek_row = ctk.CTkFrame(self, fg_color="transparent")
        seek_row.pack(side="bottom", fill="x", padx=6, pady=(3, 3))
        self.seek_row = seek_row

        self.mini_play_btn = ctk.CTkButton(
            seek_row, 
            text="▶", 
            width=28, 
            height=24, 
            fg_color="#059669", 
            hover_color="#047857", 
            font=ctk.CTkFont(size=12, weight="bold"), 
            command=self.toggle_play
        )
        self.mini_play_btn.pack(side="left", padx=(0, 4))

        # Audio Track Dropdown (OptionMenu like language selector) packed on right side first!
        self.audio_track_dropdown = ctk.CTkOptionMenu(
            seek_row,
            values=["🌐 ភាសាដើម (Original)", "🇰🇭 ភាសាខ្មែរ (Khmer Dub)"],
            width=160,
            height=24,
            command=self._on_audio_track_selected,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            fg_color="#1E293B",
            button_color="#334155",
            button_hover_color="#475569"
        )
        self.audio_track_dropdown.set("🌐 ភាសាដើម (Original)")
        self.audio_track_dropdown.pack(side="right", padx=(4, 0))

        self.time_label = ctk.CTkLabel(
            seek_row,
            text="00:00 / 00:00",
            font=ctk.CTkFont(size=11, family="Consolas", weight="bold"),
            text_color="#94A3B8",
            width=80
        )
        self.time_label.pack(side="right", padx=(4, 2))

        # Seek Slider dynamically takes the entire flexible center space between left play btn and right controls!
        self.seek_slider = ctk.CTkSlider(
            seek_row,
            from_=0.0,
            to=100.0,
            number_of_steps=500,
            command=self._on_slider_change
        )
        self.seek_slider.set(0.0)
        self.seek_slider.pack(side="left", fill="x", expand=True, padx=(2, 4))
        self.seek_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # Screen Container (Dark video canvas box) - Expands to fill middle space between header and seek_row
        self.screen_frame = ctk.CTkFrame(
            self, 
            fg_color="#090D16", 
            corner_radius=8, 
            width=self._display_w, 
            height=self._display_h
        )
        self.screen_frame.pack(side="top", fill="both", expand=True, padx=10, pady=2)
        self.screen_frame.pack_propagate(False)
        self.screen_frame.bind("<Configure>", lambda e: self._on_screen_resize())

        # Screen Canvas: provides true per-pixel transparency for subtitles over video frames!
        self.screen_canvas = tk.Canvas(
            self.screen_frame,
            bg="#090D16",
            highlightthickness=0,
            bd=0
        )
        self.screen_canvas.pack(fill="both", expand=True)

        # Canvas Items for Video Frame, Placeholder, Subtitle BG and Subtitle Text
        self._video_img_id = self.screen_canvas.create_image(0, 0, anchor="center", state="hidden")
        self._placeholder_text_id = self.screen_canvas.create_text(
            self._display_w // 2,
            self._display_h // 2,
            text="🎬 សូមជ្រើសរើសវីដេអូដើម្បីបង្ហាញនៅទីនេះ\n(Select Video File)\n\n💡 ជំនួយ៖ ប្រើ Scroll Mouse ដើម្បី Zoom • អូស Mouse ដើម្បីរំកិល Pan",
            font=(KHMER_FONT_NAME, 11),
            fill="#64748B",
            justify="center"
        )
        self._sub_bg_poly_id = self.screen_canvas.create_polygon(
            0, 0, 0, 0,
            fill="",
            outline="",
            state="hidden",
            tags="subtitle_drag"
        )
        self._sub_text_id = self.screen_canvas.create_text(
            0, 0,
            text="",
            fill=self.cc_text_color,
            font=(self.cc_font_family, self.cc_font_size, "bold"),
            justify="center",
            state="hidden",
            tags="subtitle_drag"
        )

        # Compatibility proxy for screen_label configure calls
        orig_config = self.screen_canvas.configure
        def _compat_screen_configure(*args, **kwargs):
            if 'image' in kwargs:
                img = kwargs.pop('image')
                if img is None:
                    self.screen_canvas.itemconfigure(self._video_img_id, state="hidden")
                else:
                    self.screen_canvas.itemconfigure(self._video_img_id, image=img, state="normal")
                    self.screen_canvas.image = img
            if 'text' in kwargs:
                txt = kwargs.pop('text')
                if txt:
                    self.screen_canvas.itemconfigure(self._placeholder_text_id, text=txt, state="normal")
                else:
                    self.screen_canvas.itemconfigure(self._placeholder_text_id, state="hidden")
            if kwargs:
                return orig_config(*args, **kwargs)
        self.screen_canvas.configure = _compat_screen_configure
        self.screen_canvas.config = _compat_screen_configure
        self.screen_label = self.screen_canvas

        # Dummy widgets for legacy sub_frame / sub_text_lbl references
        class _DummyWidget:
            def place_forget(self): pass
            def lift(self): pass
            def configure(self, **kw): pass
            def config(self, **kw): pass
            def bind(self, *a, **k): pass
            def pack(self, *a, **k): pass
            def pack_forget(self): pass
            def cget(self, k): return ""
        self.sub_frame = _DummyWidget()
        self.sub_text_lbl = _DummyWidget()

        # Drag-and-Drop Subtitle Positioning on Canvas
        self.screen_canvas.tag_bind("subtitle_drag", "<Button-1>", self._on_sub_drag_start)
        self.screen_canvas.tag_bind("subtitle_drag", "<B1-Motion>", self._on_sub_drag_motion)

        # Mouse Wheel & Pan Gestures on Video Canvas
        self.screen_canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.screen_frame.bind("<MouseWheel>", self._on_mouse_wheel)
        self.screen_canvas.bind("<Button-1>", self._on_drag_start)
        self.screen_canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.screen_canvas.bind("<ButtonRelease-1>", self._on_drag_stop)
        self.screen_canvas.bind("<Double-Button-1>", self._on_double_click)

    def _on_mouse_wheel(self, event):
        """Scroll mouse wheel to zoom in / zoom out smoothly."""
        if event.delta > 0:
            self.zoom_in(0.15)
        elif event.delta < 0:
            self.zoom_out(0.15)

    def _on_drag_start(self, event):
        """Start dragging/panning video viewport when zoomed in."""
        try:
            items = self.screen_canvas.find_withtag("current")
            if items:
                tags = self.screen_canvas.gettags(items[0])
                if "subtitle_drag" in tags:
                    return
        except Exception:
            pass

        if self.zoom_factor > 1.02:
            self._is_dragging = True
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            try:
                self.screen_canvas.configure(cursor="fleur")
            except Exception:
                pass

    def _on_drag_motion(self, event):
        """Pan video crop following mouse motion."""
        if getattr(self, '_is_dragging', False):
            dx = event.x - self._drag_start_x
            dy = event.y - self._drag_start_y
            self.pan_offset_x += dx
            self.pan_offset_y += dy
            self._drag_start_x = event.x
            self._drag_start_y = event.y
            if self._last_frame is not None:
                self._render_frame_to_screen(self._last_frame)

    def _on_drag_stop(self, event):
        """Release mouse pan drag."""
        self._is_dragging = False
        try:
            self.screen_canvas.configure(cursor="arrow")
        except Exception:
            pass

    def _on_double_click(self, event):
        """Double click to toggle between Fit (1.0x) and Fill."""
        if self.zoom_factor > 1.1:
            self.zoom_fit()
        else:
            self.zoom_fill()

    def _on_screen_resize(self):
        """Re-render cached frame on panel container resize."""
        if hasattr(self, 'screen_canvas') and hasattr(self, '_placeholder_text_id'):
            fw = max(100, self.screen_frame.winfo_width())
            fh = max(100, self.screen_frame.winfo_height())
            self.screen_canvas.coords(self._placeholder_text_id, fw // 2, fh // 2)
        if not self.is_playing and self._last_frame is not None:
            self._render_frame_to_screen(self._last_frame)
        else:
            self.update_subtitle_display()

    def set_zoom(self, factor: float):
        """Set zoom factor clamped between 0.5x and 4.0x."""
        self.zoom_factor = max(0.5, min(4.0, factor))
        if self.zoom_factor <= 1.05:
            self.pan_offset_x = 0.0
            self.pan_offset_y = 0.0
        self._update_zoom_label()
        if self._last_frame is not None:
            self._render_frame_to_screen(self._last_frame)
        elif self.cap:
            self._show_frame_at_sec(self.current_time_sec)

    def zoom_in(self, step: float = 0.15):
        self.set_zoom(self.zoom_factor + step)

    def zoom_out(self, step: float = 0.15):
        self.set_zoom(self.zoom_factor - step)

    def zoom_fit(self):
        """Reset zoom to Fit (100% full frame view)."""
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.set_zoom(1.0)

    def zoom_fill(self):
        """Automatically scale to completely fill screen viewport eliminating black bars."""
        if self._last_frame is not None:
            h, w = self._last_frame.shape[:2]
        elif self.cap and self.cap.isOpened():
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
        else:
            w, h = 1920, 1080
        
        fw = self.screen_frame.winfo_width()
        fh = self.screen_frame.winfo_height()
        dw = fw if fw > 100 else self._display_w
        dh = fh if fh > 100 else self._display_h
        
        base_scale = min(dw / w, dh / h) if w > 0 and h > 0 else 1.0
        fill_scale = max(dw / w, dh / h) if w > 0 and h > 0 else 1.0
        if base_scale > 0:
            factor = fill_scale / base_scale
            self.pan_offset_x = 0.0
            self.pan_offset_y = 0.0
            self.set_zoom(factor)
        else:
            self.set_zoom(1.5)

    def _update_zoom_label(self):
        if hasattr(self, 'lbl_zoom_val'):
            pct = int(round(self.zoom_factor * 100))
            self.lbl_zoom_val.configure(text=f"{pct}%")

    def _render_frame_to_screen(self, frame):
        """Render OpenCV frame to canvas with zoom, pan, ROI cropping, flip, and aspect ratio crop."""
        if frame is None:
            return
        self._last_frame = frame.copy()
        try:
            work_frame = frame
            # 1. Apply Video Crop if configured
            crop_box = self.get_effective_crop_box(work_frame.shape[1], work_frame.shape[0])
            if crop_box is not None:
                cx1, cy1, cx2, cy2 = crop_box
                if cx2 > cx1 and cy2 > cy1:
                    work_frame = work_frame[cy1:cy2, cx1:cx2]

            # 2. Apply Video Flip (Horizontal / Mirror & Vertical)
            if getattr(self, 'flip_horizontal', False):
                work_frame = cv2.flip(work_frame, 1)
            if getattr(self, 'flip_vertical', False):
                work_frame = cv2.flip(work_frame, 0)

            fw = self.screen_frame.winfo_width()
            fh = self.screen_frame.winfo_height()
            dw = fw if fw > 100 else self._display_w
            dh = fh if fh > 100 else self._display_h
            h, w = work_frame.shape[:2]
            if w <= 0 or h <= 0:
                return

            base_scale = min(dw / w, dh / h)
            eff_scale = base_scale * self.zoom_factor

            target_w = eff_scale * w
            target_h = eff_scale * h

            if target_w <= dw and target_h <= dh:
                self.pan_offset_x = 0.0
                self.pan_offset_y = 0.0
                nw = max(1, int(round(target_w)))
                nh = max(1, int(round(target_h)))
                resized = cv2.resize(work_frame, (nw, nh), interpolation=cv2.INTER_AREA if eff_scale < 1.0 else cv2.INTER_LINEAR)
            else:
                vis_w = min(float(w), dw / eff_scale)
                vis_h = min(float(h), dh / eff_scale)

                max_pan_x = max(0.0, (target_w - dw) / 2.0)
                max_pan_y = max(0.0, (target_h - dh) / 2.0)
                self.pan_offset_x = max(-max_pan_x, min(max_pan_x, self.pan_offset_x))
                self.pan_offset_y = max(-max_pan_y, min(max_pan_y, self.pan_offset_y))

                cx = (w / 2.0) - (self.pan_offset_x / eff_scale)
                cy = (h / 2.0) - (self.pan_offset_y / eff_scale)

                x1 = int(round(max(0.0, min(float(w) - vis_w, cx - vis_w / 2.0))))
                y1 = int(round(max(0.0, min(float(h) - vis_h, cy - vis_h / 2.0))))
                x2 = int(round(min(float(w), x1 + vis_w)))
                y2 = int(round(min(float(h), y1 + vis_h)))

                crop = work_frame[y1:y2, x1:x2]
                if crop.size == 0:
                    return

                out_w = max(1, min(dw, int(round((x2 - x1) * eff_scale))))
                out_h = max(1, min(dh, int(round((y2 - y1) * eff_scale))))
                resized = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

            frame_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            out_h, out_w = resized.shape[:2]
            img = Image.fromarray(frame_rgb)

            # Check for active subtitle dialogue
            active_text = ""
            if getattr(self, 'cc_enabled', True) and getattr(self, 'cc_subtitles', None):
                t = self.current_time_sec
                for s in self.cc_subtitles:
                    if s.get('start', 0.0) <= t <= s.get('end', 0.0):
                        if 'widget' in s and hasattr(s['widget'], 'get'):
                            try:
                                active_text = s['widget'].get().strip()
                            except Exception:
                                pass
                        if not active_text:
                            active_text = s.get('khmer', s.get('orig', '')).strip()
                        break

            cx = dw // 2
            cy = dh // 2
            img_x1 = cx - out_w // 2
            img_y1 = cy - out_h // 2

            rx = int(round((self.cc_pos_x_pct / 100.0) * dw))
            ry = int(round((self.cc_pos_y_pct / 100.0) * dh))
            max_wrap = max(160, dw - 48)

            eff_bg = getattr(self, 'cc_base_bg_color', '#000000')
            opacity = getattr(self, 'cc_bg_opacity', 90)
            bg_is_enabled = bool(getattr(self, 'cc_bg_enabled', True)) and eff_bg != "transparent" and opacity > 5

            if active_text:
                self.screen_canvas.itemconfigure(
                    self._sub_text_id,
                    text=active_text,
                    fill=self.cc_text_color,
                    font=(self.cc_font_family, self.cc_font_size, "bold"),
                    width=max_wrap,
                    justify="center",
                    state="normal"
                )
                self.screen_canvas.coords(self._sub_text_id, rx, ry)

                if bg_is_enabled:
                    bbox = self.screen_canvas.bbox(self._sub_text_id)
                    if bbox:
                        pad_x = 14
                        pad_y = 6
                        if getattr(self, 'cc_box_full_width', False):
                            bx1 = 0
                            bx2 = out_w
                            by1 = max(0, min(out_h, bbox[1] - img_y1 - 5))
                            by2 = max(0, min(out_h, bbox[3] - img_y1 + 5))
                        else:
                            bx1 = max(0, min(out_w, bbox[0] - img_x1 - pad_x))
                            by1 = max(0, min(out_h, bbox[1] - img_y1 - pad_y))
                            bx2 = max(0, min(out_w, bbox[2] - img_x1 + pad_x))
                            by2 = max(0, min(out_h, bbox[3] - img_y1 + pad_y))

                        if bx2 > bx1 and by2 > by1:
                            c_hex = eff_bg.lstrip('#')
                            if len(c_hex) != 6:
                                c_hex = "000000"
                            try:
                                r = int(c_hex[0:2], 16)
                                g = int(c_hex[2:4], 16)
                                b = int(c_hex[4:6], 16)
                            except Exception:
                                r, g, b = 0, 0, 0
                            # Per-pixel alpha: softly tints the background matching the slider!
                            alpha = int(round(255 * (max(0, min(100, opacity)) / 100.0)))

                            img_rgba = img.convert("RGBA")
                            overlay = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
                            draw = ImageDraw.Draw(overlay)
                            draw.rounded_rectangle([bx1, by1, bx2, by2], radius=6, fill=(r, g, b, alpha))
                            img = Image.alpha_composite(img_rgba, overlay).convert("RGB")
            else:
                self.screen_canvas.itemconfigure(self._sub_text_id, state="hidden")

            # Always hide the canvas solid polygon so it never draws an opaque box
            self.screen_canvas.itemconfigure(self._sub_bg_poly_id, state="hidden")

            photo = ImageTk.PhotoImage(image=img)
            self._current_photo = photo
            self.screen_canvas.image = photo

            self.screen_canvas.coords(self._video_img_id, cx, cy)
            self.screen_canvas.itemconfigure(self._video_img_id, image=photo, state="normal")
            self.screen_canvas.itemconfigure(self._placeholder_text_id, state="hidden")

            if active_text:
                self.screen_canvas.tag_raise(self._sub_text_id, self._video_img_id)
        except Exception:
            pass

    def _on_sub_drag_start(self, event):
        """Initiates direct drag-and-drop movement of the subtitle banner on the video player."""
        self._sub_drag_origin_x = event.x_root
        self._sub_drag_origin_y = event.y_root
        self._sub_drag_init_x = self.cc_pos_x_pct
        self._sub_drag_init_y = self.cc_pos_y_pct

    def _on_sub_drag_motion(self, event):
        """Updates subtitle banner position smoothly following mouse drag across the video preview."""
        fw = max(100, self.screen_canvas.winfo_width())
        fh = max(100, self.screen_canvas.winfo_height())
        dx = ((event.x_root - self._sub_drag_origin_x) / float(fw)) * 100.0
        dy = ((event.y_root - self._sub_drag_origin_y) / float(fh)) * 100.0
        self.cc_pos_x_pct = max(5.0, min(95.0, round(self._sub_drag_init_x + dx, 1)))
        self.cc_pos_y_pct = max(5.0, min(95.0, round(self._sub_drag_init_y + dy, 1)))
        self.refresh_current_frame()

    def _get_effective_bg_color(self):
        """Calculates effective background color based on user-selected color, opacity and bg toggle."""
        if not getattr(self, 'cc_bg_enabled', True):
            return "transparent"
        base = getattr(self, 'cc_base_bg_color', '#000000')
        opacity = getattr(self, 'cc_bg_opacity', 90)
        if base == "transparent" or opacity <= 5:
            return "transparent"
        return base

    def _get_round_rect_points(self, x1, y1, x2, y2, radius=8):
        """Generates 12 polygon vertices for a smooth rounded rectangle on Tkinter canvas."""
        radius = min(radius, max(1, (x2 - x1) / 2), max(1, (y2 - y1) / 2))
        return [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1
        ]

    def _position_subtitle_widget(self):
        """Refreshes subtitle canvas items."""
        self.refresh_current_frame()

    def update_subtitle_display(self):
        """
        Finds active dialogue for current timestamp and renders subtitle with per-pixel alpha transparency.
        Delegates to _render_frame_to_screen if a frame is cached.
        """
        if self._last_frame is not None:
            self._render_frame_to_screen(self._last_frame)
            return

        if not hasattr(self, 'screen_canvas'):
            return

        if not getattr(self, 'cc_enabled', True) or not getattr(self, 'cc_subtitles', None):
            self.screen_canvas.itemconfigure(self._sub_bg_poly_id, state="hidden")
            self.screen_canvas.itemconfigure(self._sub_text_id, state="hidden")
            return

        t = self.current_time_sec
        active_text = ""
        for s in self.cc_subtitles:
            if s.get('start', 0.0) <= t <= s.get('end', 0.0):
                if 'widget' in s and hasattr(s['widget'], 'get'):
                    try:
                        active_text = s['widget'].get().strip()
                    except Exception:
                        pass
                if not active_text:
                    active_text = s.get('khmer', s.get('orig', '')).strip()
                break

        if not active_text:
            self.screen_canvas.itemconfigure(self._sub_bg_poly_id, state="hidden")
            self.screen_canvas.itemconfigure(self._sub_text_id, state="hidden")
            return

        fw = max(100, self.screen_canvas.winfo_width())
        fh = max(100, self.screen_canvas.winfo_height())
        rx = (self.cc_pos_x_pct / 100.0) * fw
        ry = (self.cc_pos_y_pct / 100.0) * fh
        max_wrap = max(160, fw - 48)

        self.screen_canvas.itemconfigure(
            self._sub_text_id,
            text=active_text,
            fill=self.cc_text_color,
            font=(self.cc_font_family, self.cc_font_size, "bold"),
            width=max_wrap,
            justify="center",
            state="normal"
        )
        self.screen_canvas.coords(self._sub_text_id, rx, ry)
        self.screen_canvas.itemconfigure(self._sub_bg_poly_id, state="hidden")
        self.screen_canvas.tag_raise(self._sub_text_id, self._video_img_id)

    def get_subtitle_style_config(self) -> dict:
        """Returns the current subtitle configuration dictionary for ASS generator and FFmpeg drawtext."""
        return {
            "font_family": getattr(self, "cc_font_family", "Khmer OS Battambang"),
            "font_size": getattr(self, "cc_font_size", 24),
            "text_color": getattr(self, "cc_text_color", "#FFFFFF"),
            "bg_color": getattr(self, "cc_base_bg_color", "#000000"),
            "bg_opacity": getattr(self, "cc_bg_opacity", 90),
            "enable_subtitle_background": bool(getattr(self, "cc_bg_enabled", True)),
            "pos_x_pct": getattr(self, "cc_pos_x_pct", 50.0),
            "pos_y_pct": getattr(self, "cc_pos_y_pct", 85.0),
            "box_full_width": bool(getattr(self, "cc_box_full_width", False)),
            "enabled": bool(getattr(self, "cc_enabled", True)),
        }

    def refresh_current_frame(self):
        """Immediately re-renders the current frame to reflect changes to CC subtitle size, font, or position."""
        if self._last_frame is not None:
            self._render_frame_to_screen(self._last_frame)
        elif self.cap and self.cap.isOpened():
            self._show_frame_at_sec(self.current_time_sec)
        else:
            self.update_subtitle_display()

    def get_effective_crop_box(self, orig_w: int, orig_h: int):
        """
        Calculate pixel crop box (x1, y1, x2, y2) based on crop_mode and crop_margins.
        Returns None if no crop is active.
        Guarantees (x2 - x1) and (y2 - y1) are even numbers for FFmpeg compatibility.
        """
        if orig_w <= 0 or orig_h <= 0:
            return None
            
        mode = getattr(self, 'crop_mode', 'none')
        margins = getattr(self, 'crop_margins', {})
        
        has_custom_margins = any(margins.get(k, 0.0) > 0.01 for k in ['top', 'bottom', 'left', 'right'])
        
        if mode == "none" and not has_custom_margins:
            return None

        if mode == "custom" or (mode == "none" and has_custom_margins):
            left_pct = max(0.0, min(40.0, margins.get('left', 0.0)))
            right_pct = max(0.0, min(40.0, margins.get('right', 0.0)))
            top_pct = max(0.0, min(40.0, margins.get('top', 0.0)))
            bottom_pct = max(0.0, min(40.0, margins.get('bottom', 0.0)))

            x1 = int(round(orig_w * left_pct / 100.0))
            y1 = int(round(orig_h * top_pct / 100.0))
            x2 = int(round(orig_w * (1.0 - right_pct / 100.0)))
            y2 = int(round(orig_h * (1.0 - bottom_pct / 100.0)))
        else:
            aspect_map = {
                "9:16": 9.0 / 16.0,
                "16:9": 16.0 / 9.0,
                "1:1": 1.0,
                "4:3": 4.0 / 3.0,
                "2.35:1": 2.35
            }
            target_ratio = aspect_map.get(mode)
            if not target_ratio:
                return None
                
            cur_ratio = orig_w / max(1, orig_h)
            if cur_ratio > target_ratio:
                target_w = int(round(orig_h * target_ratio))
                target_h = orig_h
                x1 = (orig_w - target_w) // 2
                y1 = 0
                x2 = x1 + target_w
                y2 = orig_h
            else:
                target_w = orig_w
                target_h = int(round(orig_w / target_ratio))
                x1 = 0
                y1 = (orig_h - target_h) // 2
                x2 = orig_w
                y2 = y1 + target_h

        x1 = max(0, min(orig_w - 4, x1))
        y1 = max(0, min(orig_h - 4, y1))
        x2 = max(x1 + 4, min(orig_w, x2))
        y2 = max(y1 + 4, min(orig_h, y2))

        cw = x2 - x1
        ch = y2 - y1
        if cw % 2 != 0:
            cw -= 1
        if ch % 2 != 0:
            ch -= 1
        x2 = x1 + max(2, cw)
        y2 = y1 + max(2, ch)

        return (x1, y1, x2, y2)

    def toggle_flip_horizontal(self):
        self.flip_horizontal = not getattr(self, 'flip_horizontal', False)
        self._update_transform_buttons()
        self.refresh_current_frame()
        if getattr(self, '_crop_dialog', None) and self._crop_dialog.winfo_exists():
            self._crop_dialog._update_ui_state()

    def toggle_flip_vertical(self):
        self.flip_vertical = not getattr(self, 'flip_vertical', False)
        self._update_transform_buttons()
        self.refresh_current_frame()
        if getattr(self, '_crop_dialog', None) and self._crop_dialog.winfo_exists():
            self._crop_dialog._update_ui_state()

    def set_crop(self, mode: str, margins: dict = None):
        self.crop_mode = mode
        if margins:
            self.crop_margins.update(margins)
        elif mode == "none":
            self.crop_margins = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        self._update_transform_buttons()
        self.refresh_current_frame()
        if getattr(self, '_crop_dialog', None) and self._crop_dialog.winfo_exists():
            self._crop_dialog._update_ui_state()

    def reset_transform(self):
        self.flip_horizontal = False
        self.flip_vertical = False
        self.crop_mode = "none"
        self.crop_margins = {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
        self._update_transform_buttons()
        self.refresh_current_frame()
        if getattr(self, '_crop_dialog', None) and self._crop_dialog.winfo_exists():
            self._crop_dialog._update_ui_state()

    def _update_transform_buttons(self):
        if hasattr(self, 'btn_crop'):
            is_cropped = (self.crop_mode != "none") or any(self.crop_margins.get(k, 0.0) > 0.01 for k in ['top', 'bottom', 'left', 'right'])
            self.btn_crop.configure(
                fg_color="#7C3AED" if is_cropped else "#1E293B",
                hover_color="#6D28D9" if is_cropped else "#334155"
            )

    def _open_crop_dialog(self):
        if getattr(self, '_crop_dialog', None) and self._crop_dialog.winfo_exists():
            self._crop_dialog.lift()
            self._crop_dialog.focus_force()
            return
        self._crop_dialog = VideoCropDialog(self.winfo_toplevel(), self)

    def set_subtitles(self, subs):
        """Loads or updates active subtitle dialogue segments into player."""
        self.cc_subtitles = subs if subs else []
        self.refresh_current_frame()

    def _on_player_responsive_configure(self, event):
        if event.widget != self:
            return
        w = event.width
        if getattr(self, '_last_responsive_w', 0) == w or w < 20:
            return
        self._last_responsive_w = w
        self._adapt_player_header(w)
        self._adapt_player_seek(w)

    def _adapt_player_header(self, w: int):
        tr = UI_STRINGS.get(getattr(self, 'current_lang', 'km'), UI_STRINGS["km"])
        if w >= 560:
            if hasattr(self, 'hdr_title'):
                if not self.hdr_title.winfo_ismapped():
                    self.hdr_title.pack(side="left", before=self.zoom_box)
                self.hdr_title.configure(text=tr.get("player_title", "🎥 ផ្ទាំងចាក់វីដេអូ (Video Player)"), font=ctk.CTkFont(size=12, weight="bold"))
            self.btn_zoom_fit.configure(text="Fit", width=34)
            self.btn_zoom_fill.configure(text="Fill", width=38)
            self.size_dropdown.configure(width=84)
            if hasattr(self, 'btn_crop'):
                self.btn_crop.configure(text="✂️ Crop", width=52)
            if hasattr(self, 'status_badge') and not self.status_badge.winfo_ismapped():
                self.status_badge.pack(side="right")
        elif w >= 430:
            if hasattr(self, 'hdr_title'):
                if not self.hdr_title.winfo_ismapped():
                    self.hdr_title.pack(side="left", before=self.zoom_box)
                self.hdr_title.configure(text="🎥 វីដេអូ", font=ctk.CTkFont(size=11, weight="bold"))
            self.btn_zoom_fit.configure(text="Fit", width=28)
            self.btn_zoom_fill.configure(text="Fill", width=30)
            self.size_dropdown.configure(width=76)
            if hasattr(self, 'btn_crop'):
                self.btn_crop.configure(text="✂️", width=28)
            if hasattr(self, 'status_badge') and not self.status_badge.winfo_ismapped():
                self.status_badge.pack(side="right")
        elif w >= 320:
            if hasattr(self, 'hdr_title'):
                if not self.hdr_title.winfo_ismapped():
                    self.hdr_title.pack(side="left", before=self.zoom_box)
                self.hdr_title.configure(text="🎥", font=ctk.CTkFont(size=11, weight="bold"))
            self.btn_zoom_fit.configure(text="F", width=22)
            self.btn_zoom_fill.configure(text="Fl", width=24)
            self.size_dropdown.configure(width=62)
            if hasattr(self, 'btn_crop'):
                self.btn_crop.configure(text="✂️", width=24)
            if hasattr(self, 'status_badge') and self.status_badge.winfo_ismapped():
                self.status_badge.pack_forget()
        else:
            if hasattr(self, 'hdr_title') and self.hdr_title.winfo_ismapped():
                self.hdr_title.pack_forget()
            self.btn_zoom_fit.configure(text="F", width=20)
            self.btn_zoom_fill.configure(text="Fl", width=22)
            self.size_dropdown.configure(width=48)
            if hasattr(self, 'btn_crop'):
                self.btn_crop.configure(text="✂️", width=24)
            if hasattr(self, 'status_badge') and self.status_badge.winfo_ismapped():
                self.status_badge.pack_forget()

    def _adapt_player_seek(self, w: int):
        is_kh = (getattr(self, 'active_audio_mode', 'orig') == "khmer")
        if w >= 510:
            vals = ["🌐 ភាសាដើម (Original)", "🇰🇭 ភាសាខ្មែរ (Khmer Dub)"]
            self.audio_track_dropdown.configure(
                values=vals,
                width=160,
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold")
            )
            self.audio_track_dropdown.set(vals[1] if is_kh else vals[0])
            self.time_label.configure(font=ctk.CTkFont(size=11, family="Consolas", weight="bold"), width=80)
        elif w >= 380:
            vals = ["🌐 ដើម (Orig)", "🇰🇭 ខ្មែរ (Dub)"]
            self.audio_track_dropdown.configure(
                values=vals,
                width=110,
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9, weight="bold")
            )
            self.audio_track_dropdown.set(vals[1] if is_kh else vals[0])
            self.time_label.configure(font=ctk.CTkFont(size=10, family="Consolas", weight="bold"), width=68)
        elif w >= 290:
            vals = ["🌐 ដើម", "🇰🇭 ខ្មែរ"]
            self.audio_track_dropdown.configure(
                values=vals,
                width=80,
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9, weight="bold")
            )
            self.audio_track_dropdown.set(vals[1] if is_kh else vals[0])
            self.time_label.configure(font=ctk.CTkFont(size=9, family="Consolas", weight="bold"), width=58)
        else:
            vals = ["🌐", "🇰🇭"]
            self.audio_track_dropdown.configure(
                values=vals,
                width=46,
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9, weight="bold")
            )
            self.audio_track_dropdown.set(vals[1] if is_kh else vals[0])
            self.time_label.configure(font=ctk.CTkFont(size=8, family="Consolas", weight="bold"), width=46)

    def apply_language(self, lang="km"):
        self.current_lang = lang
        tr = UI_STRINGS.get(lang, UI_STRINGS["km"])
        if hasattr(self, 'hdr_title'):
            self.hdr_title.configure(text=tr["player_title"])
        if hasattr(self, 'size_dropdown'):
            opts = [tr["size_small"], tr["size_med"], tr["size_large"]]
            cur = self.size_dropdown.get()
            self.size_dropdown.configure(values=opts)
            if any(k in cur for k in ["តូច", "Small", "小"]):
                self.size_dropdown.set(opts[0])
            elif any(k in cur for k in ["ធំ", "Large", "大"]):
                self.size_dropdown.set(opts[2])
            else:
                self.size_dropdown.set(opts[1])
        if hasattr(self, 'audio_track_dropdown'):
            opts = [tr["track_orig"], tr["track_khmer"]]
            self.audio_track_dropdown.configure(values=opts)
            if self.active_audio_mode == "khmer":
                self.audio_track_dropdown.set(tr["track_khmer"])
            else:
                self.audio_track_dropdown.set(tr["track_orig"])
        if hasattr(self, 'status_badge') and not self.is_playing:
            self.status_badge.configure(text=tr["status_not_playing"])
        if self.winfo_width() > 30:
            self._adapt_player_header(self.winfo_width())
            self._adapt_player_seek(self.winfo_width())

    def _on_size_preset_selected(self, choice: str):
        """Handle video size preset selection from dropdown."""
        if any(k in choice for k in ["តូច", "Small", "小"]):
            self.set_display_size(360, 220)
        elif any(k in choice for k in ["ធំ", "Large", "大"]):
            self.set_display_size(620, 380)
        else:
            self.set_display_size(480, 280)

    def set_display_size(self, w: int, h: int):
        self._display_w = w
        self._display_h = h
        self.screen_frame.configure(width=w, height=h)
        if hasattr(self, 'size_dropdown'):
            opts = self.size_dropdown._values
            if w <= 380 and len(opts) >= 1:
                self.size_dropdown.set(opts[0])
            elif w >= 600 and len(opts) >= 3:
                self.size_dropdown.set(opts[2])
            elif len(opts) >= 2:
                self.size_dropdown.set(opts[1])
        if hasattr(self, 'on_size_change') and callable(self.on_size_change):
            try:
                self.on_size_change(w, h)
            except Exception:
                pass
        self._show_frame_at_sec(self.current_time_sec)

    def _on_audio_track_selected(self, choice: str):
        """Handle audio track selection from OptionMenu dropdown."""
        if any(k in choice for k in ["ខ្មែរ", "Khmer", "柬"]):
            self.switch_audio_mode("khmer")
        else:
            self.switch_audio_mode("orig")

    def switch_audio_mode(self, mode: str):
        if mode == "khmer":
            if not self.khmer_audio_path or not os.path.exists(self.khmer_audio_path):
                # Try fallback callback
                if hasattr(self, 'get_khmer_audio_cb') and callable(self.get_khmer_audio_cb):
                    candidate = self.get_khmer_audio_cb()
                    if candidate and os.path.exists(candidate):
                        self.khmer_audio_path = candidate
                        
            if not self.khmer_audio_path or not os.path.exists(self.khmer_audio_path):
                # Reset dropdown to orig since Khmer audio is not yet generated
                if hasattr(self, 'audio_track_dropdown'):
                    for v in self.audio_track_dropdown._values:
                        if any(k in v for k in ["ដើម", "Original", "原"]):
                            self.audio_track_dropdown.set(v)
                            break
                if hasattr(self, 'on_request_generate_voice') and callable(self.on_request_generate_voice):
                    res = messagebox.askyesno(
                        "ស្ដាប់សំឡេងខ្មែរ",
                        "⚠️ មិនទាន់មានសំឡេងភាសាខ្មែរនៅឡើយទេ!\n\nតើអ្នកចង់ចាប់ផ្តើមបង្កើតសំឡេងខ្មែរឥឡូវនេះដែរឬទេ?\n(ចុច Yes ដើម្បីបង្កើតសំឡេងខ្មែរ និងចាក់ស្ដាប់ភ្លាមៗ)"
                    )
                    if res:
                        self.on_request_generate_voice()
                    return
                else:
                    messagebox.showinfo(
                        "ដំណឹងពីសំឡេងខ្មែរ",
                        "⚠️ មិនទាន់មានសំឡេងភាសាខ្មែរនៅឡើយទេ!\n\nសូមចុចប៊ូតុង '⚡ ចាប់ផ្តើមបកប្រែ & បញ្ចូលសំឡេង' ជាមុនសិន។"
                    )
                    return
            
            self.active_audio_mode = "khmer"
            if hasattr(self, 'audio_track_dropdown'):
                for v in self.audio_track_dropdown._values:
                    if any(k in v for k in ["ខ្មែរ", "Khmer", "柬"]):
                        self.audio_track_dropdown.set(v)
                        break
            self.status_badge.configure(text="🇰🇭 សំឡេងខ្មែរ", text_color="#10B981")
            self._open_mci_audio(self.khmer_audio_path)
        else:
            self.active_audio_mode = "orig"
            if hasattr(self, 'audio_track_dropdown'):
                for v in self.audio_track_dropdown._values:
                    if any(k in v for k in ["ដើម", "Original", "原"]):
                        self.audio_track_dropdown.set(v)
                        break
            self.status_badge.configure(text="🌐 សំឡេងដើម", text_color="#60A5FA")
            if self.orig_audio_path and os.path.exists(self.orig_audio_path):
                self._open_mci_audio(self.orig_audio_path)
                
        if hasattr(self, 'on_audio_mode_change') and callable(self.on_audio_mode_change):
            try:
                self.on_audio_mode_change(self.active_audio_mode)
            except Exception:
                pass

    def set_khmer_audio(self, audio_path: str):
        """Called when Khmer dubbed voice track is ready."""
        if not audio_path or not os.path.exists(audio_path):
            return
        if audio_path.lower().endswith(".wav"):
            self.khmer_audio_path = audio_path
            self.switch_audio_mode("khmer")
        else:
            def _convert():
                temp_wav = os.path.join(tempfile.gettempdir(), f"kh_dub_{int(time.time()*1000)}.wav")
                cmd = [
                    FFMPEG_EXE, "-y",
                    "-i", audio_path,
                    "-vn", "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
                    temp_wav
                ]
                proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)
                if proc.returncode == 0 and os.path.exists(temp_wav):
                    self.khmer_audio_path = temp_wav
                    self.after(0, lambda: self.switch_audio_mode("khmer"))
            threading.Thread(target=_convert, daemon=True).start()

    def _close_mci(self):
        try:
            winmm = ctypes.windll.winmm
            winmm.mciSendStringW(f"stop {self._mci_alias}", None, 0, 0)
            winmm.mciSendStringW(f"close {self._mci_alias}", None, 0, 0)
        except Exception:
            pass
        self._has_audio = False

    def _open_mci_audio(self, audio_path: str):
        """Must be executed on the Main GUI Thread so MCI device is bound to this thread."""
        if not audio_path or not os.path.exists(audio_path):
            return
        self._close_mci()
        self.audio_path = audio_path
        short_p = get_short_path(audio_path)
        dev_type = "type waveaudio" if audio_path.lower().endswith(".wav") else "type mpegvideo"
        winmm = ctypes.windll.winmm
        self._mci_alias = f"emb_vplayer_{int(time.time()*1000) % 1000000}"
        r = winmm.mciSendStringW(f'open "{short_p}" {dev_type} alias {self._mci_alias}', None, 0, 0)
        if r != 0:
            r = winmm.mciSendStringW(f'open "{short_p}" alias {self._mci_alias}', None, 0, 0)
        if r == 0:
            self._has_audio = True
            winmm.mciSendStringW(f"set {self._mci_alias} time format milliseconds", None, 0, 0)
            winmm.mciSendStringW(f"setaudio {self._mci_alias} volume to 1000", None, 0, 0)
            if self.is_playing and not self.is_paused:
                pos_ms = int(self.current_time_sec * 1000)
                winmm.mciSendStringW(f"play {self._mci_alias} from {pos_ms}", None, 0, 0)
        else:
            err_buf = ctypes.create_unicode_buffer(256)
            winmm.mciGetErrorStringW(r, err_buf, 256)
            print(f"[Player] MCI open error ({r}): {err_buf.value}")

    def _check_audio_ready(self):
        """Polls on main GUI thread until background audio extraction completes."""
        if hasattr(self, '_audio_extracted_wav') and self._audio_extracted_wav:
            wav_path = self._audio_extracted_wav
            self._audio_extracted_wav = None
            self.orig_audio_path = wav_path
            if self.active_audio_mode == "orig":
                self._open_mci_audio(wav_path)
            return
        if getattr(self, '_is_extracting_audio', False):
            self.after(60, self._check_audio_ready)

    def load_audio(self, audio_path: str):
        """Allows loading or replacing the audio track (e.g. Master Dubbed Audio)."""
        self.set_khmer_audio(audio_path)

    def unload_video(self):
        """Completely unload and clear the currently loaded video."""
        self.stop()
        self._close_mci()
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        self.video_path = ""
        self.audio_path = ""
        self.orig_audio_path = ""
        self.khmer_audio_path = ""
        self.active_audio_mode = "orig"
        self._last_frame = None
        self.total_frames = 0
        self.total_duration_sec = 0.0
        self.current_time_sec = 0.0

        # Reset zoom and pan
        self.zoom_factor = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self._update_zoom_label()

        # Reset transforms (flip & crop)
        self.reset_transform()

        # Reset slider & time label
        self.seek_slider.configure(from_=0.0, to=100.0)
        self.seek_slider.set(0.0)
        self.time_label.configure(text="00:00 / 00:00")

        # Reset canvas: hide video image and show placeholder text
        if hasattr(self, '_video_img_id'):
            self.screen_canvas.itemconfigure(self._video_img_id, state="hidden")
        if hasattr(self, '_placeholder_text_id'):
            tr = UI_STRINGS.get(getattr(self, 'current_lang', 'km'), UI_STRINGS["km"])
            self.screen_canvas.itemconfigure(
                self._placeholder_text_id,
                text=tr.get("screen_prompt", "🎬 សូមជ្រើសរើសវីដេអូដើម្បីបង្ហាញនៅទីនេះ\n(Select Video File)"),
                state="normal"
            )
        if hasattr(self, '_sub_bg_id'):
            self.screen_canvas.itemconfigure(self._sub_bg_id, state="hidden")
        if hasattr(self, '_sub_text_id'):
            self.screen_canvas.itemconfigure(self._sub_text_id, state="hidden")
        self.screen_canvas.image = None

        # Reset status badge
        if hasattr(self, 'status_badge'):
            self.status_badge.configure(text="⏹️ មិនទាន់ចាក់", text_color="#9CA3AF")

    def load_video(self, video_path: str, keep_khmer_audio: bool = False):
        if not video_path or not os.path.exists(video_path):
            return
        
        self.stop()
        self._close_mci()
        
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            
        self.video_path = video_path
        sp = get_short_path(video_path)
        self.cap = cv2.VideoCapture(sp)
        if not self.cap.isOpened():
            self.screen_label.configure(image=None, text="❌ មិនអាចបើកវីដេអូបានទេ")
            return
            
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        if self.fps <= 0 or self.fps > 120:
            self.fps = 25.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.total_duration_sec = self.total_frames / self.fps if self.fps > 0 else 0.0
        self.current_time_sec = 0.0
        
        self.seek_slider.configure(from_=0.0, to=max(1.0, self.total_duration_sec))
        self.seek_slider.set(0.0)
        self.time_label.configure(text=f"00:00 / {format_time(self.total_duration_sec)}")
        
        if not keep_khmer_audio:
            self.active_audio_mode = "orig"
            self.orig_audio_path = ""
            self.khmer_audio_path = ""
            if hasattr(self, 'audio_track_dropdown'):
                for v in self.audio_track_dropdown._values:
                    if any(k in v for k in ["ដើម", "Original", "原"]):
                        self.audio_track_dropdown.set(v)
                        break
        
        # Reset zoom and pan for freshly loaded video
        self.zoom_factor = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self._update_zoom_label()

        # Display first frame
        self._show_frame_at_sec(0.0)
        
        # Extract audio safely without calling Tkinter methods from thread
        self._is_extracting_audio = True
        self._audio_extracted_wav = None
        def _prep_audio():
            try:
                temp_wav = os.path.join(tempfile.gettempdir(), f"vplay_aud_{int(time.time()*1000)}.wav")
                cmd = [
                    FFMPEG_EXE, "-y",
                    "-i", self.video_path,
                    "-vn", "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
                    temp_wav
                ]
                proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)
                if proc.returncode == 0 and os.path.exists(temp_wav) and os.path.getsize(temp_wav) > 1000:
                    self._audio_extracted_wav = temp_wav
                else:
                    print(f"[Player] Audio extraction yielded no sound or failed (returncode: {proc.returncode})")
            except Exception as e:
                print(f"[Warning] Player audio prep error: {e}")
            finally:
                self._is_extracting_audio = False
                
        threading.Thread(target=_prep_audio, daemon=True).start()
        self.after(50, self._check_audio_ready)

    def _show_frame_at_sec(self, sec: float):
        if not self.cap or not self.cap.isOpened():
            return
        try:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000.0)
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self._render_frame_to_screen(frame)
        except Exception:
            pass

    def play(self):
        if not self.video_path or not self.cap:
            return
        if self.is_playing and not self.is_paused:
            return
            
        self.is_playing = True
        self.is_paused = False
        self._start_wall_time = time.time()
        self._start_pos_sec = self.current_time_sec
        self.status_badge.configure(text="▶️ កំពុងចាក់", text_color="#10B981")
        if hasattr(self, 'mini_play_btn'):
            self.mini_play_btn.configure(text="⏸", fg_color="#D97706", hover_color="#B45309")
        if hasattr(self, 'on_play_state_change') and callable(self.on_play_state_change):
            self.on_play_state_change(True)
        
        # Ensure active audio track is opened in MCI
        target_audio = self.khmer_audio_path if self.active_audio_mode == "khmer" else self.orig_audio_path
        if target_audio and os.path.exists(target_audio):
            if not self._has_audio or self.audio_path != target_audio:
                self._open_mci_audio(target_audio)
                
        if self._has_audio:
            try:
                pos_ms = int(self.current_time_sec * 1000)
                winmm = ctypes.windll.winmm
                r = winmm.mciSendStringW(f"play {self._mci_alias} from {pos_ms}", None, 0, 0)
                if r != 0 and self.audio_path and os.path.exists(self.audio_path):
                    self._open_mci_audio(self.audio_path)
            except Exception as e:
                print(f"[Player] Play error: {e}")
                
        self._cancel_timer()
        self._tick()

    def pause(self):
        if not self.is_playing:
            return
        self.is_paused = True
        self.is_playing = False
        self._cancel_timer()
        self.status_badge.configure(text="⏸️ ផ្អាក", text_color="#F59E0B")
        if hasattr(self, 'mini_play_btn'):
            self.mini_play_btn.configure(text="▶", fg_color="#059669", hover_color="#047857")
        if hasattr(self, 'on_play_state_change') and callable(self.on_play_state_change):
            self.on_play_state_change(False)
        if self._has_audio:
            try:
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(f"pause {self._mci_alias}", None, 0, 0)
            except Exception:
                pass

    def stop(self):
        self._cancel_timer()
        self.is_playing = False
        self.is_paused = False
        self.current_time_sec = 0.0
        self.status_badge.configure(text="⏹️ ឈប់", text_color="#9CA3AF")
        if hasattr(self, 'mini_play_btn'):
            self.mini_play_btn.configure(text="▶", fg_color="#059669", hover_color="#047857")
        if hasattr(self, 'on_play_state_change') and callable(self.on_play_state_change):
            self.on_play_state_change(False)
        if self._has_audio:
            try:
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(f"stop {self._mci_alias}", None, 0, 0)
            except Exception:
                pass
        self.seek_slider.set(0.0)
        self.time_label.configure(text=f"00:00 / {format_time(self.total_duration_sec)}")
        self._show_frame_at_sec(0.0)
        if self.on_time_update:
            self.on_time_update(0.0)

    def rewind(self):
        self.seek(0.0)
        if self.is_playing:
            self.play()

    def toggle_play(self):
        """Toggle playback between Play and Pause."""
        if self.is_playing and not self.is_paused:
            self.pause()
        else:
            self.play()

    def step_backward(self, seconds: float = 1.0):
        """Seek backward by specified seconds."""
        new_time = max(0.0, self.current_time_sec - seconds)
        self.seek(new_time)
        if hasattr(self, 'on_time_update') and callable(self.on_time_update):
            self.on_time_update(new_time)

    def step_forward(self, seconds: float = 1.0):
        """Seek forward by specified seconds."""
        new_time = min(self.total_duration_sec, self.current_time_sec + seconds)
        self.seek(new_time)
        if hasattr(self, 'on_time_update') and callable(self.on_time_update):
            self.on_time_update(new_time)

    def seek(self, sec: float):
        sec = max(0.0, min(self.total_duration_sec, sec))
        self.current_time_sec = sec
        self._start_wall_time = time.time()
        self._start_pos_sec = sec
        
        target_audio = self.khmer_audio_path if self.active_audio_mode == "khmer" else self.orig_audio_path
        if target_audio and os.path.exists(target_audio):
            if not self._has_audio or self.audio_path != target_audio:
                self._open_mci_audio(target_audio)
                
        if self._has_audio:
            try:
                pos_ms = int(sec * 1000)
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(f"seek {self._mci_alias} to {pos_ms}", None, 0, 0)
                if self.is_playing:
                    winmm.mciSendStringW(f"play {self._mci_alias} from {pos_ms}", None, 0, 0)
            except Exception:
                pass
                
        self.seek_slider.set(sec)
        self.time_label.configure(text=f"{format_time(sec)} / {format_time(self.total_duration_sec)}")
        self._show_frame_at_sec(sec)
        if self.on_time_update:
            self.on_time_update(sec)

    def _on_slider_change(self, val):
        self._is_seeking = True
        self.time_label.configure(text=f"{format_time(val)} / {format_time(self.total_duration_sec)}")

    def _on_slider_release(self, event):
        val = self.seek_slider.get()
        self._is_seeking = False
        self.seek(val)

    def _cancel_timer(self):
        if self._timer_id:
            try:
                self.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None

    def _tick(self):
        if not self.is_playing:
            return
            
        cur = time.time() - self._start_wall_time + self._start_pos_sec
        if self._has_audio:
            try:
                buf = ctypes.create_unicode_buffer(128)
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(f"status {self._mci_alias} position", buf, 128, 0)
                if buf.value and buf.value.isdigit():
                    cur = int(buf.value) / 1000.0
            except Exception:
                pass
                
        if cur >= self.total_duration_sec and self.total_duration_sec > 0:
            self.stop()
            return
            
        self.current_time_sec = cur
        if not self._is_seeking:
            self.seek_slider.set(cur)
            self.time_label.configure(text=f"{format_time(cur)} / {format_time(self.total_duration_sec)}")
            
        self._show_frame_at_sec(cur)
        
        if self.on_time_update:
            self.on_time_update(cur)
            
        delay = int(1000 / max(10, min(60, self.fps)))
        self._timer_id = self.after(delay, self._tick)

    def destroy(self):
        self._cancel_timer()
        self._close_mci()
        self._last_frame = None
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        super().destroy()

# ---------------------------------------------------------
# Khmer Font & Multi-Language System Configuration
# ---------------------------------------------------------
def get_khmer_ui_font_name():
    pref = [
        'Kantumruy Pro',
        'Kantumruy',
        'Noto Sans Khmer',
        'Khmer OS Battambang',
        'Battambang',
        'Leelawadee UI',
        'Segoe UI'
    ]
    try:
        import tkinter.font as tkfont
        avail = tkfont.families()
        for f in pref:
            if f in avail:
                return f
    except Exception:
        pass
    return "Kantumruy"

KHMER_FONT_NAME = "Kantumruy"

def get_khmer_ui_font(size=12, weight="normal"):
    return ctk.CTkFont(family=KHMER_FONT_NAME, size=size, weight=weight)


APP_LANG_FILE = os.path.join(APP_DIR, "app_lang.txt")

def get_saved_language() -> str:
    try:
        if os.path.exists(APP_LANG_FILE):
            with open(APP_LANG_FILE, "r", encoding="utf-8") as f:
                c = f.read().strip()
                if c in ("km", "en", "zh"):
                    return c
    except Exception:
        pass
    return "km"

def save_language(lang: str):
    try:
        with open(APP_LANG_FILE, "w", encoding="utf-8") as f:
            f.write(lang)
    except Exception:
        pass

def attach_context_menu(widget, get_lang_func):
    """Attaches standard Right-Click Context Menu (Cut, Copy, Paste, Select All)"""
    def show_menu(e):
        lang = get_lang_func() if callable(get_lang_func) else "km"
        menu = tk.Menu(widget, tearoff=0, bg="#1E293B", fg="#F8FAFC", activebackground="#2563EB", activeforeground="#FFFFFF")
        
        labels = {
            "km": {"cut": "✂️ កាត់ (Cut)", "copy": "📋 ចម្លង (Copy)", "paste": "📌 បិទភ្ជាប់ (Paste)", "sel": "🔘 ជ្រើសទាំងអស់ (Select All)"},
            "en": {"cut": "✂️ Cut", "copy": "📋 Copy", "paste": "📌 Paste", "sel": "🔘 Select All"},
            "zh": {"cut": "✂️ 剪切 (Cut)", "copy": "📋 复制 (Copy)", "paste": "📌 粘贴 (Paste)", "sel": "🔘 全选 (Select All)"}
        }
        l = labels.get(lang, labels["km"])
        target = widget._entry if hasattr(widget, '_entry') else widget
        menu.add_command(label=l["cut"], command=lambda: target.event_generate("<<Cut>>"))
        menu.add_command(label=l["copy"], command=lambda: target.event_generate("<<Copy>>"))
        menu.add_command(label=l["paste"], command=lambda: target.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label=l["sel"], command=lambda: (target.select_range(0, 'end'), target.icursor('end')))
        menu.tk_popup(e.x_root, e.y_root)
        
    target = widget._entry if hasattr(widget, '_entry') else widget
    target.bind("<Button-3>", show_menu)

UI_STRINGS = {
    "km": {
        "header_sub": "កម្មវិធីសម្រាយរឿង និងបកប្រែបញ្ចូលសំឡេងស្វ័យប្រវត្តិជាភាសាខ្មែរ (Auto Subtitles • Translation • TTS • Video Mixing)",
        "lang_label": "🌐 ភាសា:",
        "gemini_title": "✨ Gemini 2.5 Flash សម្រាយរឿង",
        "gemini_key_lbl": "🔑 Key:",
        "gemini_key_placeholder": "Gemini API Key...",
        "save_btn": "💾 រក្សាទុក",
        "video_placeholder": "សូមជ្រើសរើសវីដេអូដើម... (Select Video File)",
        "browse_video_btn": "📁 ជ្រើសរើសវីដេអូ",
        "remove_video_btn": "❌ ដកវីដេអូចេញ",
        "eject_video_btn": "⏏️ ដកវីដេអូ",
        "model_lbl": "🧠 Model:",
        "voice_lbl": "🎙️ សំឡេង:",
        "speed_lbl": "⚡ ល្បឿន:",
        "auto_cb": "⚡ Auto",
        "start_btn": "⚡ ចាប់ផ្តើមបកប្រែ & បញ្ចូលសំឡេង",
        "scan_translate_btn": "🔍 ១. ស្កែន & បកប្រែ",
        "dub_voice_btn": "🎙️ ២. បញ្ចូលសំឡេង",
        "export_btn": "📤 ៣. Export វីដេអូ",
        "export_dialog_title": "📤 Export វីដេអូច្របាច់សំឡេង (Export Video)",
        "export_heading": "📤 ការកំណត់ Export វីដេអូ (Video Export Studio)",
        "export_quality_lbl": "📐 កម្រិតគុណភាពវីដេអូ (Resolution / Quality)៖",
        "export_quality_hint": "💡 គុណភាពត្រូវបានកំណត់ត្រឹមកម្រិតវីដេអូដើម ({res}p) ចុះក្រោម",
        "export_preset_lbl": "⚡ គុណភាព Encoding (Preset)៖",
        "export_sub_mode_lbl": "💬 ជម្រើសអក្សរ Subtitle៖",
        "export_sub_hard": "🔥 Hardcode Subtitle (ដុតអក្សរ Subtitle ជាប់លើវីដេអូ - ណែនាំ)",
        "export_sub_soft": "🔲 Soft Subtitle (ឯកសារ .ass ក្រៅវីដេអូ)",
        "export_sub_none": "🚫 មិនដាក់ Subtitle (No Subtitles)",
        "export_path_lbl": "📁 ទីតាំងរក្សាទុកឯកសារ (Output Path)៖",
        "export_browse_btn": "📁 ផ្លាស់ប្ដូរ...",
        "btn_start_export": "🚀 ចាប់ផ្តើម Export",
        "initial_status": "សូមជ្រើសរើសវីដេអូរួចចុច '🔍 ១. ស្កែន & បកប្រែ' ដើម្បីចាប់ផ្តើម",
        "player_title": "🎥 ផ្ទាំងចាក់វីដេអូ (Video Player)",
        "size_small": "📐 តូច",
        "size_med": "📐 មធ្យម",
        "size_large": "📐 ធំ",
        "status_not_playing": "⏹️ មិនទាន់ចាក់",
        "screen_prompt": "🎬 សូមជ្រើសរើសវីដេអូដើម្បីបង្ហាញនៅទីនេះ\n(Select Video File)",
        "audio_track_lbl": "🎧 ជ្រើសរើសសំឡេង៖",
        "track_orig": "🌐 ស្តាប់ភាសាដើម (Original)",
        "track_khmer": "🇰🇭 ស្តាប់ភាសាខ្មែរ (Khmer Dubbed)",
        "play_btn": "▶️ ស្តាប់ (Play)",
        "pause_btn": "⏸️ ផ្អាក",
        "stop_btn": "⏹️ ឈប់ (Stop)",
        "rewind_btn": "⏮️ ពីដើម",
        "sub_editor_title": "✏️ បញ្ជីអត្ថបទបកប្រែខ្មែរ (Subtitle Editor)៖",
        "find_replace_btn": "🔍 ផ្លាស់ប្ដូរពាក្យ",
        "retranslate_all_btn": "🔄 បកប្រែឡើងវិញទាំងអស់",
        "regen_video_btn": "🎬 បញ្ចូលសំឡេងឡើងវិញ",
        "bgm_lbl": "🔊 ភ្លេងដើម BGM:",
        "manage_bgm_btn": "✂️ រៀបចំកង់ BGM",
        "mute_orig_cb": "🔇 បិទសំឡេងនិយាយដើម ១០០% (ឮតែខ្មែរ + BGM)",
        "demucs_cb": "✨ AI Demucs (ស្រង់ភ្លេង BGM សុទ្ធ)",
        "result_preview_title": "📺 កន្លែងមើលវីដេអូ៖ វីដេអូច្របាច់រួចនឹងបង្ហាញនៅទីនេះដោយស្វ័យប្រវត្តិ",
        "result_path_placeholder": "ទីតាំងវីដេអូច្របាច់រួចនឹងបង្ហាញនៅទីនេះ...",
        "play_video_btn": "▶️ មើលវីដេអូ",
        "locate_video_btn": "📍 បើក Folder",
        "auto_gender_cb": "🎭 អូតូសំឡេងស្រី-ប្រុស",
        "voice_options": [
            "🎭 អូតូសំឡេងស្រី-ប្រុស (Auto Voice)",
            "👨 សំឡេងប្រុស (Piseth Neural)",
            "👩 សំឡេងស្រី (Sreymom Neural)"
        ],
        "speed_options": [
            "1.0x (ធម្មតា)",
            "1.05x (លឿនល្មម)",
            "1.1x (លឿន)",
            "1.15x (លឿនខ្លាំង)",
            "0.95x (យឺតល្មម)"
        ],
        "segment_orig_prefix": " ដើម: ",
        "segment_retrans_btn": "🌐 បកប្រែឡើងវិញ",
        "segment_preview_btn": "🔊 ស្តាប់ល្បះនេះ",
        "segment_gender_male": "👨 សំឡេងប្រុស",
        "segment_gender_female": "👩 សំឡេងស្រី",
        "find_replace_dialog_title": "🔍 ស្វែងរក និងផ្លាស់ប្ដូរពាក្យក្នុងអត្ថបទ",
        "find_replace_heading": "ស្វែងរក និងផ្លាស់ប្ដូរពាក្យ (Find & Replace)",
        "find_label": "ពាក្យដែលត្រូវស្វែងរក៖",
        "replace_label": "ផ្លាស់ប្ដូរជំនួសដោយ៖",
        "btn_do_replace": "✅ ផ្លាស់ប្ដូរទាំងអស់",
        "btn_cancel": "❌ បោះបង់",
        "empty_find_warning": "សូមបញ្ចូលពាក្យដែលត្រូវស្វែងរក!",
        "replace_success": "បានផ្លាស់ប្ដូរពាក្យចំនួន {n} កន្លែងជោគជ័យ!",
        "no_segments_to_replace": "មិនទាន់មានអត្ថបទសម្រាយរឿងសម្រាប់ផ្លាស់ប្ដូរនៅឡើយទេ!",
        "notice_title": "ដំណឹង",
        "warning_title": "ការព្រមាន",
        "success_title": "ជោគជ័យ",
        "toggle_timeline_hide": "🎞️ បិទ Timeline",
        "toggle_timeline_show": "🎞️ បើក Timeline",
        "toggle_cc_bg_on": "🔲 ផ្ទៃខាងក្រោយ: បើក",
        "toggle_cc_bg_off": "🔲 ផ្ទៃខាងក្រោយ: បិទ",
        "toggle_cc_settings": "⚙️ កំណត់ Subtitle",
        "lbl_sub_sec": "💬 អក្សរ Subtitle:",
        "zoom_fit": "Fit",
        "zoom_fill": "Fill"
    },
    "en": {
        "header_sub": "AI Movie Dubbing & Video Translation Studio (Auto Subtitles • Translation • TTS • Video Mixing)",
        "lang_label": "🌐 Language:",
        "gemini_title": "✨ Gemini 2.5 Flash Narration",
        "gemini_key_lbl": "🔑 Key:",
        "gemini_key_placeholder": "Gemini API Key...",
        "save_btn": "💾 Save",
        "video_placeholder": "Please select source video... (Select Video File)",
        "browse_video_btn": "📁 Browse Video",
        "remove_video_btn": "❌ Remove Video",
        "eject_video_btn": "⏏️ Eject Video",
        "model_lbl": "🧠 Model:",
        "voice_lbl": "🎙️ Voice:",
        "speed_lbl": "⚡ Speed:",
        "auto_cb": "⚡ Auto",
        "start_btn": "⚡ Start Auto Dubbing & Merge",
        "scan_translate_btn": "🔍 1. Scan & Translate",
        "dub_voice_btn": "🎙️ 2. Generate Dubbing",
        "export_btn": "📤 3. Export Video",
        "export_dialog_title": "📤 Export Dubbed Video",
        "export_heading": "📤 Video Export Studio",
        "export_quality_lbl": "📐 Video Resolution / Quality:",
        "export_quality_hint": "💡 Quality is capped at source resolution ({res}p) and downwards",
        "export_preset_lbl": "⚡ Encoding Preset:",
        "export_sub_mode_lbl": "💬 Subtitle Export Mode:",
        "export_sub_hard": "🔥 Hardcode Subtitle (Burn-in text directly onto video - Recommended)",
        "export_sub_soft": "🔲 Soft Subtitle (.ass file alongside video)",
        "export_sub_none": "🚫 No Subtitles",
        "export_path_lbl": "📁 Destination File Path:",
        "export_browse_btn": "📁 Browse...",
        "btn_start_export": "🚀 Start Export",
        "initial_status": "Please select a video, then click '🔍 1. Scan & Translate' to begin",
        "player_title": "🎥 Video Player Preview",
        "size_small": "📐 Small",
        "size_med": "📐 Medium",
        "size_large": "📐 Large",
        "status_not_playing": "⏹️ Stopped",
        "screen_prompt": "🎬 Please select a video to preview here\n(Select Video File)",
        "audio_track_lbl": "🎧 Audio Track:",
        "track_orig": "🌐 Original Audio",
        "track_khmer": "🇰🇭 Khmer Dubbed Audio",
        "play_btn": "▶️ Play",
        "pause_btn": "⏸️ Pause",
        "stop_btn": "⏹️ Stop",
        "rewind_btn": "⏮️ Rewind",
        "sub_editor_title": "✏️ Subtitle & Dialogue Editor:",
        "find_replace_btn": "🔍 Find & Replace",
        "retranslate_all_btn": "🔄 Retranslate All",
        "regen_video_btn": "🎬 Re-Dub Video",
        "bgm_lbl": "🔊 Background Music (BGM):",
        "manage_bgm_btn": "✂️ Manage BGM Clips",
        "mute_orig_cb": "🔇 Mute 100% original speech (Khmer + BGM only)",
        "demucs_cb": "✨ AI Demucs (Isolate Pure BGM)",
        "result_preview_title": "📺 Export Preview: Merged video will appear here automatically",
        "result_path_placeholder": "Finished video path will appear here...",
        "play_video_btn": "▶️ Play Video",
        "locate_video_btn": "📍 Open Folder",
        "auto_gender_cb": "🎭 Auto Female/Male Voice",
        "voice_options": [
            "🎭 Auto Female/Male Voice (Auto Character)",
            "👨 Male Voice (Piseth Neural)",
            "👩 Female Voice (Sreymom Neural)"
        ],
        "speed_options": [
            "1.0x (Normal)",
            "1.05x (Slightly Fast)",
            "1.1x (Fast)",
            "1.15x (Very Fast)",
            "0.95x (Slightly Slow)"
        ],
        "segment_orig_prefix": " Orig: ",
        "segment_retrans_btn": "🌐 Retranslate",
        "segment_preview_btn": "🔊 Listen Line",
        "segment_gender_male": "👨 Male Voice",
        "segment_gender_female": "👩 Female Voice",
        "find_replace_dialog_title": "🔍 Find & Replace Subtitle Text",
        "find_replace_heading": "Find & Replace Text",
        "find_label": "Find word / text:",
        "replace_label": "Replace with:",
        "btn_do_replace": "✅ Replace All",
        "btn_cancel": "❌ Cancel",
        "empty_find_warning": "Please enter text to search!",
        "replace_success": "Successfully replaced text in {n} line(s)!",
        "no_segments_to_replace": "No subtitle lines available to replace yet!",
        "notice_title": "Notice",
        "warning_title": "Warning",
        "success_title": "Success",
        "toggle_timeline_hide": "🎞️ Hide Timeline",
        "toggle_timeline_show": "🎞️ Show Timeline",
        "toggle_cc_bg_on": "🔲 Background: ON",
        "toggle_cc_bg_off": "🔲 Background: OFF",
        "toggle_cc_settings": "⚙️ Subtitle Settings",
        "lbl_sub_sec": "💬 CC Subtitle:",
        "zoom_fit": "Fit",
        "zoom_fill": "Fill"
    },
    "zh": {
        "header_sub": "AI 影视解说与视频配音工作室 (自动字幕 • 翻译 • TTS 语音 • 视频混剪)",
        "lang_label": "🌐 语言:",
        "gemini_title": "✨ Gemini 2.5 Flash 影视解说",
        "gemini_key_lbl": "🔑 密钥:",
        "gemini_key_placeholder": "Gemini API Key 密钥...",
        "save_btn": "💾 保存",
        "video_placeholder": "请选择原视频文件... (Select Video File)",
        "browse_video_btn": "📁 选择视频",
        "remove_video_btn": "❌ 移除视频",
        "eject_video_btn": "⏏️ 移除视频",
        "model_lbl": "🧠 模型:",
        "voice_lbl": "🎙️ 声音:",
        "speed_lbl": "⚡ 语速:",
        "auto_cb": "⚡ 自动",
        "start_btn": "⚡ 开始全自动翻译与配音",
        "scan_translate_btn": "🔍 1. 识别并翻译",
        "dub_voice_btn": "🎙️ 2. 生成配音合成",
        "export_btn": "📤 3. 导出视频",
        "export_dialog_title": "📤 导出配音视频 (Export Video)",
        "export_heading": "📤 视频导出设置 (Video Export Studio)",
        "export_video_info": "🎬 原视频信息：",
        "export_quality_lbl": "📐 视频画质分辨率 (Resolution / Quality)：",
        "export_quality_hint": "💡 导出画质已根据原视频最高分辨率 ({res}p) 及以下自适应限制",
        "export_preset_lbl": "⚡ 编码质量预设 (Preset)：",
        "export_sub_mode_lbl": "💬 字幕导出方式：",
        "export_sub_hard": "🔥 压制硬字幕 (将字幕直接压制烧录在视频画面上 - 推荐)",
        "export_sub_soft": "🔲 外挂软字幕 (生成同名 .ass 字幕文件)",
        "export_sub_none": "🚫 不添加字幕 (无字幕)",
        "export_path_lbl": "📁 导出文件路径：",
        "export_browse_btn": "📁 浏览...",
        "btn_start_export": "🚀 开始导出",
        "initial_status": "请先选择视频，然后点击“🔍 1. 识别并翻译”以开始",
        "player_title": "🎥 视频播放器 (Video Player)",
        "size_small": "📐 小",
        "size_med": "📐 中",
        "size_large": "📐 大",
        "status_not_playing": "⏹️ 未播放",
        "screen_prompt": "🎬 请选择视频以在此预览播放\n(Select Video File)",
        "audio_track_lbl": "🎧 选择音频轨道：",
        "track_orig": "🌐 原声原音 (Original)",
        "track_khmer": "🇰🇭 柬语配音 (Khmer Dub)",
        "play_btn": "▶️ 播放 (Play)",
        "pause_btn": "⏸️ 暂停",
        "stop_btn": "⏹️ 停止 (Stop)",
        "rewind_btn": "⏮️ 片头",
        "sub_editor_title": "✏️ 译文字幕编辑列表 (Subtitle Editor)：",
        "find_replace_btn": "🔍 查找与替换",
        "retranslate_all_btn": "🔄 重新翻译全部",
        "regen_video_btn": "🎬 重新合成配音视频",
        "bgm_lbl": "🔊 背景音乐 (BGM)：",
        "manage_bgm_btn": "✂️ 管理背景音乐片段",
        "mute_orig_cb": "🔇 100% 静音原声语音 (仅保留配音 + BGM)",
        "demucs_cb": "✨ AI Demucs (提取纯背景音乐)",
        "result_preview_title": "📺 导出预览：合成完成的视频将自动显示在此处",
        "result_path_placeholder": "合成完成的视频路径将显示在此处...",
        "play_video_btn": "▶️ 播放视频",
        "locate_video_btn": "📍 打开文件夹",
        "auto_gender_cb": "🎭 自动男女角色配音",
        "voice_options": [
            "🎭 自动男女角色配音 (Auto Character)",
            "👨 男声 (Piseth Neural)",
            "👩 女声 (Sreymom Neural)"
        ],
        "speed_options": [
            "1.0x (正常)",
            "1.05x (稍快)",
            "1.1x (快速)",
            "1.15x (特快)",
            "0.95x (稍慢)"
        ],
        "segment_orig_prefix": " 原文: ",
        "segment_retrans_btn": "🌐 重新翻译",
        "segment_preview_btn": "🔊 试听本句",
        "segment_gender_male": "👨 男声",
        "segment_gender_female": "👩 女声",
        "find_replace_dialog_title": "🔍 查找并替换字幕文本",
        "find_replace_heading": "查找并替换文本 (Find & Replace)",
        "find_label": "要查找的文字：",
        "replace_label": "替换为新文字：",
        "btn_do_replace": "✅ 全部替换",
        "btn_cancel": "❌ 取消",
        "empty_find_warning": "请输入要查找的文字！",
        "replace_success": "已成功在 {n} 处字幕中完成替换！",
        "no_segments_to_replace": "目前暂无字幕内容可供替换！",
        "notice_title": "提示",
        "warning_title": "警告",
        "success_title": "成功",
        "toggle_timeline_hide": "🎞️ 隐藏时间轴",
        "toggle_timeline_show": "🎞️ 显示时间轴",
        "toggle_cc_bg_on": "🔲 背景框: 开启",
        "toggle_cc_bg_off": "🔲 背景框: 关闭",
        "toggle_cc_settings": "⚙️ 字幕设置",
        "lbl_sub_sec": "💬 CC 字幕:",
        "zoom_fit": "Fit",
        "zoom_fill": "Fill"
    }
}

# ---------------------------------------------------------
# Multi-Track Dubbing Timeline Component (Authentic Adobe Premiere Pro Style)
# ---------------------------------------------------------
def format_smpte(sec: float, fps: float = 25.0) -> str:
    """Format seconds into HH:MM:SS:FF (Adobe Premiere Pro Timecode format)."""
    total_frames = int(max(0.0, sec) * fps)
    ff = total_frames % int(fps)
    total_sec = int(sec)
    ss = total_sec % 60
    mm = (total_sec // 60) % 60
    hh = total_sec // 3600
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

class BGMVolumeDialog(ctk.CTkToplevel):
    """
    Dialog for adjusting volume and managing individual BGM segments.
    Allows user to set volume anywhere from 0% (mute) to 200% (boosted),
    split clips at playhead, and merge with neighboring clips.
    """
    def __init__(self, master_timeline, seg_idx: int = 0):
        super().__init__(master_timeline)
        self.timeline = master_timeline
        self.seg_idx = max(0, min(len(self.timeline.bgm_segments) - 1, seg_idx)) if self.timeline.bgm_segments else 0
        
        self.title("🎵 កែសម្រួលកម្រិតសំឡេងភ្លេង BGM (BGM Segment Volume)")
        self.geometry("520x490")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        
        self.update_idletasks()
        try:
            x = (self.winfo_screenwidth() - 520) // 2
            y = (self.winfo_screenheight() - 490) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
            
        self.configure(fg_color="#181824")
        self._build_ui()

    def _build_ui(self):
        # Header banner
        header = ctk.CTkFrame(self, fg_color="#241B35", corner_radius=0, height=54)
        header.pack(fill="x")
        header.pack_propagate(False)
        
        self.title_lbl = ctk.CTkLabel(
            header,
            text=f"🎵 កែសម្រួលកម្រិតសំឡេងកង់ BGM (កង់ទី #{self.seg_idx + 1})",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=14, weight="bold"),
            text_color="#F3E8FF"
        )
        self.title_lbl.pack(side="left", padx=16, pady=6)

        # Main container
        main_box = ctk.CTkFrame(self, fg_color="transparent")
        main_box.pack(fill="both", expand=True, padx=16, pady=10)

        # 1. Segment Time Interval Card
        seg = self.timeline.bgm_segments[self.seg_idx] if self.timeline.bgm_segments else {'start': 0.0, 'end': self.timeline.duration_sec, 'vol': 0.3}
        s_tc = format_smpte(seg['start'], self.timeline.fps)
        e_tc = format_smpte(seg['end'], self.timeline.fps)
        dur = round(seg['end'] - seg['start'], 2)
        
        self.time_lbl = ctk.CTkLabel(
            main_box,
            text=f"⏱️ ចន្លោះពេល៖ {s_tc} ➔ {e_tc}  (ប្រវែង៖ {dur} វិនាទី)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=12, weight="bold"),
            text_color="#C084FC"
        )
        self.time_lbl.pack(anchor="w", pady=(0, 8))

        # 2. Big Volume Readout Card
        card = ctk.CTkFrame(main_box, fg_color="#201733", corner_radius=8, border_color="#581C87", border_width=1)
        card.pack(fill="x", pady=(0, 10), ipady=6)

        self.vol_pct_lbl = ctk.CTkLabel(
            card,
            text="100%",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#FDE047"
        )
        self.vol_pct_lbl.pack(pady=(4, 2))

        self.vol_status_lbl = ctk.CTkLabel(
            card,
            text="🔊 សំឡេងកម្រិតដើមពេញ (100%)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#E9D5FF"
        )
        self.vol_status_lbl.pack(pady=(0, 6))

        # Slider: 0% to 200%
        self.slider = ctk.CTkSlider(
            card,
            from_=0.0,
            to=2.0,
            number_of_steps=40,
            width=440,
            command=self._on_slider_change,
            progress_color="#9333EA",
            button_color="#C084FC",
            button_hover_color="#E9D5FF"
        )
        self.slider.set(seg.get('vol', 0.3))
        self.slider.pack(pady=4)

        # 3. Quick Volume Presets
        pr_box = ctk.CTkFrame(main_box, fg_color="transparent")
        pr_box.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            pr_box,
            text="⚡ កម្រិតសំឡេងរហ័ស (Quick Presets)៖",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 4))

        p_row1 = ctk.CTkFrame(pr_box, fg_color="transparent")
        p_row1.pack(fill="x", pady=2)
        presets1 = [
            ("🔇 0% (បិទ)", 0.0, "#334155"),
            ("🔈 15% (តិច)", 0.15, "#4C1D95"),
            ("🔉 30% (ល្មម)", 0.30, "#581C87"),
            ("🔉 60% (មធ្យម)", 0.60, "#6B21A8"),
        ]
        for txt, val, col in presets1:
            ctk.CTkButton(
                p_row1, text=txt, width=105, height=26,
                fg_color=col, hover_color="#7E22CE",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
                command=lambda v=val: self._apply_preset(v)
            ).pack(side="left", padx=2, expand=True)

        p_row2 = ctk.CTkFrame(pr_box, fg_color="transparent")
        p_row2.pack(fill="x", pady=2)
        presets2 = [
            ("🔊 100% (ពេញ)", 1.00, "#7E22CE"),
            ("🔊 150% (ខ្លាំង)", 1.50, "#9333EA"),
            ("🔊 200% (ខ្លាំងបំផុត)", 2.00, "#C026D3"),
        ]
        for txt, val, col in presets2:
            ctk.CTkButton(
                p_row2, text=txt, width=140, height=26,
                fg_color=col, hover_color="#A855F7",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
                command=lambda v=val: self._apply_preset(v)
            ).pack(side="left", padx=3, expand=True)

        # 4. Cutting & Merging Actions
        tool_box = ctk.CTkFrame(main_box, fg_color="#1F1E2E", corner_radius=6)
        tool_box.pack(fill="x", pady=(0, 8), padx=0, ipady=4)

        t_row = ctk.CTkFrame(tool_box, fg_color="transparent")
        t_row.pack(fill="x", padx=6, pady=4)

        self.btn_split_here = ctk.CTkButton(
            t_row,
            text=f"✂️ កាត់ត្រង់ Playhead ({format_smpte(self.timeline.current_time_sec, self.timeline.fps)})",
            height=28,
            fg_color="#3B1C54",
            hover_color="#581C87",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._split_at_playhead
        )
        self.btn_split_here.pack(side="left", padx=4, expand=True, fill="x")

        self.btn_merge_next = ctk.CTkButton(
            t_row,
            text="🗑️ បញ្ចូលជាមួយកង់បន្ទាប់ (Merge)",
            height=28,
            fg_color="#374151",
            hover_color="#4B5563",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            command=self._merge_with_next
        )
        self.btn_merge_next.pack(side="left", padx=4, expand=True, fill="x")

        # 5. Bottom Action Buttons
        b_box = ctk.CTkFrame(self, fg_color="transparent")
        b_box.pack(fill="x", side="bottom", padx=16, pady=(0, 10))

        ctk.CTkButton(
            b_box,
            text="✅ រួចរាល់ (Apply & Close)",
            height=30,
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self.destroy
        ).pack(side="right")

        ctk.CTkButton(
            b_box,
            text="🔄 កំណត់ឡើងវិញទាំងអស់ (Reset)",
            height=30,
            fg_color="#475569",
            hover_color="#64748B",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            command=self._reset_all
        ).pack(side="left")

        self._update_readout(seg.get('vol', 0.3))

    def _on_slider_change(self, val):
        self.timeline.set_bgm_segment_volume(self.seg_idx, val)
        self._update_readout(val)

    def _apply_preset(self, val):
        self.slider.set(val)
        self._on_slider_change(val)

    def _update_readout(self, val):
        pct = int(round(val * 100))
        self.vol_pct_lbl.configure(text=f"{pct}%")
        if pct == 0:
            self.vol_pct_lbl.configure(text_color="#9CA3AF")
            self.vol_status_lbl.configure(text="🔇 បិទសំឡេងទាំងស្រុង (0% Digital Silence / Mute)", text_color="#9CA3AF")
        elif pct >= 100:
            self.vol_pct_lbl.configure(text_color="#FDE047")
            self.vol_status_lbl.configure(text=f"🔊 សំឡេងឮខ្លាំងច្បាស់ ({pct}% Boosted Audio)", text_color="#FDE047")
        elif pct <= 20:
            self.vol_pct_lbl.configure(text_color="#A78BFA")
            self.vol_status_lbl.configure(text=f"🔈 សំឡេងឮតិច / Ducked ({pct}% Ambient Background)", text_color="#A78BFA")
        else:
            self.vol_pct_lbl.configure(text_color="#E9D5FF")
            self.vol_status_lbl.configure(text=f"🔉 សំឡេងល្មមស្តាប់ ({pct}% Normal Ambient)", text_color="#E9D5FF")

    def _split_at_playhead(self):
        curr_t = self.timeline.current_time_sec
        self.timeline.split_bgm_at_time(curr_t)
        self.destroy()
        self.timeline.open_bgm_volume_dialog(self.seg_idx)

    def _merge_with_next(self):
        if self.seg_idx < len(self.timeline.bgm_segments) - 1:
            self.timeline.merge_bgm_segment_with_next(self.seg_idx)
            self.destroy()
            self.timeline.open_bgm_volume_dialog(self.seg_idx)

    def _reset_all(self):
        self.timeline.reset_bgm_segments()
        self.destroy()
        self.timeline.open_bgm_volume_dialog(0)

# ---------------------------------------------------------
# Subtitle Settings Localized Strings
# ---------------------------------------------------------
SUBTITLE_STRINGS = {
    "km": {
        "dialog_title": "💬 កំណត់ទំហំ ពណ៌ ទីតាំង & Font របស់ Subtitle",
        "hdr_title": "💬 កំណត់ Subtitle លើវីដេអូ",
        "has_subs": "✅ មាន {n} ប្រយោគ",
        "no_subs": "⚠️ មិនទាន់មាន Subtitle",
        "auto_prompt": "មិនទាន់មាន Subtitle សម្រាប់វីដេអូនេះទេ! ចុចដើម្បីបង្កើតស្វ័យប្រវត្តិ:",
        "auto_btn": "⚡ បង្កើតឥឡូវ",
        "enable_overlay": "បើកបង្ហាញ Subtitle (Enable CC Overlay)",
        "bg_enable_switch": "🔲 ដាក់ផ្ទៃខាងក្រោយអក្សរ (Enable Background)",
        "font_family": "🔤 ពុម្ពអក្សរ (Font Family):",
        "font_size": "📏 ទំហំអក្សរ (Font Size):",
        "bg_color": "🎨 ពណ៌ខាងក្រោយអក្សរ (Background Color):",
        "current_color": " ពណ៌បច្ចុប្បន្ន ",
        "custom_color": "🎨 រើសពណ៌តាមចិត្ត...",
        "opacity_title": "🎚️ ភាពស្រាល / ធ្ងន់នៃប្រអប់ (Opacity):",
        "opacity_trans": "ថ្លា / គ្មានប្រអប់",
        "opacity_solid": "ដិតខ្លាំងសុទ្ធ",
        "opacity_med": "ដិតល្មម",
        "opacity_light": "ស្រាលល្មម",
        "pos_title": "📍 ទីតាំងអក្សរ (Position & Drag):",
        "reset_pos": "🎯 ដាក់ចំកណ្តាលបាត",
        "drag_hint": "💡 គន្លឹះ៖ អ្នកអាចចុច និងអូស (Drag & Drop) អក្សរ subtitle នៅលើផ្ទាំងវីដេអូដោយផ្ទាល់បាន!",
        "pos_y": "↕️ ទីតាំង Y ឡើងលើ/ចុះក្រោម:",
        "pos_x": "↔️ ទីតាំង X ឆ្វេង/កណ្តាល/ស្តាំ:",
        "width_mode": "🔲 ទំហំទទឹងប្រអប់:",
        "width_full": "ពេញទទឹង (Full Width)",
        "width_fit": "តាមប្រវែងអក្សរ (Fit to Text)",
        "text_color": "✨ ពណ៌អក្សរ (Text Color):",
        "custom_text_color": "🎨 ពណ៌ផ្សេង...",
        "done_btn": "✅ រួចរាល់ (Apply & Close)",
        "color_picker_bg_title": "ជ្រើសរើសពណ៌ផ្ទៃខាងក្រោយ Subtitle",
        "color_picker_text_title": "ជ្រើសរើសពណ៌អក្សរ Subtitle",
        "presets_bg": [("🚫 គ្មានប្រអប់", "transparent"), ("⬛ ខ្មៅ", "#000000"), ("⬜ ប្រផេះ", "#64748B"), ("🟦 ខៀវ", "#1E293B"), ("🟫 ក្រហម", "#DC2626"), ("🟩 បៃតង", "#059669"), ("⬜ ស", "#F8FAFC")],
        "presets_text": [("⚪ ស", "#FFFFFF"), ("🟡 លឿង", "#FDE047"), ("🔵 ខៀវខ្ចី", "#38BDF8"), ("🟢 បៃតង", "#4ADE80")]
    },
    "en": {
        "dialog_title": "💬 Subtitle Size, Color, Position & Font Settings",
        "hdr_title": "💬 Video Subtitle Overlay Settings",
        "has_subs": "✅ {n} Sentences Available",
        "no_subs": "⚠️ No Subtitles Available",
        "auto_prompt": "No subtitles for this video yet! Click to auto-generate:",
        "auto_btn": "⚡ Generate Now",
        "enable_overlay": "Enable Subtitles (CC Overlay)",
        "bg_enable_switch": "🔲 Enable Subtitle Background",
        "font_family": "🔤 Font Family:",
        "font_size": "📏 Font Size:",
        "bg_color": "🎨 Background Color:",
        "current_color": " Current Color ",
        "custom_color": "🎨 Custom Color...",
        "opacity_title": "🎚️ Background Opacity:",
        "opacity_trans": "Transparent / None",
        "opacity_solid": "Solid Heavy",
        "opacity_med": "Medium Heavy",
        "opacity_light": "Light Semi-transparent",
        "pos_title": "📍 Position & Drag:",
        "reset_pos": "🎯 Center Bottom",
        "drag_hint": "💡 Tip: You can click & drag the subtitle directly on the video player!",
        "pos_y": "↕️ Vertical Y (Up / Down):",
        "pos_x": "↔️ Horizontal X (Left / Right):",
        "width_mode": "🔲 Box Width Mode:",
        "width_full": "Full Width",
        "width_fit": "Fit to Text",
        "text_color": "✨ Text Color:",
        "custom_text_color": "🎨 Custom...",
        "done_btn": "✅ Apply & Close",
        "color_picker_bg_title": "Choose Subtitle Background Color",
        "color_picker_text_title": "Choose Subtitle Text Color",
        "presets_bg": [("🚫 None", "transparent"), ("⬛ Black", "#000000"), ("⬜ Gray", "#64748B"), ("🟦 Navy", "#1E293B"), ("🟫 Red", "#DC2626"), ("🟩 Green", "#059669"), ("⬜ White", "#F8FAFC")],
        "presets_text": [("⚪ White", "#FFFFFF"), ("🟡 Yellow", "#FDE047"), ("🔵 Cyan", "#38BDF8"), ("🟢 Green", "#4ADE80")]
    },
    "zh": {
        "dialog_title": "💬 字幕大小、颜色、位置与字体设置",
        "hdr_title": "💬 视频字幕显示与排版设置",
        "has_subs": "✅ 已有 {n} 句字幕",
        "no_subs": "⚠️ 暂无字幕",
        "auto_prompt": "此视频尚未生成字幕！点击立即自动生成：",
        "auto_btn": "⚡ 立即生成",
        "enable_overlay": "开启字幕显示 (CC Overlay)",
        "bg_enable_switch": "🔲 开启字幕背景底框",
        "font_family": "🔤 字体 (Font Family):",
        "font_size": "📏 字号大小 (Font Size):",
        "bg_color": "🎨 字幕背景颜色 (Background):",
        "current_color": " 当前颜色 ",
        "custom_color": "🎨 自选颜色...",
        "opacity_title": "🎚️ 背景透明度/深浅 (Opacity):",
        "opacity_trans": "全透明 / 无底框",
        "opacity_solid": "纯色完全不透明",
        "opacity_med": "半透明较深",
        "opacity_light": "轻度半透明",
        "pos_title": "📍 字幕位置与拖拽:",
        "reset_pos": "🎯 居中底部",
        "drag_hint": "💡 提示：您可以直接在视频画面上用鼠标点击并拖拽字幕框到任意位置！",
        "pos_y": "↕️ Y 轴位置 (上下):",
        "pos_x": "↔️ X 轴位置 (左右):",
        "width_mode": "🔲 底框宽度:",
        "width_full": "全屏宽度 (Full Width)",
        "width_fit": "适应文字长度 (Fit to Text)",
        "text_color": "✨ 文字颜色 (Text Color):",
        "custom_text_color": "🎨 更多颜色...",
        "done_btn": "✅ 完成并关闭 (Apply & Close)",
        "color_picker_bg_title": "选择字幕背景颜色",
        "color_picker_text_title": "选择字幕文字颜色",
        "presets_bg": [("🚫 无底框", "transparent"), ("⬛ 黑色", "#000000"), ("⬜ 灰色", "#64748B"), ("🟦 深蓝", "#1E293B"), ("🟫 红色", "#DC2626"), ("🟩 墨绿", "#059669"), ("⬜ 白色", "#F8FAFC")],
        "presets_text": [("⚪ 白色", "#FFFFFF"), ("🟡 黄色", "#FDE047"), ("🔵 青蓝", "#38BDF8"), ("🟢 亮绿", "#4ADE80")]
    }
}

class SubtitleSettingsDialog(ctk.CTkToplevel):
    """
    Modern Premiere Pro Style Dialog for Subtitle Customization:
    - Khmer Font Family Selector (Khmer OS Battambang, Kantumruy, DaunPenh, Leelawadee UI, Noto Sans Khmer, etc.)
    - Font Size Slider (11 - 34 px)
    - Background Color Presets & Custom Color Picker (askcolor)
    - Background Opacity Slider: 0% (Transparent) to 100% (Solid) (ភាពស្រាល និង ធ្ងន់)
    - Full Drag-and-Drop Positioning + X & Y Coordinate Sliders
    - Box Width Mode (Full Width / Fit to Text)
    - Subtitle Text Color (White / Yellow / Cyan / Green / Custom)
    - Full Dynamic Localization (Khmer / English / Chinese)
    """
    def __init__(self, master, video_player, lang=None, on_auto_generate=None, on_change_state=None):
        super().__init__(master)
        self.video_player = video_player
        self.on_auto_generate = on_auto_generate
        self.on_change_state = on_change_state
        self.current_lang = lang or getattr(master, 'current_lang', 'km')
        
        self.geometry("520x640")
        self.resizable(False, False)
        self.configure(fg_color="#18181B")
        self.attributes("-topmost", True)
        self.update_idletasks()
        try:
            x = max(0, (self.winfo_screenwidth() - 520) // 2)
            y = max(0, (self.winfo_screenheight() - 640) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
        self.lift()
        self.focus_force()

        scroll = ctk.CTkScrollableFrame(self, fg_color="#18181B", corner_radius=10, border_color="#3B82F6", border_width=1)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # 1. Header Title & Subtitle Count
        hdr = ctk.CTkFrame(scroll, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(6, 4))

        self.hdr_title = ctk.CTkLabel(
            hdr,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=16, weight="bold"),
            text_color="#38BDF8"
        )
        self.hdr_title.pack(side="left")

        self.sub_count_lbl = ctk.CTkLabel(
            hdr,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold")
        )
        self.sub_count_lbl.pack(side="right")

        # Auto-generate banner if no subtitles yet
        sub_count = len(getattr(self.video_player, 'cc_subtitles', []))
        self.auto_box = None
        if sub_count == 0 and self.on_auto_generate:
            self.auto_box = ctk.CTkFrame(scroll, fg_color="#1E293B", corner_radius=6)
            self.auto_box.pack(fill="x", padx=10, pady=(0, 6))
            self.auto_box_lbl = ctk.CTkLabel(
                self.auto_box,
                text="",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
                text_color="#CBD5E1"
            )
            self.auto_box_lbl.pack(side="left", padx=8, pady=6)
            self.btn_auto_gen = ctk.CTkButton(
                self.auto_box,
                text="",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
                fg_color="#059669",
                hover_color="#047857",
                width=90,
                height=22,
                command=self._do_auto_generate
            )
            self.btn_auto_gen.pack(side="right", padx=8, pady=6)

        # 2. Main Enable Toggle Switch
        sw_box = ctk.CTkFrame(scroll, fg_color="#27272A", corner_radius=6)
        sw_box.pack(fill="x", padx=10, pady=4)
        
        self.sw_enable = ctk.CTkSwitch(
            sw_box,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            progress_color="#2563EB",
            command=self._on_toggle_enable
        )
        if getattr(self.video_player, 'cc_enabled', True):
            self.sw_enable.select()
        else:
            self.sw_enable.deselect()
        self.sw_enable.pack(side="left", padx=12, pady=6)

        # Card 1: Font & Size Controls
        c1 = ctk.CTkFrame(scroll, fg_color="#202023", corner_radius=8)
        c1.pack(fill="x", padx=10, pady=4)

        r_font = ctk.CTkFrame(c1, fg_color="transparent")
        r_font.pack(fill="x", padx=12, pady=(8, 4))
        self.lbl_font_title = ctk.CTkLabel(r_font, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"))
        self.lbl_font_title.pack(side="left")

        font_options = [
            "Khmer OS Battambang",
            "Kantumruy",
            "DaunPenh",
            "Leelawadee UI",
            "Noto Sans Khmer",
            "Khmer OS Content",
            "Khmer OS Muol",
            "Battambang",
            "Khmer OS Bokor",
            "Khmer OS Siemreap"
        ]
        cur_font = getattr(self.video_player, 'cc_font_family', 'Khmer OS Battambang')
        if cur_font not in font_options:
            font_options.insert(0, cur_font)

        self.opt_font = ctk.CTkOptionMenu(
            r_font,
            values=font_options,
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=11),
            width=210,
            height=26,
            fg_color="#1E293B",
            button_color="#334155",
            command=self._on_font_change
        )
        self.opt_font.set(cur_font)
        self.opt_font.pack(side="right")

        # Font Size Slider
        r_sz = ctk.CTkFrame(c1, fg_color="transparent")
        r_sz.pack(fill="x", padx=12, pady=(6, 2))
        self.lbl_font_size_title = ctk.CTkLabel(r_sz, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11))
        self.lbl_font_size_title.pack(side="left")
        self.lbl_font_size = ctk.CTkLabel(r_sz, text=f"{self.video_player.cc_font_size} px", font=ctk.CTkFont(size=11, weight="bold"), text_color="#FDE047", width=55)
        self.lbl_font_size.pack(side="right")

        self.slider_font = ctk.CTkSlider(c1, from_=11, to=34, number_of_steps=23, command=self._on_font_size_change)
        self.slider_font.set(self.video_player.cc_font_size)
        self.slider_font.pack(fill="x", padx=12, pady=(0, 8))

        # Card 2: Background Color & Opacity (ភាពស្រាល និង ធ្ងន់)
        c2 = ctk.CTkFrame(scroll, fg_color="#202023", corner_radius=8)
        c2.pack(fill="x", padx=10, pady=4)

        # Switch to enable / disable subtitle background (យើងចង់ដាក់ក៏បាន អត់ក៏បាន)
        r_sw_bg = ctk.CTkFrame(c2, fg_color="transparent")
        r_sw_bg.pack(fill="x", padx=12, pady=(8, 2))
        self.sw_bg_enable = ctk.CTkSwitch(
            r_sw_bg,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            progress_color="#0284C7",
            command=self._on_toggle_bg_enable
        )
        if getattr(self.video_player, 'cc_bg_enabled', True):
            self.sw_bg_enable.select()
        else:
            self.sw_bg_enable.deselect()
        self.sw_bg_enable.pack(side="left")

        r_bg = ctk.CTkFrame(c2, fg_color="transparent")
        r_bg.pack(fill="x", padx=12, pady=(4, 4))
        self.lbl_bg_color_title = ctk.CTkLabel(r_bg, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"))
        self.lbl_bg_color_title.pack(side="left")

        self.bg_preview_badge = ctk.CTkLabel(
            r_bg,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9, weight="bold"),
            fg_color=self.video_player.cc_base_bg_color,
            text_color="#FFFFFF" if self.video_player.cc_base_bg_color in ("#000000", "#1E293B", "#450A0A", "#3B0764", "#064E3B") else "#000000",
            corner_radius=4
        )
        self.bg_preview_badge.pack(side="right")

        # Color Presets Row + Custom Color Picker Button
        self.r_bg_btns = ctk.CTkFrame(c2, fg_color="transparent")
        self.r_bg_btns.pack(fill="x", padx=12, pady=2)
        self.preset_bg_widgets = []

        self.btn_custom_bg = ctk.CTkButton(
            self.r_bg_btns,
            text="",
            height=24,
            fg_color="#4F46E5",
            hover_color="#4338CA",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            command=self._open_custom_bg_color_picker
        )

        # Background Opacity Slider (ភាពស្រាល និង ធ្ងន់)
        r_op = ctk.CTkFrame(c2, fg_color="transparent")
        r_op.pack(fill="x", padx=12, pady=(8, 2))
        self.lbl_opacity_title = ctk.CTkLabel(r_op, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11))
        self.lbl_opacity_title.pack(side="left")

        op_val = getattr(self.video_player, 'cc_bg_opacity', 90)
        self.lbl_opacity = ctk.CTkLabel(r_op, text=self._format_opacity_text(op_val), font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"), text_color="#38BDF8")
        self.lbl_opacity.pack(side="right")

        self.slider_opacity = ctk.CTkSlider(c2, from_=0, to=100, number_of_steps=20, command=self._on_opacity_change)
        self.slider_opacity.set(op_val)
        self.slider_opacity.pack(fill="x", padx=12, pady=(0, 8))

        # Card 3: Position & Dragging (រំកិលអក្សរ)
        c3 = ctk.CTkFrame(scroll, fg_color="#202023", corner_radius=8)
        c3.pack(fill="x", padx=10, pady=4)

        r_pos_hdr = ctk.CTkFrame(c3, fg_color="transparent")
        r_pos_hdr.pack(fill="x", padx=12, pady=(8, 2))
        self.lbl_pos_title = ctk.CTkLabel(r_pos_hdr, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"))
        self.lbl_pos_title.pack(side="left")

        self.btn_reset_pos = ctk.CTkButton(
            r_pos_hdr,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9),
            width=115,
            height=20,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self._reset_position_center_bottom
        )
        self.btn_reset_pos.pack(side="right")

        # Drag hint banner
        hint_box = ctk.CTkFrame(c3, fg_color="#182334", corner_radius=4)
        hint_box.pack(fill="x", padx=12, pady=(2, 6))
        self.lbl_drag_hint = ctk.CTkLabel(
            hint_box,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            text_color="#93C5FD"
        )
        self.lbl_drag_hint.pack(anchor="w", padx=8, pady=3)

        # Vertical Position Y Slider
        r_pos_y = ctk.CTkFrame(c3, fg_color="transparent")
        r_pos_y.pack(fill="x", padx=12, pady=(2, 1))
        self.lbl_pos_y_title = ctk.CTkLabel(r_pos_y, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11))
        self.lbl_pos_y_title.pack(side="left")
        self.lbl_pos_y = ctk.CTkLabel(r_pos_y, text=f"{int(round(self.video_player.cc_pos_y_pct))}%", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A78BFA", width=45)
        self.lbl_pos_y.pack(side="right")

        self.slider_pos_y = ctk.CTkSlider(c3, from_=10, to=95, number_of_steps=85, command=self._on_pos_y_change)
        self.slider_pos_y.set(self.video_player.cc_pos_y_pct)
        self.slider_pos_y.pack(fill="x", padx=12, pady=(0, 6))

        # Horizontal Position X Slider
        r_pos_x = ctk.CTkFrame(c3, fg_color="transparent")
        r_pos_x.pack(fill="x", padx=12, pady=(2, 1))
        self.lbl_pos_x_title = ctk.CTkLabel(r_pos_x, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11))
        self.lbl_pos_x_title.pack(side="left")
        self.lbl_pos_x = ctk.CTkLabel(r_pos_x, text=f"{int(round(self.video_player.cc_pos_x_pct))}%", font=ctk.CTkFont(size=11, weight="bold"), text_color="#A78BFA", width=45)
        self.lbl_pos_x.pack(side="right")

        self.slider_pos_x = ctk.CTkSlider(c3, from_=10, to=90, number_of_steps=80, command=self._on_pos_x_change)
        self.slider_pos_x.set(self.video_player.cc_pos_x_pct)
        self.slider_pos_x.pack(fill="x", padx=12, pady=(0, 6))

        # Box Width Mode (Full Width / Fit Text)
        r_mode = ctk.CTkFrame(c3, fg_color="transparent")
        r_mode.pack(fill="x", padx=12, pady=(4, 8))
        self.lbl_width_title = ctk.CTkLabel(r_mode, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11))
        self.lbl_width_title.pack(side="left", padx=(0, 6))

        self.opt_width = ctk.CTkOptionMenu(
            r_mode,
            values=["ពេញទទឹង (Full Width)", "តាមប្រវែងអក្សរ (Fit to Text)"],
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            width=180,
            height=24,
            command=self._on_width_mode_change
        )
        self.opt_width.pack(side="left")

        # Card 4: Text Color
        c4 = ctk.CTkFrame(scroll, fg_color="#202023", corner_radius=8)
        c4.pack(fill="x", padx=10, pady=4)

        self.r_tc = ctk.CTkFrame(c4, fg_color="transparent")
        self.r_tc.pack(fill="x", padx=12, pady=8)
        self.lbl_text_color_title = ctk.CTkLabel(self.r_tc, text="", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"))
        self.lbl_text_color_title.pack(side="left", padx=(0, 8))
        self.preset_text_widgets = []

        self.btn_custom_tc = ctk.CTkButton(
            self.r_tc,
            text="",
            height=24,
            fg_color="#374151",
            hover_color="#4B5563",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9),
            command=self._open_custom_text_color_picker
        )

        # Bottom Close Button
        b_box = ctk.CTkFrame(scroll, fg_color="transparent")
        b_box.pack(fill="x", padx=10, pady=(8, 4))

        self.btn_close = ctk.CTkButton(
            b_box,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            height=32,
            command=self._apply_and_close
        )
        self.btn_close.pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._apply_and_close)

        self.apply_language(self.current_lang)

    def apply_language(self, lang: str):
        """Dynamically translates all UI texts in this dialog according to app language."""
        self.current_lang = lang if lang in SUBTITLE_STRINGS else "km"
        tr = SUBTITLE_STRINGS[self.current_lang]

        self.title(tr["dialog_title"])
        self.hdr_title.configure(text=tr["hdr_title"])

        sub_count = len(getattr(self.video_player, 'cc_subtitles', []))
        if sub_count > 0:
            self.sub_count_lbl.configure(text=tr["has_subs"].format(n=sub_count), text_color="#10B981")
        else:
            self.sub_count_lbl.configure(text=tr["no_subs"], text_color="#EF4444")

        if self.auto_box and hasattr(self, 'auto_box_lbl'):
            self.auto_box_lbl.configure(text=tr["auto_prompt"])
            self.btn_auto_gen.configure(text=tr["auto_btn"])

        self.sw_enable.configure(text=tr["enable_overlay"])
        if hasattr(self, 'sw_bg_enable'):
            self.sw_bg_enable.configure(text=tr.get("bg_enable_switch", "🔲 ដាក់ផ្ទៃខាងក្រោយអក្សរ (Enable Background)"))
        self.lbl_font_title.configure(text=tr["font_family"])
        self.lbl_font_size_title.configure(text=tr["font_size"])
        self.lbl_bg_color_title.configure(text=tr["bg_color"])
        self.bg_preview_badge.configure(text=tr["current_color"])
        self.lbl_opacity_title.configure(text=tr["opacity_title"])
        self.lbl_opacity.configure(text=self._format_opacity_text(self.slider_opacity.get()))
        self.lbl_pos_title.configure(text=tr["pos_title"])
        self.btn_reset_pos.configure(text=tr["reset_pos"])
        self.lbl_drag_hint.configure(text=tr["drag_hint"])
        self.lbl_pos_y_title.configure(text=tr["pos_y"])
        self.lbl_pos_x_title.configure(text=tr["pos_x"])
        self.lbl_width_title.configure(text=tr["width_mode"])

        # Update width dropdown options
        cur_w_is_full = getattr(self.video_player, 'cc_box_full_width', False)
        w_opts = [tr["width_fit"], tr["width_full"]]
        self.opt_width.configure(values=w_opts)
        self.opt_width.set(tr["width_full"] if cur_w_is_full else tr["width_fit"])

        self.lbl_text_color_title.configure(text=tr["text_color"])
        self.btn_close.configure(text=tr["done_btn"])

        # Rebuild BG preset buttons
        for w in self.preset_bg_widgets:
            w.destroy()
        self.preset_bg_widgets.clear()
        self.btn_custom_bg.pack_forget()

        for lbl_p, col_hex in tr["presets_bg"]:
            b = ctk.CTkButton(
                self.r_bg_btns,
                text=lbl_p,
                width=55,
                height=24,
                fg_color="#334155",
                hover_color="#475569",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9),
                command=lambda c=col_hex: self._on_bg_color_pick(c)
            )
            b.pack(side="left", padx=2)
            self.preset_bg_widgets.append(b)

        self.btn_custom_bg.configure(text=tr["custom_color"])
        self.btn_custom_bg.pack(side="left", padx=(6, 2), fill="x", expand=True)

        # Rebuild Text preset buttons
        for w in self.preset_text_widgets:
            w.destroy()
        self.preset_text_widgets.clear()
        self.btn_custom_tc.pack_forget()

        for lbl_t, col_t in tr["presets_text"]:
            b = ctk.CTkButton(
                self.r_tc,
                text=lbl_t,
                width=58,
                height=24,
                fg_color="#334155",
                hover_color="#475569",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9),
                command=lambda c=col_t: self._on_text_color_pick(c)
            )
            b.pack(side="left", padx=2)
            self.preset_text_widgets.append(b)

        self.btn_custom_tc.configure(text=tr["custom_text_color"])
        self.btn_custom_tc.pack(side="left", padx=(4, 2), fill="x", expand=True)

    def _format_opacity_text(self, val):
        pct = int(round(val))
        tr = SUBTITLE_STRINGS.get(self.current_lang, SUBTITLE_STRINGS["km"])
        if pct <= 5:
            return f"{pct}% ({tr['opacity_trans']})"
        elif pct >= 95:
            return f"{pct}% ({tr['opacity_solid']})"
        elif pct >= 60:
            return f"{pct}% ({tr['opacity_med']})"
        else:
            return f"{pct}% ({tr['opacity_light']})"

    def _apply_and_close(self):
        """Immediately applies subtitle settings, triggers frame re-render, notifies parent, and closes dialog."""
        try:
            self.video_player.refresh_current_frame()
        except Exception:
            pass
        if hasattr(self, 'on_change_state') and callable(self.on_change_state):
            try:
                self.on_change_state()
            except Exception:
                pass
        self.destroy()

    def _do_auto_generate(self):
        self.destroy()
        if self.on_auto_generate:
            self.on_auto_generate()

    def _on_toggle_enable(self):
        self.video_player.cc_enabled = bool(self.sw_enable.get())
        if self.on_change_state:
            self.on_change_state()
        self.video_player.refresh_current_frame()

    def _on_toggle_bg_enable(self):
        is_on = bool(self.sw_bg_enable.get())
        self.video_player.cc_bg_enabled = is_on
        if is_on:
            if getattr(self.video_player, 'cc_base_bg_color', '') == 'transparent' or getattr(self.video_player, 'cc_bg_opacity', 0) <= 5:
                self.video_player.cc_base_bg_color = "#000000"
                self.video_player.cc_bg_opacity = 90
                self.slider_opacity.set(90)
                self.lbl_opacity.configure(text=self._format_opacity_text(90))
                self.bg_preview_badge.configure(fg_color="#000000", text_color="#FFFFFF")
            else:
                cur_c = getattr(self.video_player, 'cc_base_bg_color', '#000000')
                self.bg_preview_badge.configure(fg_color=cur_c, text_color="#FFFFFF" if cur_c in ("#000000", "#1E293B", "#DC2626", "#3B0764", "#059669") else "#000000")
        else:
            self.bg_preview_badge.configure(fg_color="#374151", text_color="#9CA3AF")
        self.video_player.refresh_current_frame()
        if hasattr(self, 'on_change_state') and callable(self.on_change_state):
            self.on_change_state()

    def _on_font_change(self, font_name):
        self.video_player.cc_font_family = font_name
        self.video_player.refresh_current_frame()

    def _on_font_size_change(self, val):
        self.video_player.cc_font_size = int(round(val))
        self.lbl_font_size.configure(text=f"{self.video_player.cc_font_size} px")
        self.video_player.refresh_current_frame()

    def _on_bg_color_pick(self, color_hex):
        if color_hex == "transparent":
            self.video_player.cc_bg_enabled = False
            self.video_player.cc_base_bg_color = "transparent"
            self.video_player.cc_bg_opacity = 0
            self.slider_opacity.set(0)
            self.lbl_opacity.configure(text=self._format_opacity_text(0))
            self.bg_preview_badge.configure(fg_color="#374151", text_color="#9CA3AF")
            if hasattr(self, 'sw_bg_enable'):
                self.sw_bg_enable.deselect()
        else:
            self.video_player.cc_bg_enabled = True
            self.video_player.cc_base_bg_color = color_hex
            if getattr(self.video_player, 'cc_bg_opacity', 0) <= 5:
                self.video_player.cc_bg_opacity = 90
                self.slider_opacity.set(90)
                self.lbl_opacity.configure(text=self._format_opacity_text(90))
            dark_colors = ("#000000", "#1E293B", "#DC2626", "#3B0764", "#059669", "#64748B", "#450A0A", "#064E3B")
            self.bg_preview_badge.configure(
                fg_color=color_hex,
                text_color="#FFFFFF" if color_hex in dark_colors else "#000000"
            )
            if hasattr(self, 'sw_bg_enable'):
                self.sw_bg_enable.select()
        self.video_player.refresh_current_frame()
        if hasattr(self, 'on_change_state') and callable(self.on_change_state):
            self.on_change_state()

    def _open_custom_bg_color_picker(self):
        tr = SUBTITLE_STRINGS.get(self.current_lang, SUBTITLE_STRINGS["km"])
        cur = self.video_player.cc_base_bg_color
        chosen = colorchooser.askcolor(color=cur if cur != "transparent" else "#64748B", title=tr["color_picker_bg_title"], parent=self)
        if chosen and chosen[1]:
            self._on_bg_color_pick(chosen[1])

    def _on_opacity_change(self, val):
        self.video_player.cc_bg_opacity = int(round(val))
        if self.video_player.cc_bg_opacity <= 5:
            self.video_player.cc_bg_enabled = False
            self.video_player.cc_base_bg_color = "transparent"
            self.bg_preview_badge.configure(fg_color="#374151", text_color="#9CA3AF")
            if hasattr(self, 'sw_bg_enable'):
                self.sw_bg_enable.deselect()
        else:
            self.video_player.cc_bg_enabled = True
            if getattr(self.video_player, 'cc_base_bg_color', '') == "transparent":
                self.video_player.cc_base_bg_color = "#64748B"
            dark_colors = ("#000000", "#1E293B", "#DC2626", "#3B0764", "#059669", "#64748B", "#450A0A", "#064E3B")
            self.bg_preview_badge.configure(
                fg_color=self.video_player.cc_base_bg_color,
                text_color="#FFFFFF" if self.video_player.cc_base_bg_color in dark_colors else "#000000"
            )
            if hasattr(self, 'sw_bg_enable'):
                self.sw_bg_enable.select()
        self.lbl_opacity.configure(text=self._format_opacity_text(val))
        self.video_player.refresh_current_frame()
        if hasattr(self, 'on_change_state') and callable(self.on_change_state):
            self.on_change_state()

    def _on_pos_y_change(self, val):
        self.video_player.cc_pos_y_pct = float(round(val, 1))
        self.lbl_pos_y.configure(text=f"{int(round(val))}%")
        self.video_player.refresh_current_frame()

    def _on_pos_x_change(self, val):
        self.video_player.cc_pos_x_pct = float(round(val, 1))
        self.lbl_pos_x.configure(text=f"{int(round(val))}%")
        self.video_player.refresh_current_frame()

    def _reset_position_center_bottom(self):
        self.video_player.cc_pos_x_pct = 50.0
        self.video_player.cc_pos_y_pct = 85.0
        self.slider_pos_x.set(50.0)
        self.slider_pos_y.set(85.0)
        self.lbl_pos_x.configure(text="50%")
        self.lbl_pos_y.configure(text="85%")
        self.video_player.refresh_current_frame()

    def _on_width_mode_change(self, choice):
        self.video_player.cc_box_full_width = ("ពេញទទឹង" in choice or "Full" in choice or "全屏" in choice)
        self.video_player.refresh_current_frame()
        if hasattr(self, 'on_change_state') and callable(self.on_change_state):
            self.on_change_state()

    def _on_text_color_pick(self, color_hex):
        self.video_player.cc_text_color = color_hex
        self.video_player.refresh_current_frame()

    def _open_custom_text_color_picker(self):
        tr = SUBTITLE_STRINGS.get(self.current_lang, SUBTITLE_STRINGS["km"])
        chosen = colorchooser.askcolor(color=self.video_player.cc_text_color, title=tr["color_picker_text_title"], parent=self)
        if chosen and chosen[1]:
            self._on_text_color_pick(chosen[1])

# ---------------------------------------------------------
# Video Crop & Transform Dialog (Aspect Ratio & Flip Studio)
# ---------------------------------------------------------
class VideoCropDialog(ctk.CTkToplevel):
    """
    Modern Video Transformation Dialog:
    - ↔️ Flip Horizontal (Mirror left-right)
    - ↕️ Flip Vertical (Flip upside-down)
    - 📐 Aspect Ratio Presets (9:16 TikTok, 16:9 YouTube, 1:1 Square, 4:3, 2.35:1 Cinema, Original)
    - ✂️ Free Custom Crop Margins (Left, Right, Top, Bottom %)
    - Real-time Interactive Live Preview on Video Canvas
    """
    def __init__(self, master, video_player):
        super().__init__(master)
        self.video_player = video_player
        self.title("✂️ កាត់តម្រឹម & ត្រឡប់វីដេអូ (Crop & Flip Video)")
        self.geometry("490x590")
        self.resizable(False, False)
        self.configure(fg_color="#0F172A")
        self.attributes("-topmost", True)
        self.transient(master)
        self.grab_set()

        self.update_idletasks()
        try:
            x = max(0, (self.winfo_screenwidth() - 490) // 2)
            y = max(0, (self.winfo_screenheight() - 590) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self._build_ui()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr,
            text="✂️ កាត់តម្រឹម & ត្រឡប់វីដេអូ (Crop & Flip Studio)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=13, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="left", padx=16, pady=6)

        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=10)

        # 1. Flip Section
        c_flip = ctk.CTkFrame(container, fg_color="#1E293B", corner_radius=8, border_width=1, border_color="#334155")
        c_flip.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            c_flip,
            text="🔄 ត្រឡប់ទិសវីដេអូ (Video Flip & Mirror)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#F1F5F9"
        ).pack(anchor="w", padx=12, pady=(8, 6))

        flip_btns_row = ctk.CTkFrame(c_flip, fg_color="transparent")
        flip_btns_row.pack(fill="x", padx=12, pady=(0, 10))

        self.btn_dlg_fliph = ctk.CTkButton(
            flip_btns_row,
            text="↔️ ត្រឡប់ឆ្វេង-ស្ដាំ (Flip H)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            height=32,
            command=self._on_toggle_flip_h
        )
        self.btn_dlg_fliph.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_dlg_flipv = ctk.CTkButton(
            flip_btns_row,
            text="↕️ ត្រឡប់លើ-ក្រោម (Flip V)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            height=32,
            command=self._on_toggle_flip_v
        )
        self.btn_dlg_flipv.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # 2. Preset Aspect Ratio Crops
        c_preset = ctk.CTkFrame(container, fg_color="#1E293B", corner_radius=8, border_width=1, border_color="#334155")
        c_preset.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            c_preset,
            text="📐 ទម្រង់ខ្នាត Aspect Ratio (Preset Crops)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#F1F5F9"
        ).pack(anchor="w", padx=12, pady=(8, 6))

        presets_grid1 = ctk.CTkFrame(c_preset, fg_color="transparent")
        presets_grid1.pack(fill="x", padx=12, pady=(0, 4))

        self.preset_btns = {}
        p_row1 = [
            ("none", "❌ ដើម (Full)"),
            ("9:16", "📱 9:16 (TikTok)"),
            ("16:9", "🎬 16:9 (YouTube)")
        ]
        for mode, lbl in p_row1:
            btn = ctk.CTkButton(
                presets_grid1, text=lbl,
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
                height=30,
                command=lambda m=mode: self._on_preset_click(m)
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.preset_btns[mode] = btn

        presets_grid2 = ctk.CTkFrame(c_preset, fg_color="transparent")
        presets_grid2.pack(fill="x", padx=12, pady=(0, 10))

        p_row2 = [
            ("1:1", "⬛ 1:1 (Square)"),
            ("4:3", "📺 4:3 (Classic)"),
            ("2.35:1", "🎞️ 2.35:1 (Cinema)")
        ]
        for mode, lbl in p_row2:
            btn = ctk.CTkButton(
                presets_grid2, text=lbl,
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
                height=30,
                command=lambda m=mode: self._on_preset_click(m)
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)
            self.preset_btns[mode] = btn

        # 3. Custom Margins (%)
        c_margins = ctk.CTkFrame(container, fg_color="#1E293B", corner_radius=8, border_width=1, border_color="#334155")
        c_margins.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            c_margins,
            text="✂️ កាត់តម្រឹមតាមភាគរយ % (Custom Margins)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#F1F5F9"
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self.sliders = {}
        for side, side_lbl in [("left", "ឆ្វេង (Left)"), ("right", "ស្ដាំ (Right)"), ("top", "លើ (Top)"), ("bottom", "ក្រោម (Bottom)")]:
            row = ctk.CTkFrame(c_margins, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            lbl = ctk.CTkLabel(row, text=f"{side_lbl} : 0%", width=110, anchor="w", font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10))
            lbl.pack(side="left")
            cur_val = self.video_player.crop_margins.get(side, 0.0)
            sl = ctk.CTkSlider(row, from_=0.0, to=40.0, number_of_steps=80, command=lambda v, s=side, l=lbl, slb=side_lbl: self._on_margin_slider(s, v, l, slb))
            sl.set(cur_val)
            sl.pack(side="left", fill="x", expand=True, padx=(4, 0))
            lbl.configure(text=f"{side_lbl} : {int(cur_val)}%")
            self.sliders[side] = (sl, lbl, side_lbl)

        # 4. Live Dimension Status Card
        c_status = ctk.CTkFrame(container, fg_color="#0B132B", corner_radius=8, border_width=1, border_color="#1E293B")
        c_status.pack(fill="x", pady=(0, 10))
        self.lbl_info = ctk.CTkLabel(
            c_status, text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            text_color="#38BDF8",
            justify="center"
        )
        self.lbl_info.pack(fill="x", padx=8, pady=8)

        # Footer Actions
        footer = ctk.CTkFrame(self, fg_color="#1E293B", height=48, corner_radius=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        ctk.CTkButton(
            footer, text="🔄 កំណត់ដើមវិញ (Reset)", width=140, height=28,
            fg_color="#374151", hover_color="#4B5563",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._on_reset
        ).pack(side="left", padx=12, pady=10)

        ctk.CTkButton(
            footer, text="✅ យល់ព្រម (Done)", width=110, height=28,
            fg_color="#059669", hover_color="#047857",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self.destroy
        ).pack(side="right", padx=12, pady=10)

        self._update_ui_state()

    def _on_toggle_flip_h(self):
        self.video_player.toggle_flip_horizontal()
        self._update_ui_state()

    def _on_toggle_flip_v(self):
        self.video_player.toggle_flip_vertical()
        self._update_ui_state()

    def _on_preset_click(self, mode):
        self.video_player.set_crop(mode)
        for side, (sl, lbl, side_lbl) in self.sliders.items():
            sl.set(0.0)
            lbl.configure(text=f"{side_lbl} : 0%")
        self._update_ui_state()

    def _on_margin_slider(self, side, val, lbl, side_lbl):
        lbl.configure(text=f"{side_lbl} : {int(val)}%")
        self.video_player.crop_margins[side] = float(val)
        self.video_player.crop_mode = "custom"
        self.video_player.refresh_current_frame()
        self._update_ui_state(skip_slider_update=True)

    def _on_reset(self):
        self.video_player.reset_transform()
        for side, (sl, lbl, side_lbl) in self.sliders.items():
            sl.set(0.0)
            lbl.configure(text=f"{side_lbl} : 0%")
        self._update_ui_state()

    def _update_ui_state(self, skip_slider_update=False):
        is_fliph = getattr(self.video_player, 'flip_horizontal', False)
        is_flipv = getattr(self.video_player, 'flip_vertical', False)
        self.btn_dlg_fliph.configure(
            text="↔️ ត្រឡប់ឆ្វេង-ស្ដាំ: បើក ✓" if is_fliph else "↔️ ត្រឡប់ឆ្វេង-ស្ដាំ: បិទ",
            fg_color="#0284C7" if is_fliph else "#334155",
            hover_color="#0369A1" if is_fliph else "#475569"
        )
        self.btn_dlg_flipv.configure(
            text="↕️ ត្រឡប់លើ-ក្រោម: បើក ✓" if is_flipv else "↕️ ត្រឡប់លើ-ក្រោម: បិទ",
            fg_color="#0284C7" if is_flipv else "#334155",
            hover_color="#0369A1" if is_flipv else "#475569"
        )

        cur_mode = getattr(self.video_player, 'crop_mode', 'none')
        for mode, btn in self.preset_btns.items():
            is_active = (cur_mode == mode)
            btn.configure(
                fg_color="#0284C7" if is_active else "#334155",
                hover_color="#0369A1" if is_active else "#475569"
            )

        if not skip_slider_update:
            margins = getattr(self.video_player, 'crop_margins', {})
            for side, (sl, lbl, side_lbl) in self.sliders.items():
                v = margins.get(side, 0.0)
                sl.set(v)
                lbl.configure(text=f"{side_lbl} : {int(v)}%")

        orig_w, orig_h = 1920, 1080
        if getattr(self.video_player, 'cap', None) and self.video_player.cap.isOpened():
            orig_w = int(self.video_player.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
            orig_h = int(self.video_player.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
        elif getattr(self.video_player, '_last_frame', None) is not None:
            orig_h, orig_w = self.video_player._last_frame.shape[:2]

        box = self.video_player.get_effective_crop_box(orig_w, orig_h)
        if box:
            cw = box[2] - box[0]
            ch = box[3] - box[1]
            info_txt = f"📐 វិមាត្រដើម: {orig_w}x{orig_h} ➔ វិមាត្រក្រោយកាត់: {cw}x{ch} ({cur_mode})"
        else:
            info_txt = f"📐 វិមាត្រដើម: {orig_w}x{orig_h} (ពេញលេញ 100% គ្មាន Crop)"

        flip_flags = []
        if is_fliph: flip_flags.append("↔️ ឆ្វេង-ស្ដាំ")
        if is_flipv: flip_flags.append("↕️ លើ-ក្រោម")
        if flip_flags:
            info_txt += f"\n🔄 ត្រឡប់ទិស៖ {' + '.join(flip_flags)}"

        self.lbl_info.configure(text=info_txt)

# ---------------------------------------------------------
# Dynamic Video Export Dialog (Resolution Capped at Source)
# ---------------------------------------------------------
class ExportVideoDialog(ctk.CTkToplevel):
    """
    Dialog for exporting final video with custom Quality (Resolution capped at source),
    Bitrate Preset, Subtitle embedding mode, and custom output path.
    """
    def __init__(self, master_app):
        super().__init__(master_app)
        self.master_app = master_app
        self.current_lang = getattr(master_app, 'current_lang', 'km')
        tr = UI_STRINGS.get(self.current_lang, UI_STRINGS['km'])

        self.title(tr.get("export_dialog_title", "📤 Export វីដេអូច្របាច់សំឡេង (Export Dubbed Video)"))
        self.geometry("580x630")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.transient(master_app)
        self.grab_set()

        self.update_idletasks()
        try:
            x = (self.winfo_screenwidth() - 580) // 2
            y = (self.winfo_screenheight() - 630) // 2
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        self.configure(fg_color="#181824")
        self._load_video_metadata()
        self._build_ui()

    def _load_video_metadata(self):
        video_path = self.master_app.v1_video_entry.get().strip() if hasattr(self.master_app, 'v1_video_entry') else ""
        self.video_path = video_path
        self.v_info = get_video_info(video_path) if (video_path and os.path.exists(video_path)) else {'width': 1920, 'height': 1080, 'duration': 0.0, 'size_mb': 0.0}
        self.src_w = int(self.v_info.get('width', 0) or 1920)
        self.src_h = int(self.v_info.get('height', 0) or 1080)
        self.duration = float(self.v_info.get('duration', 0.0))
        self.size_mb = float(self.v_info.get('size_mb', 0.0))

        # Build dynamic tiers strictly capped at source resolution
        self.quality_tiers = self._compute_quality_tiers(self.src_w, self.src_h)

    def _compute_quality_tiers(self, src_w: int, src_h: int):
        standard_tiers = [
            (2160, "4K Ultra HD (2160p)"),
            (1440, "2K QHD (1440p)"),
            (1080, "1080p Full HD"),
            (720, "720p HD"),
            (480, "480p SD"),
            (360, "360p Low"),
        ]

        orig_tag = f"💎 Original ({src_w}x{src_h} - គុណភាពដើម)" if self.current_lang == "km" else (
            f"💎 Original ({src_w}x{src_h} - 原画质)" if self.current_lang == "zh" else f"💎 Original ({src_w}x{src_h})"
        )
        tiers = [{"label": orig_tag, "height": src_h, "width": src_w, "is_orig": True}]

        for h, name in standard_tiers:
            # Strictly tiers lower than src_h (margin 20px)
            if h < src_h - 20:
                calc_w = int(round((src_w / max(1, src_h)) * h))
                if calc_w % 2 != 0:
                    calc_w += 1
                tiers.append({
                    "label": f"✨ {name} ({calc_w}x{h})",
                    "height": h,
                    "width": calc_w,
                    "is_orig": False
                })
        return tiers

    def _build_ui(self):
        tr = UI_STRINGS.get(self.current_lang, UI_STRINGS['km'])

        # Header
        header = ctk.CTkFrame(self, fg_color="#241B35", corner_radius=0, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text=tr.get("export_heading", "📤 ការកំណត់ Export វីដេអូ (Video Export Studio)"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=14, weight="bold"),
            text_color="#F3E8FF"
        ).pack(side="left", padx=16, pady=6)

        # Scrollable container
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=14, pady=8)

        # Card 1: Source Video Info
        c_info = ctk.CTkFrame(container, fg_color="#1E293B", corner_radius=8, border_width=1, border_color="#334155")
        c_info.pack(fill="x", pady=(0, 8), padx=2)

        info_hdr = ctk.CTkFrame(c_info, fg_color="transparent")
        info_hdr.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            info_hdr,
            text=f"🎬 វីដេអូដើម៖ {os.path.basename(self.video_path)}" if self.video_path else "🎬 មិនទាន់មានវីដេអូ",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#38BDF8"
        ).pack(side="left")

        sz_str = f"{self.size_mb} MB" if self.size_mb > 0 else "N/A"
        dur_str = format_time(self.duration) if self.duration > 0 else "00:00"
        info_sub = ctk.CTkFrame(c_info, fg_color="transparent")
        info_sub.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(
            info_sub,
            text=f"📐 កម្រិតដើម: {self.src_w}x{self.src_h} ({self.src_h}p)  |  ⏱️ ប្រវែង: {dur_str}  |  💾 ទំហំ: {sz_str}",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            text_color="#94A3B8"
        ).pack(side="left")

        # Card 1.5: Video Transform & Crop Info
        c_crop = ctk.CTkFrame(container, fg_color="#1E2235", corner_radius=8, border_width=1, border_color="#334155")
        c_crop.pack(fill="x", pady=(0, 8), padx=2)

        crop_row = ctk.CTkFrame(c_crop, fg_color="transparent")
        crop_row.pack(fill="x", padx=12, pady=8)

        vplayer = getattr(self.master_app, 'video_player', None)
        fliph = getattr(vplayer, 'flip_horizontal', False) if vplayer else False
        flipv = getattr(vplayer, 'flip_vertical', False) if vplayer else False
        cmode = getattr(vplayer, 'crop_mode', 'none') if vplayer else 'none'

        crop_parts = []
        if fliph: crop_parts.append("↔️ Flip H")
        if flipv: crop_parts.append("↕️ Flip V")
        if cmode != "none": crop_parts.append(f"✂️ Crop {cmode}")
        summary_txt = " | ".join(crop_parts) if crop_parts else "ដើម (គ្មាន Flip / Crop)"

        self.lbl_export_crop_status = ctk.CTkLabel(
            crop_row,
            text=f"✂️ ទម្រង់វីដេអូ៖ {summary_txt}",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#38BDF8"
        )
        self.lbl_export_crop_status.pack(side="left")

        def _open_crop_from_export():
            if vplayer:
                VideoCropDialog(self, vplayer)
                self.after(500, self._refresh_crop_status)

        ctk.CTkButton(
            crop_row,
            text="✂️ កែសម្រួល...",
            width=90,
            height=26,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            command=_open_crop_from_export
        ).pack(side="right")

        # Card 2: Quality Selection
        c_qual = ctk.CTkFrame(container, fg_color="#1E2235", corner_radius=8, border_width=1, border_color="#334155")
        c_qual.pack(fill="x", pady=(0, 8), padx=2)

        q_row1 = ctk.CTkFrame(c_qual, fg_color="transparent")
        q_row1.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            q_row1,
            text=tr.get("export_quality_lbl", "📐 កម្រិតគុណភាពវីដេអូ (Resolution / Quality)៖"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#F1F5F9"
        ).pack(side="left")

        tier_labels = [t['label'] for t in self.quality_tiers]
        self.quality_dropdown = ctk.CTkOptionMenu(
            c_qual,
            values=tier_labels,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            height=30,
            fg_color="#0284C7",
            button_color="#0369A1",
            button_hover_color="#075985"
        )
        self.quality_dropdown.set(tier_labels[0])
        self.quality_dropdown.pack(fill="x", padx=12, pady=(2, 4))

        # Dynamic Quality Limit Hint Badge
        hint_text = tr.get("export_quality_hint", "💡 គុណភាពត្រូវបានកំណត់ត្រឹមកម្រិតវីដេអូដើម ({res}p) ចុះក្រោម").format(res=self.src_h)
        ctk.CTkLabel(
            c_qual,
            text=hint_text,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            text_color="#FDE047"
        ).pack(anchor="w", padx=12, pady=(0, 8))

        # Card 3: Encoding Preset (CRF)
        c_pre = ctk.CTkFrame(container, fg_color="#1E2235", corner_radius=8, border_width=1, border_color="#334155")
        c_pre.pack(fill="x", pady=(0, 8), padx=2)

        pre_row = ctk.CTkFrame(c_pre, fg_color="transparent")
        pre_row.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            pre_row,
            text=tr.get("export_preset_lbl", "⚡ គុណភាព Encoding (Preset)៖"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#F1F5F9"
        ).pack(side="left")

        preset_opts = [
            "✨ ស្ដង់ដារ (Standard - CRF 22)",
            "🔥 គុណភាពខ្ពស់បំផុត (High Quality - CRF 18)",
            "⚡ លឿន & សន្សំទំហំ (Fast & Small - CRF 26)"
        ] if self.current_lang == "km" else (
            [
                "✨ 标准画质 (Standard - CRF 22)",
                "🔥 超高清 (High Quality - CRF 18)",
                "⚡ 快速省空间 (Fast & Small - CRF 26)"
            ] if self.current_lang == "zh" else [
                "✨ Standard (CRF 22)",
                "🔥 High Quality (CRF 18)",
                "⚡ Fast & Small (CRF 26)"
            ]
        )
        self.preset_dropdown = ctk.CTkOptionMenu(
            c_pre,
            values=preset_opts,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            height=28
        )
        self.preset_dropdown.set(preset_opts[0])
        self.preset_dropdown.pack(fill="x", padx=12, pady=(2, 8))

        # Card 4: Subtitle Mode
        c_sub = ctk.CTkFrame(container, fg_color="#1E2235", corner_radius=8, border_width=1, border_color="#334155")
        c_sub.pack(fill="x", pady=(0, 8), padx=2)

        sub_row = ctk.CTkFrame(c_sub, fg_color="transparent")
        sub_row.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            sub_row,
            text=tr.get("export_sub_mode_lbl", "💬 ជម្រើសអក្សរ Subtitle៖"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#F1F5F9"
        ).pack(side="left")

        sub_opts = [
            tr.get("export_sub_hard", "🔥 Hardcode Subtitle (ដុតអក្សរ Subtitle ជាប់លើវីដេអូ - ណែនាំ)"),
            tr.get("export_sub_soft", "🔲 Soft Subtitle (ឯកសារ .ass ក្រៅវីដេអូ)"),
            tr.get("export_sub_none", "🚫 មិនដាក់ Subtitle (No Subtitles)")
        ]
        self.sub_mode_dropdown = ctk.CTkOptionMenu(
            c_sub,
            values=sub_opts,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            height=28
        )
        self.sub_mode_dropdown.set(sub_opts[0])
        self.sub_mode_dropdown.pack(fill="x", padx=12, pady=(2, 8))

        # Card 5: Destination Output Path
        c_path = ctk.CTkFrame(container, fg_color="#1E2235", corner_radius=8, border_width=1, border_color="#334155")
        c_path.pack(fill="x", pady=(0, 8), padx=2)

        p_row1 = ctk.CTkFrame(c_path, fg_color="transparent")
        p_row1.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            p_row1,
            text=tr.get("export_path_lbl", "📁 ទីតាំងរក្សាទុកឯកសារ (Output Path)៖"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#F1F5F9"
        ).pack(side="left")

        p_row2 = ctk.CTkFrame(c_path, fg_color="transparent")
        p_row2.pack(fill="x", padx=12, pady=(2, 8))

        init_dir = os.path.dirname(self.video_path) if self.video_path else os.getcwd()
        base_name = os.path.splitext(os.path.basename(self.video_path))[0] if self.video_path else "dubbed"
        def_out = os.path.join(init_dir, f"{base_name}_dubbed_{int(time.time())}.mp4")

        self.dest_entry = ctk.CTkEntry(p_row2, height=28, font=ctk.CTkFont(size=11))
        self.dest_entry.insert(0, def_out)
        self.dest_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            p_row2,
            text=tr.get("export_browse_btn", "📁 ផ្លាស់ប្ដូរ..."),
            width=85,
            height=28,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            command=self._browse_dest_path
        ).pack(side="right")

        # Bottom Frame: Progress + Buttons
        bot = ctk.CTkFrame(self, fg_color="#13131D", corner_radius=0)
        bot.pack(side="bottom", fill="x")

        self.status_lbl = ctk.CTkLabel(
            bot,
            text="រួចរាល់សម្រាប់ការ Export (Ready to export)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#60A5FA"
        )
        self.status_lbl.pack(anchor="w", padx=16, pady=(8, 2))

        self.progress_bar = ctk.CTkProgressBar(bot, height=8)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 8))

        btn_row = ctk.CTkFrame(bot, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_export = ctk.CTkButton(
            btn_row,
            text=tr.get("btn_start_export", "🚀 ចាប់ផ្តើម Export"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=32,
            width=170,
            command=self._start_export_process
        )
        self.btn_export.pack(side="right", padx=(8, 0))

        self.btn_cancel = ctk.CTkButton(
            btn_row,
            text="❌ បោះបង់",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            fg_color="#4B5563",
            hover_color="#374151",
            height=32,
            width=100,
            command=self.destroy
        )
        self.btn_cancel.pack(side="right")

    def _refresh_crop_status(self):
        vplayer = getattr(self.master_app, 'video_player', None)
        fliph = getattr(vplayer, 'flip_horizontal', False) if vplayer else False
        flipv = getattr(vplayer, 'flip_vertical', False) if vplayer else False
        cmode = getattr(vplayer, 'crop_mode', 'none') if vplayer else 'none'
        crop_parts = []
        if fliph: crop_parts.append("↔️ Flip H")
        if flipv: crop_parts.append("↕️ Flip V")
        if cmode != "none": crop_parts.append(f"✂️ Crop {cmode}")
        summary_txt = " | ".join(crop_parts) if crop_parts else "ដើម (គ្មាន Flip / Crop)"
        if hasattr(self, 'lbl_export_crop_status'):
            self.lbl_export_crop_status.configure(text=f"✂️ ទម្រង់វីដេអូ៖ {summary_txt}")

    def _browse_dest_path(self):
        cur = self.dest_entry.get().strip()
        init_d = os.path.dirname(cur) if cur else os.getcwd()
        init_f = os.path.basename(cur) if cur else "dubbed.mp4"
        chosen = filedialog.asksaveasfilename(
            initialdir=init_d,
            initialfile=init_f,
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("All Files", "*.*")],
            parent=self
        )
        if chosen:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, chosen)

    def _start_export_process(self):
        video_path = self.video_path
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("កំហុស", "មិនមានវីដេអូសម្រាប់ Export ទេ!", parent=self)
            return

        if not self.master_app.segments_data:
            messagebox.showerror("កំហុស", "មិនទាន់មានអត្ថបទសម្រាយរឿង / Subtitle នៅឡើយទេ! សូមចុច '🔍 ១. ស្កែន & បកប្រែ' ជាមុនសិន។", parent=self)
            return

        out_path = self.dest_entry.get().strip()
        if not out_path:
            messagebox.showerror("កំហុស", "សូមជ្រើសរើសទីតាំងរក្សាទុកវីដេអូ!", parent=self)
            return

        sel_label = self.quality_dropdown.get()
        matched = next((t for t in self.quality_tiers if t['label'] == sel_label), self.quality_tiers[0])
        target_h = None if matched.get('is_orig', False) else matched.get('height')

        pre_sel = self.preset_dropdown.get()
        if "CRF 18" in pre_sel:
            crf_val = 18
        elif "CRF 26" in pre_sel:
            crf_val = 26
        else:
            crf_val = 22

        # Sync all edited widget texts to segments_data on the UI thread before export
        for s in (self.master_app.segments_data or []):
            if 'widget' in s and hasattr(s['widget'], 'get'):
                try:
                    w_txt = s['widget'].get().strip()
                    if w_txt:
                        s['khmer'] = w_txt
                except Exception:
                    pass

        sub_sel = self.sub_mode_dropdown.get()
        burn_subs = ("Hardcode" in sub_sel or "ដុត" in sub_sel or "硬字幕" in sub_sel)
        skip_subs = ("មិនដាក់" in sub_sel or "No Subtitles" in sub_sel or "无字幕" in sub_sel)

        self.btn_export.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        self.progress_bar.set(0.1)
        self.status_lbl.configure(text="🚀 កំពុងរៀបចំ Export...", text_color="#38BDF8")

        def _do_merge_step():
            self.master_app._execute_merge_video(
                target_h=target_h,
                crf=crf_val,
                burn_subtitles=burn_subs,
                output_video_path=out_path,
                on_progress=lambda msg, p: self.after(0, lambda m=msg, pr=p: [
                    self.status_lbl.configure(text=m),
                    self.progress_bar.set(pr)
                ]),
                on_done=lambda final_p: self.after(0, lambda fp=final_p: self._on_export_complete(fp)),
                on_error=lambda err: self.after(0, lambda e=err: self._on_export_error(e))
            )

        def _run_flow():
            if not getattr(self.master_app, 'generated_master_audio', '') or not os.path.exists(self.master_app.generated_master_audio):
                self.after(0, lambda: self.status_lbl.configure(text="🎙️ កំពុងបង្កើតសំឡេងខ្មែរ TTS ជាមុនសិន..."))
                self.master_app._generate_voices_sync_worker(
                    on_progress=lambda msg, p: self.after(0, lambda m=msg, pr=p: [
                        self.status_lbl.configure(text=m),
                        self.progress_bar.set(0.1 + p * 0.4)
                    ]),
                    on_done=_do_merge_step,
                    on_error=lambda err: self.after(0, lambda e=err: self._on_export_error(e))
                )
            else:
                _do_merge_step()

        threading.Thread(target=_run_flow, daemon=True).start()

    def _on_export_complete(self, final_p):
        self.progress_bar.set(1.0)
        self.status_lbl.configure(text="🎉 Export វីដេអូបានសម្រេចជោគជ័យ!", text_color="#10B981")
        self.master_app._on_merge_success(final_p)
        self.destroy()

    def _on_export_error(self, err_msg):
        self.btn_export.configure(state="normal")
        self.btn_cancel.configure(state="normal")
        self.status_lbl.configure(text=f"❌ កំហុស: {err_msg}", text_color="#EF4444")
        messagebox.showerror("Export Error", f"កំហុសក្នុងការ Export វីដេអូ:\n{err_msg}", parent=self)

class DubbingTimeline(ctk.CTkFrame):
    """
    Professional Compact 3-Track Dubbing Timeline Component:
    - Active Blue Panel Border (#1473E6)
    - Transport Header & Sequence Tab (× 2 ≡)
    - Left Tool Strip (Selection, Razor)
    - Track Headers with target indicators (V1, A1, A2, Lock)
    - SMPTE Time Ruler with Yellow Render Bar
    - Track V1: Video Clip [V] with fx badge
    - Track A1: Khmer Dubbed Dialogue Clips with text preview
    - Track A2: Background Music (BGM) Track with waveform & volume
    - Blue Playhead with teardrop indicator
    - Right dB Peak Level Meters
    """
    def __init__(self, master, on_clip_click=None, on_seek=None, on_close=None, **kwargs):
        on_close = on_close or kwargs.pop('on_close', None)
        self.on_play = kwargs.pop('on_play', None)
        self.on_pause = kwargs.pop('on_pause', None)
        self.on_stop = kwargs.pop('on_stop', None)
        self.on_rewind = kwargs.pop('on_rewind', None)
        self.on_step_back = kwargs.pop('on_step_back', None)
        self.on_step_fwd = kwargs.pop('on_step_fwd', None)
        self.on_switch_audio_mode = kwargs.pop('on_switch_audio_mode', None)
        self.on_toggle_cc = kwargs.pop('on_toggle_cc', None)
        self.on_open_cc_settings = kwargs.pop('on_open_cc_settings', None)
        self.on_delete_dialogue = kwargs.pop('on_delete_dialogue', None)
        self.on_remove_video = kwargs.pop('on_remove_video', None)
        super().__init__(
            master, 
            fg_color="#12141A", 
            border_color="#2E333D", 
            border_width=1, 
            corner_radius=6, 
            **kwargs
        )
        self.on_clip_click = on_clip_click
        self.on_seek = on_seek
        self.on_close = on_close
        
        self.zoom = 1.0
        self.pixels_per_sec = 26.0
        self.duration_sec = 60.0
        self.current_time_sec = 0.0
        self.clips = []
        self.video_name = "2.mp4"
        self.fps = 25.0
        self.waveform_cache = []
        self.app_lang = "km"
        
        # Multi-Track Cutting & Tool Selection
        self.active_tool = "select"
        self.master_bg_vol = 0.3
        self.bgm_segments = [{'start': 0.0, 'end': 60.0, 'vol': 0.3}]
        self.video_segments = [{'start': 0.0, 'end': 60.0}]
        self.audio_segments = [{'start': 0.0, 'end': 60.0}]
        self.selected_track = "v1"
        self.selected_video_idx = 0
        self.selected_clip_idx = None
        self.selected_clips = set()
        self.selected_bgm_idx = None
        self._bgm_dialog = None
        self.copyright_segments = []

        
        # Real-Time Stereo VU Audio Meter & Resizing State
        self.db_meter_width = 38
        self.is_playing = False
        self.vu_l = 0.0
        self.vu_r = 0.0
        self.vu_peak_l = 0.0
        self.vu_peak_r = 0.0
        self._vu_timer_id = None
        
        self._build_top_header()
        self._build_main_body()
        self._init_default_waveform()
        self._setup_keyboard_shortcuts()
        self.redraw()

    def _on_close_clicked(self):
        if hasattr(self, 'on_close') and self.on_close:
            self.on_close()

    def set_play_state(self, is_playing: bool):
        """Update transport Play/Pause button appearance and animate audio meters."""
        self.is_playing = bool(is_playing)
        if hasattr(self, 'btn_tp_play'):
            if is_playing:
                self.btn_tp_play.configure(text="⏸", text_color="#F59E0B", fg_color="#262A34")
            else:
                self.btn_tp_play.configure(text="▶", text_color="#10B981", fg_color="#262A34")
        if not getattr(self, '_vu_timer_id', None):
            self._vu_tick()

    def _on_tp_rewind(self):
        if hasattr(self, 'on_rewind') and callable(self.on_rewind):
            self.on_rewind()
        else:
            self.set_current_time(0.0)
            if self.on_seek:
                self.on_seek(0.0)

    def _on_tp_step_back(self):
        if hasattr(self, 'on_step_back') and callable(self.on_step_back):
            self.on_step_back()
        else:
            t = max(0.0, self.current_time_sec - 1.0)
            self.set_current_time(t)
            if self.on_seek:
                self.on_seek(t)

    def _on_tp_play_toggle(self):
        if hasattr(self, 'on_play') and callable(self.on_play):
            self.on_play()

    def _on_tp_stop(self):
        if hasattr(self, 'on_stop') and callable(self.on_stop):
            self.on_stop()
        else:
            self.set_current_time(0.0)
            if self.on_seek:
                self.on_seek(0.0)

    def _on_tp_step_fwd(self):
        if hasattr(self, 'on_step_fwd') and callable(self.on_step_fwd):
            self.on_step_fwd()
        else:
            t = min(self.duration_sec, self.current_time_sec + 1.0)
            self.set_current_time(t)
            if self.on_seek:
                self.on_seek(t)

    def _on_tp_end(self):
        t = self.duration_sec
        self.set_current_time(t)
        if self.on_seek:
            self.on_seek(t)

    def set_language(self, lang):
        self.app_lang = lang
        tr = UI_STRINGS.get(lang, UI_STRINGS["km"])
        if hasattr(self, 'btn_split_bgm'):
            split_lbls = {
                "km": "✂️ Split BGM (កាត់ភ្លេង)",
                "en": "✂️ Split BGM",
                "zh": "✂️ 分割背景音乐 (Split)"
            }
            self.btn_split_bgm.configure(text=split_lbls.get(lang, "✂️ Split BGM"))
        if hasattr(self, 'btn_track_orig'):
            self.btn_track_orig.configure(text="🌐 " + tr.get("track_orig", "ស្តាប់ភាសាដើម (Original)"))
        if hasattr(self, 'btn_track_khmer'):
            self.btn_track_khmer.configure(text="🇰🇭 " + tr.get("track_khmer", "ស្តាប់ភាសាខ្មែរ (រួចរាល់)"))
        if hasattr(self, 'btn_cc'):
            is_on = ("ON" in self.btn_cc.cget("text") or "开启" in self.btn_cc.cget("text"))
            self.update_cc_button_state(is_on)
        self.redraw()

    def _on_toggle_cc(self):
        if hasattr(self, 'on_toggle_cc') and callable(self.on_toggle_cc):
            self.on_toggle_cc()

    def _open_cc_settings_dialog(self):
        try:
            if hasattr(self, 'on_open_cc_settings') and callable(self.on_open_cc_settings):
                self.on_open_cc_settings()
        except Exception as e:
            print(f"[Error opening CC settings] {e}")

    def update_cc_button_state(self, enabled: bool):
        if hasattr(self, 'btn_cc'):
            lang = getattr(self, 'app_lang', 'km')
            lbl_on = "💬 CC Subtitle: ON" if lang != "zh" else "💬 CC 字幕: 开启"
            lbl_off = "💬 CC Subtitle: OFF" if lang != "zh" else "💬 CC 字幕: 关闭"
            if enabled:
                self.btn_cc.configure(text=lbl_on, fg_color="#262A34", hover_color="#323846", border_color="#373D4B", border_width=1, text_color="#10B981")
            else:
                self.btn_cc.configure(text=lbl_off, fg_color="#262A34", hover_color="#323846", border_color="#373D4B", border_width=1, text_color="#9CA3AF")

    def _init_default_waveform(self):
        self.waveform_cache = []
        for i in range(450):
            base = abs(math.sin(i * 0.12) * math.cos(i * 0.04)) * 0.75
            burst = abs(math.sin(i * 0.55)) * 0.25 if (i % 35 > 12) else 0.08
            val = max(0.08, min(0.95, base + burst))
            self.waveform_cache.append(val)

    def _build_top_header(self):
        top_bar = ctk.CTkFrame(self, fg_color="#181A20", height=28, corner_radius=0)
        top_bar.pack(fill="x", side="top")
        
        # Sequence tab with clickable close button "✕"
        tab_box = ctk.CTkFrame(top_bar, fg_color="#1F232B", corner_radius=0, width=135, height=28)
        tab_box.pack(side="left")
        tab_box.pack_propagate(False)
        self.btn_close_seq = ctk.CTkButton(
            tab_box, 
            text="✕", 
            width=20, 
            height=20,
            fg_color="transparent",
            hover_color="#3F1B1E",
            text_color="#94A3B8",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._on_close_clicked
        )
        self.btn_close_seq.pack(side="left", padx=(4, 0))
        
        self.seq_tab_lbl = ctk.CTkLabel(
            tab_box, 
            text="Sequence 01  ≡", 
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#CBD5E1"
        )
        self.seq_tab_lbl.pack(side="left", padx=4)

        # Center Premiere Pro Transport Icons & Split Button
        center_tools = ctk.CTkFrame(top_bar, fg_color="transparent")
        center_tools.pack(side="left", expand=True)
        
        # Tools: Mark In / Mark Out
        ctk.CTkLabel(center_tools, text="▼", font=ctk.CTkFont(size=10), text_color="#64748B", width=14).pack(side="left", padx=1)
        ctk.CTkLabel(center_tools, text="{", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94A3B8", width=14).pack(side="left", padx=1)
        ctk.CTkLabel(center_tools, text="}", font=ctk.CTkFont(size=11, weight="bold"), text_color="#94A3B8", width=14).pack(side="left", padx=1)

        # Interactive Premiere Pro Transport Control Bar
        # 1. Rewind to beginning (⇤ / ពីដើម)
        self.btn_tp_rewind = ctk.CTkButton(
            center_tools,
            text="⇤",
            width=26,
            height=22,
            fg_color="transparent",
            hover_color="#262A34",
            text_color="#CBD5E1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_tp_rewind
        )
        self.btn_tp_rewind.pack(side="left", padx=1)

        # 2. Step Backward 1s (⯇ / ខាថយក្រោយ)
        self.btn_tp_step_back = ctk.CTkButton(
            center_tools,
            text="⯇",
            width=26,
            height=22,
            fg_color="transparent",
            hover_color="#262A34",
            text_color="#CBD5E1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_tp_step_back
        )
        self.btn_tp_step_back.pack(side="left", padx=1)

        # 3. Play / Pause Toggle (▶ / ⏸ ចាក់/ផ្អាក)
        self.btn_tp_play = ctk.CTkButton(
            center_tools,
            text="▶",
            width=30,
            height=22,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#10B981",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_tp_play_toggle
        )
        self.btn_tp_play.pack(side="left", padx=1)

        # 4. Stop Button (⏹ / ឈប់)
        self.btn_tp_stop = ctk.CTkButton(
            center_tools,
            text="⏹",
            width=26,
            height=22,
            fg_color="transparent",
            hover_color="#3F1B1E",
            text_color="#EF4444",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_tp_stop
        )
        self.btn_tp_stop.pack(side="left", padx=1)

        # 5. Step Forward 1s (⯈ / ខាទៅមុខ)
        self.btn_tp_step_fwd = ctk.CTkButton(
            center_tools,
            text="⯈",
            width=26,
            height=22,
            fg_color="transparent",
            hover_color="#262A34",
            text_color="#CBD5E1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_tp_step_fwd
        )
        self.btn_tp_step_fwd.pack(side="left", padx=1)

        # 6. Go to End (⇥ / ទៅចុង)
        self.btn_tp_end = ctk.CTkButton(
            center_tools,
            text="⇥",
            width=26,
            height=22,
            fg_color="transparent",
            hover_color="#262A34",
            text_color="#CBD5E1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_tp_end
        )
        self.btn_tp_end.pack(side="left", padx=1)

        ctk.CTkLabel(center_tools, text="📷", font=ctk.CTkFont(size=11), text_color="#64748B", width=18).pack(side="left", padx=1)
        ctk.CTkLabel(center_tools, text="🔲", font=ctk.CTkFont(size=11), text_color="#64748B", width=18).pack(side="left", padx=1)

        # Prominent Split Button (✂️ Split at Playhead)
        self.btn_split = ctk.CTkButton(
            center_tools,
            text="✂️ កាត់ (Split / S)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#E5E7EB",
            height=22,
            width=110,
            corner_radius=4,
            command=self.split_at_playhead
        )
        self.btn_split.pack(side="left", padx=(4, 2))
        self.btn_split_bgm = self.btn_split

        # Prominent Delete Button (🗑️ Delete Selected Cut Segment - Soft Red)
        self.btn_delete_clip = ctk.CTkButton(
            center_tools,
            text="🗑️ លុប (Del)",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            fg_color="#2E181A",
            hover_color="#3F1B1E",
            border_color="#7F1D1D",
            border_width=1,
            text_color="#EF4444",
            height=22,
            width=80,
            corner_radius=4,
            command=self.delete_selected_clip
        )
        self.btn_delete_clip.pack(side="left", padx=(2, 6))

        # Right Zoom controls & Duration Readout
        right_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        right_box.pack(side="right", padx=8)
        
        self.duration_display = ctk.CTkLabel(
            right_box,
            text="00:01:00:00",
            font=ctk.CTkFont(size=11, family="Consolas", weight="bold"),
            text_color="#94A3B8"
        )
        self.duration_display.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            right_box, text="-", width=22, height=18, font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#333333", hover_color="#444444", command=self.zoom_out
        ).pack(side="left", padx=2)
        
        self.zoom_badge = ctk.CTkLabel(right_box, text="100%", font=ctk.CTkFont(size=10), text_color="#A1A1AA", width=36)
        self.zoom_badge.pack(side="left")

        ctk.CTkButton(
            right_box, text="+", width=22, height=18, font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#333333", hover_color="#444444", command=self.zoom_in
        ).pack(side="left", padx=2)

    def _build_main_body(self):
        body = ctk.CTkFrame(self, fg_color="#12141A", corner_radius=0)
        body.pack(fill="both", expand=True)

        # 1. Left Tool Strip (~32px)
        self.tool_strip = tk.Canvas(body, width=32, bg="#181A20", highlightthickness=0)
        self.tool_strip.pack(side="left", fill="y")
        self.tool_strip.bind("<Button-1>", self._on_tool_click)
        self._draw_tool_strip()

        # 2. Track Header Column (~80px clean compact)
        self.track_headers = tk.Canvas(body, width=80, bg="#181A20", highlightthickness=0)
        self.track_headers.pack(side="left", fill="y")

        # 3. Far Right: Resizable Audio dB Meter
        self.db_meter = tk.Canvas(body, width=self.db_meter_width, bg="#12141A", highlightthickness=0)
        self.db_meter.pack(side="right", fill="y")
        self.db_meter.bind("<Configure>", lambda e: self._draw_db_meter())

        # Resizer Sash handle between timeline canvas and db_meter (Grip to drag left/right)
        self.db_resizer = tk.Frame(body, width=5, bg="#1F232B", cursor="sb_h_double_arrow")
        self.db_resizer.pack(side="right", fill="y")
        self.db_resizer.bind("<Button-1>", self._on_db_resize_start)
        self.db_resizer.bind("<B1-Motion>", self._on_db_resize_drag)
        self.db_resizer.bind("<Enter>", lambda e: self.db_resizer.config(bg="#10B981"))
        self.db_resizer.bind("<Leave>", lambda e: self.db_resizer.config(bg="#1F232B"))
        self._draw_db_meter()

        # 4. Center Timeline Canvas Container
        center_frame = ctk.CTkFrame(body, fg_color="#12141A", corner_radius=0)
        center_frame.pack(side="left", fill="both", expand=True)

        # Bottom Navigator Scrollbar
        self.nav_scroll = tk.Scrollbar(center_frame, orient="horizontal")
        self.nav_scroll.pack(side="bottom", fill="x")

        # Main Timeline Canvas (Studio Dark #0F1115)
        self.canvas = tk.Canvas(
            center_frame, bg="#0F1115", highlightthickness=0,
            xscrollcommand=self.nav_scroll.set,
            height=144
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.nav_scroll.config(command=self.canvas.xview)

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
        self.canvas.bind("<Button-2>", self._on_canvas_right_click)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.xview_scroll(int(-1 * (e.delta / 120)), "units"))
        self.canvas.bind("<Shift-MouseWheel>", lambda e: self.canvas.xview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _setup_keyboard_shortcuts(self):
        def _bind():
            try:
                root = self.winfo_toplevel()
                def _handle_key(event):
                    w = event.widget
                    w_class = ""
                    try:
                        w_class = w.winfo_class().lower()
                    except Exception:
                        pass
                    # If focused inside text/entry widget, do not intercept keys so user can type
                    if w_class in ("entry", "text", "ctkentry", "ctktextbox") or "entry" in str(w).lower() or "text" in str(w).lower():
                        return
                    k = event.keysym.lower()
                    if k in ('delete', 'backspace', 'kp_delete'):
                        self.delete_selected_clip()
                        return "break"
                    elif k == 's':
                        self.split_at_playhead()
                        return "break"
                    elif k == 'v':
                        self.set_active_tool("select")
                    elif k == 'c':
                        self.set_active_tool("razor")
                    elif k == 'a':
                        self.set_active_tool("track_forward")
                    elif k == 'space':
                        if hasattr(self, 'on_play') and callable(self.on_play):
                            self.on_play()
                            return "break"

                for key in ('v', 'V', 'c', 'C', 'a', 'A', 's', 'S', 'space'):
                    root.bind(f"<Key-{key}>", _handle_key, add="+")
                root.bind("<Delete>", _handle_key, add="+")
                root.bind("<BackSpace>", _handle_key, add="+")
                root.bind("<KP_Delete>", _handle_key, add="+")
                root.bind("<Control-k>", lambda e: (self.split_at_playhead(), "break")[1], add="+")
                root.bind("<Control-K>", lambda e: (self.split_at_playhead(), "break")[1], add="+")

                # Also bind directly on canvas and timeline container
                for b_target in (self.canvas, self):
                    b_target.bind("<Delete>", _handle_key)
                    b_target.bind("<BackSpace>", _handle_key)
                    b_target.bind("<KP_Delete>", _handle_key)
                    b_target.bind("<Key-s>", _handle_key)
                    b_target.bind("<Key-S>", _handle_key)
                    b_target.bind("<Key-c>", _handle_key)
                    b_target.bind("<Key-v>", _handle_key)
            except Exception as e:
                print(f"[Timeline] Shortcut bind error: {e}")

        self.after(120, _bind)

    def set_active_tool(self, tool_name: str):
        if tool_name in ("select", "razor"):
            self.active_tool = tool_name
        else:
            self.active_tool = "select"
            
        if self.active_tool == "razor":
            self.canvas.config(cursor="crosshair")
        else:
            self.canvas.config(cursor="")
            
        self._draw_tool_strip()

    def _draw_tool_strip(self):
        c = self.tool_strip
        c.delete("all")
        tools = [
            ("↖", self.active_tool == "select"),
            ("✂", self.active_tool == "razor"),
        ]
        y = 6
        for sym, active in tools:
            if active:
                fill_c = "#10B981"
                outl_c = "#34D399"
                c.create_rectangle(4, y, 28, y + 20, fill=fill_c, outline=outl_c)
                c.create_text(16, y + 10, text=sym, fill="#FFFFFF", font=("Segoe UI", 10, "bold"))
            else:
                c.create_rectangle(4, y, 28, y + 20, fill="#1E2128", outline="#2E333D")
                c.create_text(16, y + 10, text=sym, fill="#9CA3AF", font=("Segoe UI", 9))
            y += 24

    def _on_tool_click(self, event):
        y = event.y
        idx = (y - 6) // 24
        if idx == 0:
            self.set_active_tool("select")
        elif idx == 1:
            self.set_active_tool("razor")

    # --- Multi-Track Video & Audio Cutting Methods ---
    def split_video_at_time(self, split_t: float = None):
        """Split Track V1 video clip at specified time or current playhead."""
        if split_t is None:
            split_t = self.current_time_sec
        split_t = max(0.1, min(self.duration_sec - 0.1, round(split_t, 2)))
        new_idx = None
        for i, seg in enumerate(self.video_segments):
            if seg['start'] < split_t < seg['end']:
                if (split_t - seg['start'] >= 0.1) and (seg['end'] - split_t >= 0.1):
                    old_end = seg['end']
                    seg['end'] = split_t
                    self.video_segments.insert(i + 1, {'start': split_t, 'end': old_end})
                    new_idx = i + 1
                    break
        if new_idx is not None:
            self.selected_track = "v1"
            self.selected_video_idx = new_idx
            self.selected_clip_idx = None
            self.selected_clips.clear()
            self.selected_bgm_idx = None
        self.redraw()
        return new_idx

    def _get_video_segment_at_time(self, t: float):
        for i, vseg in enumerate(self.video_segments):
            if vseg['start'] <= t <= vseg['end']:
                return i
        return None

    def _get_dialogue_clip_at_time(self, t: float):
        for i, clip in enumerate(self.clips):
            if clip.get('start', 0.0) <= t <= clip.get('end', 0.0):
                return i
        return None

    def split_at_playhead(self):
        """Split currently selected track or all tracks at current playhead position."""
        t = self.current_time_sec
        if self.selected_track == "v1":
            self.split_video_at_time(t)
        elif self.selected_track == "a1":
            self.split_dialogue_at_time(t)
        elif self.selected_track == "a2":
            self.split_bgm_at_time(t)
        else:
            self.split_video_at_time(t)
            self.split_dialogue_at_time(t)
            self.split_bgm_at_time(t)
        self.redraw()

    def _delete_video_segment(self, idx: int):
        if not (0 <= idx < len(self.video_segments)):
            return
        if len(self.video_segments) > 1:
            del self.video_segments[idx]
            self.selected_video_idx = min(idx, len(self.video_segments) - 1) if self.video_segments else None
            self.selected_track = "v1"
            self.redraw()
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        else:
            top = self.winfo_toplevel()
            if messagebox.askyesno("ដកវីដេអូ", "តើអ្នកចង់ដកវីដេអូចេញពីកម្មវិធីមែនទេ? (Remove video?)", parent=top):
                if hasattr(self, 'on_remove_video') and callable(self.on_remove_video):
                    self.on_remove_video()

    def _delete_dialogue_clip(self, idx: int):
        if not (0 <= idx < len(self.clips)):
            return
        del self.clips[idx]
        self.selected_clip_idx = min(idx, len(self.clips) - 1) if self.clips else None
        self.selected_clips.clear()
        if self.selected_clip_idx is not None:
            self.selected_clips.add(self.selected_clip_idx)
        self.selected_track = "a1"
        if hasattr(self, 'on_delete_dialogue') and callable(self.on_delete_dialogue):
            self.on_delete_dialogue(idx)
        self.redraw()
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def _delete_bgm_segment(self, idx: int):
        if not (0 <= idx < len(self.bgm_segments)):
            return
        if len(self.bgm_segments) > 1:
            if idx > 0:
                self.bgm_segments[idx - 1]['end'] = self.bgm_segments[idx]['end']
                self.bgm_segments.pop(idx)
                self.selected_bgm_idx = idx - 1
            elif idx < len(self.bgm_segments) - 1:
                self.bgm_segments[idx + 1]['start'] = self.bgm_segments[idx]['start']
                self.bgm_segments.pop(idx)
                self.selected_bgm_idx = 0
        else:
            self.bgm_segments[0]['vol'] = 0.0
        self.selected_track = "a2"
        self.redraw()
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

    def delete_selected_clip(self):
        """Delete whichever segment or clip is currently selected (or under playhead)."""
        if self.selected_track == "v1" and self.selected_video_idx is not None:
            self._delete_video_segment(self.selected_video_idx)
        elif self.selected_track == "a1" and (getattr(self, 'selected_clip_idx', None) is not None or self.selected_clips):
            c_idx = self.selected_clip_idx if getattr(self, 'selected_clip_idx', None) is not None else (next(iter(self.selected_clips)) if self.selected_clips else None)
            if c_idx is not None:
                self._delete_dialogue_clip(c_idx)
        elif self.selected_track == "a2" and self.selected_bgm_idx is not None:
            self._delete_bgm_segment(self.selected_bgm_idx)
        else:
            v_idx = self._get_video_segment_at_time(self.current_time_sec)
            if v_idx is not None and len(self.video_segments) > 1:
                self._delete_video_segment(v_idx)
            else:
                a_idx = self._get_dialogue_clip_at_time(self.current_time_sec)
                if a_idx is not None:
                    self._delete_dialogue_clip(a_idx)
                elif v_idx is not None:
                    self._delete_video_segment(v_idx)

    def _reset_video_segments(self):
        self.video_segments = [{'start': 0.0, 'end': self.duration_sec}]
        self.selected_track = "v1"
        self.selected_video_idx = 0
        self.redraw()

    def split_audio_at_time(self, split_t: float = None):
        """Split Track A1 audio clip at specified time or current playhead."""
        if split_t is None:
            split_t = self.current_time_sec
        split_t = max(0.2, min(self.duration_sec - 0.2, round(split_t, 2)))
        for i, seg in enumerate(self.audio_segments):
            if seg['start'] < split_t < seg['end']:
                if (split_t - seg['start'] >= 0.2) and (seg['end'] - split_t >= 0.2):
                    old_end = seg['end']
                    seg['end'] = split_t
                    self.audio_segments.insert(i + 1, {'start': split_t, 'end': old_end})
                    break
        self.redraw()

    def split_dialogue_at_time(self, split_t: float = None):
        """Split Track A2 Khmer speech / dialogue clip at specified time or playhead."""
        if split_t is None:
            split_t = self.current_time_sec
        split_t = max(0.1, min(self.duration_sec - 0.1, round(split_t, 2)))
        target_idx = None
        for i, clip in enumerate(self.clips):
            st = clip.get('start', 0.0)
            et = clip.get('end', 0.0)
            if st < split_t < et:
                if (split_t - st >= 0.2) and (et - split_t >= 0.2):
                    target_idx = i
                    break
        if target_idx is not None:
            old_clip = self.clips[target_idx]
            old_end = old_clip['end']
            old_text = old_clip.get('khmer', old_clip.get('orig', ''))
            if hasattr(old_clip.get('widget'), 'get'):
                try:
                    old_text = old_clip['widget'].get()
                except Exception:
                    pass
            words = old_text.split()
            if len(words) > 1:
                mid = len(words) // 2
                t1 = " ".join(words[:mid])
                t2 = " ".join(words[mid:])
            else:
                t1 = old_text
                t2 = old_text
            old_clip['end'] = split_t
            if hasattr(old_clip.get('widget'), 'delete') and hasattr(old_clip.get('widget'), 'insert'):
                try:
                    old_clip['widget'].delete(0, 'end')
                    old_clip['widget'].insert(0, t1)
                except Exception:
                    pass
            new_clip = dict(old_clip)
            new_clip['start'] = split_t
            new_clip['end'] = old_end
            new_clip['khmer'] = t2
            new_clip['orig'] = old_clip.get('orig', '')
            self.clips.insert(target_idx + 1, new_clip)
            if hasattr(self, 'on_split_clip') and self.on_split_clip:
                try:
                    self.on_split_clip(target_idx, split_t)
                except Exception:
                    pass
        self.redraw()

    def select_forward_from_time(self, select_t: float):
        """Select all clips from select_t forward (Track Select Forward Tool - A)."""
        self.selected_clips.clear()
        for i, clip in enumerate(self.clips):
            if clip.get('start', 0.0) >= select_t - 0.08:
                self.selected_clips.add(i)
        self.redraw()

    # --- BGM Multi-Segment Editing Methods ---
    def set_default_bgm_volume(self, vol: float):
        self.master_bg_vol = max(0.0, min(2.5, round(vol, 2)))
        if len(self.bgm_segments) <= 1:
            self.bgm_segments = [{'start': 0.0, 'end': self.duration_sec, 'vol': self.master_bg_vol}]
            self.redraw()

    def split_bgm_at_time(self, split_t: float = None):
        if split_t is None:
            split_t = self.current_time_sec
        split_t = max(0.2, min(self.duration_sec - 0.2, round(split_t, 2)))
        
        target_idx = None
        for i, seg in enumerate(self.bgm_segments):
            if seg['start'] < split_t < seg['end']:
                if (split_t - seg['start'] >= 0.2) and (seg['end'] - split_t >= 0.2):
                    target_idx = i
                    break
        if target_idx is None:
            return
            
        old_seg = self.bgm_segments[target_idx]
        old_end = old_seg['end']
        old_vol = old_seg.get('vol', self.master_bg_vol)
        
        old_seg['end'] = split_t
        new_seg = {'start': split_t, 'end': old_end, 'vol': old_vol}
        self.bgm_segments.insert(target_idx + 1, new_seg)
        self.selected_bgm_idx = target_idx + 1
        self.redraw()

    def merge_bgm_segment_with_next(self, idx: int):
        if 0 <= idx < len(self.bgm_segments) - 1:
            self.bgm_segments[idx]['end'] = self.bgm_segments[idx + 1]['end']
            self.bgm_segments.pop(idx + 1)
            self.selected_bgm_idx = min(idx, len(self.bgm_segments) - 1)
            self.redraw()

    def set_bgm_segment_volume(self, idx: int, vol: float):
        if 0 <= idx < len(self.bgm_segments):
            self.bgm_segments[idx]['vol'] = max(0.0, min(2.5, round(vol, 2)))
            self.redraw()

    def reset_bgm_segments(self):
        self.bgm_segments = [{'start': 0.0, 'end': self.duration_sec, 'vol': self.master_bg_vol}]
        self.selected_bgm_idx = 0
        self.redraw()

    def get_bgm_segments(self):
        return [dict(s) for s in self.bgm_segments]

    def open_bgm_volume_dialog(self, seg_idx: int = None):
        if seg_idx is None:
            seg_idx = self.selected_bgm_idx
        if hasattr(self, '_bgm_dialog') and self._bgm_dialog and self._bgm_dialog.winfo_exists():
            try:
                self._bgm_dialog.destroy()
            except Exception:
                pass
        self._bgm_dialog = BGMVolumeDialog(self, seg_idx)

    def _get_bgm_segment_at_time(self, t: float):
        for idx, seg in enumerate(self.bgm_segments):
            if seg['start'] <= t <= seg['end']:
                return idx
        if self.bgm_segments:
            return min(len(self.bgm_segments) - 1, max(0, len(self.bgm_segments) - 1))
        return None

    def _show_bgm_context_menu(self, event):
        canvas_x = self.canvas.canvasx(event.x)
        pps = self.pixels_per_sec * self.zoom
        t = max(0.0, min(self.duration_sec, canvas_x / pps))
        idx = self._get_bgm_segment_at_time(t)
        if idx is None:
            return
        seg = self.bgm_segments[idx]
        self.selected_bgm_idx = idx
        self.redraw()
        
        menu = tk.Menu(self, tearoff=0, bg="#1E1E2E", fg="#F8FAFC", activebackground="#7C3AED", activeforeground="#FFFFFF", font=("Segoe UI", 9))
        
        start_tc = format_smpte(seg['start'], self.fps)
        end_tc = format_smpte(seg['end'], self.fps)
        cur_pct = int(round(seg.get('vol', self.master_bg_vol) * 100))
        
        menu.add_command(
            label=f"🎵 កង់ទី #{idx+1} ({start_tc} - {end_tc}) [បច្ចុប្បន្ន: {cur_pct}%]",
            state="disabled"
        )
        menu.add_separator()
        
        presets = [
            ("🔊 សំឡេងខ្លាំងបំផុត (200%)", 2.0),
            ("🔊 សំឡេងខ្លាំង (150%)", 1.5),
            ("🔊 សំឡេងពេញកម្រិតដើម (100%)", 1.0),
            ("🔉 សំឡេងមធ្យម (60%)", 0.6),
            ("🔉 សំឡេងល្មម (30%)", 0.3),
            ("🔈 សំឡេងតិច / Ducked (15%)", 0.15),
            ("🔇 បិទសំឡេងទាំងស្រុង (0% Mute)", 0.0),
        ]
        for lbl, v in presets:
            menu.add_command(label=lbl, command=lambda val=v, i=idx: self.set_bgm_segment_volume(i, val))
            
        menu.add_separator()
        menu.add_command(label="🎚️ កែសម្រួលតាមចិត្ត (Slider % Dialog)...", command=lambda i=idx: self.open_bgm_volume_dialog(i))
        menu.add_command(label=f"✂️ កាត់ត្រង់ទីនេះ ({format_smpte(t, self.fps)})", command=lambda sp_t=t: self.split_bgm_at_time(sp_t))
        if idx < len(self.bgm_segments) - 1:
            menu.add_command(label="🗑️ បញ្ចូលជាមួយកង់បន្ទាប់ (Merge with Next)", command=lambda i=idx: self.merge_bgm_segment_with_next(i))
        menu.add_command(label="🔄 កំណត់ឡើងវិញទាំងអស់ (Reset All BGM)", command=self.reset_bgm_segments)
        
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_canvas_right_click(self, event):
        self.canvas.focus_set()
        canvas_x = self.canvas.canvasx(event.x)
        pps = self.pixels_per_sec * self.zoom
        self.current_time_sec = max(0.0, min(self.duration_sec, canvas_x / pps))
        self.set_current_time(self.current_time_sec)
        
        if 36 <= event.y <= 72: # Track V1: Video Track
            v_idx = self._get_video_segment_at_time(self.current_time_sec)
            if v_idx is not None:
                self.selected_track = "v1"
                self.selected_video_idx = v_idx
                self.selected_clip_idx = None
                self.selected_clips.clear()
                self.selected_bgm_idx = None
                self.redraw()
            self._show_video_context_menu(event)
        elif 72 <= event.y <= 108: # Track A1: Dialogue Track
            c_idx = self._get_dialogue_clip_at_time(self.current_time_sec)
            if c_idx is not None:
                self.selected_track = "a1"
                self.selected_video_idx = None
                self.selected_clip_idx = c_idx
                self.selected_clips = {c_idx}
                self.selected_bgm_idx = None
                self.redraw()
            self._show_dialogue_context_menu(event)
        elif 108 <= event.y <= 144: # Track A2: BGM Track
            self._show_bgm_context_menu(event)

    def _show_video_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg="#202024", fg="#E2E8F0", activebackground="#2563EB", activeforeground="#FFFFFF")
        menu.add_command(label="✂️ កាត់វីដេអូត្រង់ទីនេះ (Split / S)", command=self.split_at_playhead)
        menu.add_command(label="🗑️ លុបកង់វីដេអូនេះ (Delete - Del)", command=self.delete_selected_clip)
        menu.add_separator()
        menu.add_command(label="🔄 កំណត់វីដេអូឡើងវិញទាំងអស់ (Reset Segments)", command=self._reset_video_segments)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _show_dialogue_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0, bg="#202024", fg="#E2E8F0", activebackground="#2563EB", activeforeground="#FFFFFF")
        menu.add_command(label="✂️ កាត់ល្បះត្រង់ទីនេះ (Split)", command=self.split_at_playhead)
        menu.add_command(label="🗑️ លុបល្បះនេះ (Delete - Del)", command=self.delete_selected_clip)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_db_resize_start(self, event):
        self._drag_db_x = event.x_root
        self._drag_db_w = self.db_meter_width

    def _on_db_resize_drag(self, event):
        dx = self._drag_db_x - event.x_root
        new_w = max(28, min(140, self._drag_db_w + dx))
        if new_w != self.db_meter_width:
            self.db_meter_width = new_w
            self.db_meter.config(width=new_w)
            self._draw_db_meter()

    def _vu_tick(self):
        if not self.is_playing:
            # Smooth decay down to zero when playback stops
            if self.vu_l > 0.02 or self.vu_r > 0.02:
                self.vu_l = max(0.0, self.vu_l * 0.72 - 0.02)
                self.vu_r = max(0.0, self.vu_r * 0.72 - 0.02)
                self.vu_peak_l = max(0.0, self.vu_peak_l * 0.88 - 0.01)
                self.vu_peak_r = max(0.0, self.vu_peak_r * 0.88 - 0.01)
                self._draw_db_meter()
                self._vu_timer_id = self.after(35, self._vu_tick)
            else:
                self.vu_l = 0.0
                self.vu_r = 0.0
                self.vu_peak_l = 0.0
                self.vu_peak_r = 0.0
                self._draw_db_meter()
                self._vu_timer_id = None
            return

        # Active Playback: Dynamic bounce tracking actual video audio rhythm
        base_amp = 0.55
        if self.waveform_cache and self.duration_sec > 0:
            idx = int((self.current_time_sec / self.duration_sec) * len(self.waveform_cache))
            idx = max(0, min(len(self.waveform_cache) - 1, idx))
            base_amp = self.waveform_cache[idx]

        t = time.time()
        mod1 = 0.85 + 0.28 * math.sin(t * 30.0) + 0.14 * math.cos(t * 13.0)
        mod2 = 0.85 + 0.28 * math.cos(t * 27.0) + 0.14 * math.sin(t * 17.0)

        target_l = max(0.06, min(0.96, base_amp * mod1))
        target_r = max(0.06, min(0.96, base_amp * mod2))

        # Fast attack, smooth decay
        if target_l > self.vu_l:
            self.vu_l = target_l
        else:
            self.vu_l = self.vu_l * 0.68 + target_l * 0.32

        if target_r > self.vu_r:
            self.vu_r = target_r
        else:
            self.vu_r = self.vu_r * 0.68 + target_r * 0.32

        # Peak hold indicators
        if self.vu_l > self.vu_peak_l:
            self.vu_peak_l = self.vu_l
        else:
            self.vu_peak_l = max(self.vu_l, self.vu_peak_l * 0.96)

        if self.vu_r > self.vu_peak_r:
            self.vu_peak_r = self.vu_r
        else:
            self.vu_peak_r = max(self.vu_r, self.vu_peak_r * 0.96)

        self._draw_db_meter()
        self._vu_timer_id = self.after(35, self._vu_tick)

    def _draw_db_meter(self):
        c = self.db_meter
        c.delete("all")
        w = max(28, self.db_meter_width)
        h_actual = self.db_meter.winfo_height()
        ch = max(144, h_actual if h_actual > 50 else 144)
        
        # Left separator line
        c.create_line(0, 0, 0, ch, fill="#2D2D2D", width=1)
        
        # Geometry for meter bars
        y_top = 10
        y_bot = max(y_top + 60, min(126, ch - 18))
        meter_h = max(50, y_bot - y_top)
        
        scale_marks = [
            ("0", 0.00, "#EF4444"),    # Peak overload (Red)
            ("-3", 0.14, "#F59E0B"),   # High level (Amber)
            ("-6", 0.28, "#FACC15"),   # Warm level (Yellow)
            ("-12", 0.48, "#10B981"),  # Nominal speech level (Green)
            ("-18", 0.64, "#10B981"),
            ("-24", 0.80, "#059669"),
            ("-∞", 1.00, "#64748B")    # Silence
        ]
        
        show_full_labels = (w >= 45)
        text_w = 20 if show_full_labels else 14
        
        # Draw scale ticks & text
        for lbl, ratio, col in scale_marks:
            y = int(y_top + meter_h * ratio)
            c.create_line(w - text_w - 4, y, w - text_w, y, fill="#4B5563", width=1)
            if show_full_labels or lbl in ("0", "-12", "-∞"):
                c.create_text(w - (text_w // 2), y, text=lbl, fill=col if lbl in ("0", "-∞") else "#94A3B8", font=("Segoe UI", 7), anchor="center")

        # Calculate Bar Widths (Left & Right Channel)
        bar_area_w = max(10, w - text_w - 6)
        bar_w = max(3, (bar_area_w - 4) // 2)
        
        bx_l = 4
        bx_r = bx_l + bar_w + 3
        
        # Background slot for L and R
        c.create_rectangle(bx_l, y_top, bx_l + bar_w, y_bot, fill="#0D0D11", outline="#1F2937")
        c.create_rectangle(bx_r, y_top, bx_r + bar_w, y_bot, fill="#0D0D11", outline="#1F2937")

        # Thresholds in Y
        y_red = int(y_top + meter_h * 0.14)     # Above -3dB is Red
        y_yellow = int(y_top + meter_h * 0.48)  # Between -12dB and -3dB is Yellow
        
        def _draw_channel_fill(bx, level, peak_val):
            if level <= 0.01:
                return
            fill_top = max(y_top, int(y_bot - meter_h * level))
            
            # 1. Green section
            g_top = max(y_yellow, fill_top)
            if y_bot > g_top:
                c.create_rectangle(bx + 1, g_top, bx + bar_w - 1, y_bot, fill="#10B981", outline="")
                
            # 2. Yellow section
            if fill_top < y_yellow:
                y_sec_top = max(y_red, fill_top)
                c.create_rectangle(bx + 1, y_sec_top, bx + bar_w - 1, y_yellow, fill="#FACC15", outline="")
                
            # 3. Red section
            if fill_top < y_red:
                c.create_rectangle(bx + 1, fill_top, bx + bar_w - 1, y_red, fill="#EF4444", outline="")
                
            # 4. Peak hold tick
            if peak_val > 0.03:
                py = max(y_top, int(y_bot - meter_h * peak_val))
                p_col = "#EF4444" if py < y_red else ("#FACC15" if py < y_yellow else "#FFFFFF")
                c.create_line(bx, py, bx + bar_w, py, fill=p_col, width=1.5)

        _draw_channel_fill(bx_l, self.vu_l, self.vu_peak_l)
        _draw_channel_fill(bx_r, self.vu_r, self.vu_peak_r)

        # L and R channel labels at bottom
        c.create_text(bx_l + bar_w // 2, y_bot + 8, text="L", fill="#64748B", font=("Segoe UI", 7, "bold"))
        c.create_text(bx_r + bar_w // 2, y_bot + 8, text="R", fill="#64748B", font=("Segoe UI", 7, "bold"))

    def _draw_track_headers(self):
        c = self.track_headers
        c.delete("all")
        w = 80
        
        # 1. Top SMPTE Timecode Display Box (Height: 0 to 36 matching ruler height)
        c.create_rectangle(0, 0, w, 36, fill="#12141A", outline="#2E333D")
        time_str = format_smpte(self.current_time_sec, self.fps)
        c.create_text(w // 2, 18, text=time_str, fill="#10B981", font=("Consolas", 9, "bold"), anchor="center")

        # 2. Track V1 (Video Clip): y=36 to 72 (height 36) - Studio Slate
        c.create_rectangle(0, 36, w, 72, fill="#181A20", outline="#2E333D")
        c.create_text(13, 54, text="🔒", fill="#64748B", font=("Segoe UI", 8))
        c.create_rectangle(26, 42, w - 8, 66, fill="#1E293B", outline="#334155")
        c.create_text(26 + (w - 8 - 26) // 2, 54, text="V1", fill="#93C5FD", font=("Segoe UI", 9, "bold"))

        # 3. Track A1 (Translated Audio / Dubbed Track): y=72 to 108 (height 36) - Emerald Accent
        c.create_rectangle(0, 72, w, 108, fill="#181A20", outline="#2E333D")
        c.create_text(13, 90, text="🔒", fill="#64748B", font=("Segoe UI", 8))
        c.create_rectangle(26, 78, w - 8, 102, fill="#162E26", outline="#234A38")
        c.create_text(26 + (w - 8 - 26) // 2, 90, text="A1", fill="#6EE7B7", font=("Segoe UI", 9, "bold"))

        # 4. Track A2 (BGM Track): y=108 to 144 (height 36) - Studio Dark Charcoal
        c.create_rectangle(0, 108, w, 144, fill="#181A20", outline="#2E333D")
        c.create_text(13, 126, text="🔒", fill="#64748B", font=("Segoe UI", 8))
        c.create_rectangle(26, 114, w - 8, 138, fill="#22252E", outline="#373D4B")
        c.create_text(26 + (w - 8 - 26) // 2, 126, text="A2", fill="#D1D5DB", font=("Segoe UI", 9, "bold"))

    def load_audio_waveform(self, wav_path: str):
        """Extract and display authentic waveform peaks from the video's audio."""
        if not wav_path or not os.path.exists(wav_path):
            return
        def _read():
            try:
                import wave, struct
                with wave.open(wav_path, 'rb') as wf:
                    n_frames = wf.getnframes()
                    if n_frames <= 0:
                        return
                    channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    chunk_size = max(1, n_frames // 450)
                    peaks = []
                    for _ in range(450):
                        raw_data = wf.readframes(chunk_size)
                        if not raw_data:
                            break
                        if sampwidth == 2:
                            fmt = f"{len(raw_data)//2}h"
                            samples = struct.unpack(fmt, raw_data)
                            max_val = max([abs(s) for s in samples[::channels]]) / 32768.0
                            peaks.append(min(1.0, max_val))
                    if peaks:
                        self.waveform_cache = peaks
                        self.after(0, self.redraw)
            except Exception as e:
                print(f"[Timeline] Waveform read error: {e}")
        threading.Thread(target=_read, daemon=True).start()

    def set_video_name(self, filename: str):
        if filename:
            self.video_name = os.path.basename(filename)
            if hasattr(self, 'seq_tab_lbl'):
                self.seq_tab_lbl.configure(text=f"✕  {self.video_name[:12]}  ≡")
            self.redraw()
        else:
            self.video_name = ""
            if hasattr(self, 'seq_tab_lbl'):
                self.seq_tab_lbl.configure(text="✕  Sequence 01  ≡")
            self.redraw()

    def redraw(self):
        self._draw_track_headers()
        self.canvas.delete("all")
        
        pps = self.pixels_per_sec * self.zoom
        total_width = max(1100, int(self.duration_sec * pps) + 160)
        ch = max(144, self.canvas.winfo_height())
        self.canvas.config(scrollregion=(0, 0, total_width, max(144, ch)))
        
        # 1. Studio Time Ruler (Height: 0 to 36)
        self.canvas.create_rectangle(0, 0, total_width, 36, fill="#181A20", outline="")
        self.canvas.create_line(0, 36, total_width, 36, fill="#2E333D", width=1)
        
        step_sec = 5 if self.zoom >= 1.5 else (15 if self.zoom >= 0.8 else 30)
        
        for sec in range(0, int(self.duration_sec) + 30, step_sec):
            x = int(sec * pps)
            tc = format_smpte(sec, self.fps)
            self.canvas.create_text(x + 2, 12, text=tc, fill="#9CA3AF", font=("Consolas", 8), anchor="w")
            self.canvas.create_line(x, 22, x, 33, fill="#475569", width=1)
            sub_step = max(1, step_sec // 5)
            for sub in range(1, 5):
                sub_sec = sec + sub * sub_step
                sub_x = int(sub_sec * pps)
                if sub_x < total_width:
                    self.canvas.create_line(sub_x, 27, sub_x, 33, fill="#334155", width=1)

        # Emerald Render Bar (Height: 34 to 36)
        vid_w = int(self.duration_sec * pps)
        self.canvas.create_rectangle(0, 34, vid_w, 36, fill="#10B981", outline="")

        # 2. Track V1: Video Clip [V] (Height: 36 to 72)
        self.canvas.create_rectangle(0, 36, total_width, 72, fill="#12141A", outline="#232730")
        if vid_w > 0:
            for i, vseg in enumerate(self.video_segments):
                vx1 = int(vseg['start'] * pps)
                vx2 = min(vid_w, int(vseg['end'] * pps))
                vw = vx2 - vx1
                if vw <= 1:
                    continue
                is_selected = (self.selected_track == "v1" and self.selected_video_idx == i)
                seg_tag = f"vseg_{i}"
                v_fill = "#24334A" if is_selected else "#1E293B"
                v_outline = "#FACC15" if is_selected else "#3B82F6"
                v_w = 2.0 if is_selected else 1
                
                # Video Clip Body
                self.canvas.create_rectangle(vx1, 37, vx2, 71, fill=v_fill, outline=v_outline, width=v_w, tags=(seg_tag, "vclip"))
                if is_selected:
                    self.canvas.create_rectangle(vx1 + 1, 37, vx2 - 1, 40, fill="#FACC15", outline="", tags=(seg_tag, "vclip"))
                if i > 0:
                    self.canvas.create_line(vx1, 36, vx1, 72, fill="#FFFFFF", width=2)
                # fx Badge
                if vw >= 28:
                    fx_bg = "#1E3A8A" if is_selected else "#172554"
                    self.canvas.create_rectangle(vx1 + 4, 41, vx1 + 20, 55, fill=fx_bg, outline="#3B82F6" if is_selected else "#1E3A8A", tags=(seg_tag, "vclip"))
                    self.canvas.create_text(vx1 + 12, 48, text="fx", fill="#FFFFFF" if is_selected else "#93C5FD", font=("Segoe UI", 7, "bold"), tags=(seg_tag, "vclip"))
                # Video Title
                v_title = f"{self.video_name} [V]" + (f" #{i+1}" if len(self.video_segments) > 1 else "")
                if vw >= 55:
                    self.canvas.create_text(vx1 + 24, 48, text=v_title, fill="#FFFFFF", font=("Segoe UI", 9, "bold"), anchor="w", tags=(seg_tag, "vclip"))
                # Top-right corner handle cut
                self.canvas.create_polygon(vx2 - 6, 37, vx2, 37, vx2, 43, fill="#FACC15" if is_selected else "#3B82F6", tags=(seg_tag, "vclip"))

        # 3. Track A1: Khmer Dubbed Speech Clips (Height: 72 to 108)
        self.canvas.create_rectangle(0, 72, total_width, 108, fill="#12141A", outline="#232730")
        if not self.clips:
            p_text = "🎙️ A1 Dubbed Track: " + ("ល្បះបកប្រែជាភាសាខ្មែរនឹងបង្ហាញនៅទីនេះ" if self.app_lang == "km" else ("Dubbed speech clips will appear here" if self.app_lang == "en" else "配音片段将显示在此处"))
            self.canvas.create_text(
                10, 90, 
                text=p_text, 
                fill="#64748B", 
                font=(KHMER_FONT_NAME, 8), 
                anchor="w"
            )
        else:
            for idx, clip in enumerate(self.clips):
                st = clip.get('start', 0)
                et = clip.get('end', st + 1)
                x1 = int(st * pps)
                x2 = max(x1 + 30, int(et * pps))
                
                v_info = clip.get('gender', 'male')
                if isinstance(clip.get('voice_widget'), object) and hasattr(clip.get('voice_widget'), 'get'):
                    try:
                        v_info = clip['voice_widget'].get()
                    except Exception:
                        pass
                is_fem = ("ស្រី" in str(v_info) or "Female" in str(v_info) or "女" in str(v_info) or str(v_info) == "female")
                is_selected = (self.selected_track == "a1" and (idx == getattr(self, 'selected_clip_idx', None) or idx in self.selected_clips))
                clip_fill = "#1E3A34" if is_fem else "#172F29"
                clip_border = "#FACC15" if is_selected else "#10B981"
                b_width = 2.0 if is_selected else 1
                tag = f"clip_{idx}"
                
                self.canvas.create_rectangle(x1, 73, x2, 107, fill=clip_fill, outline=clip_border, width=b_width, tags=(tag, "clip"))
                # fx badge
                self.canvas.create_rectangle(x1 + 3, 76, x1 + 17, 88, fill="#064E3B", outline="")
                self.canvas.create_text(x1 + 10, 82, text="fx", fill="#6EE7B7", font=("Segoe UI", 6, "bold"), tags=(tag, "clip"))
                
                txt_src = clip.get('khmer', clip.get('orig', ''))
                if hasattr(clip.get('widget'), 'get'):
                    try:
                        txt_src = clip['widget'].get()
                    except Exception:
                        pass
                c_text = f"#{idx+1} {txt_src}"
                if len(c_text) > 28:
                    c_text = c_text[:26] + "..."
                self.canvas.create_text(x1 + 22, 90, text=c_text, fill="#E5E7EB", font=(KHMER_FONT_NAME, 8, "bold"), anchor="w", tags=(tag, "clip"))

        # 4. Track A2: Background Music (BGM) Track (Height: 108 to 144)
        self.canvas.create_rectangle(0, 108, total_width, 144, fill="#12141A", outline="#232730")
        
        if not self.bgm_segments:
            self.bgm_segments = [{'start': 0.0, 'end': self.duration_sec, 'vol': self.master_bg_vol}]
            
        for idx, seg in enumerate(self.bgm_segments):
            s_t = seg.get('start', 0.0)
            e_t = min(self.duration_sec, seg.get('end', self.duration_sec))
            vol = seg.get('vol', self.master_bg_vol)
            x1 = int(s_t * pps)
            x2 = int(e_t * pps)
            w = x2 - x1
            if w <= 1:
                continue
                
            seg_tag = f"bgm_seg_{idx}"
            is_selected = (self.selected_track == "a2" and idx == self.selected_bgm_idx)
            
            # Segment Body (Studio Dark Charcoal)
            fill_color = "#242A36" if is_selected else "#1A1E26"
            outline_color = "#FACC15" if is_selected else "#2E333D"
            self.canvas.create_rectangle(x1, 109, x2, 143, fill=fill_color, outline=outline_color, width=2.0 if is_selected else 1, tags=(seg_tag, "bgm_seg"))
            
            # Cut Separator lines at clip boundaries
            if idx > 0:
                self.canvas.create_line(x1, 108, x1, 144, fill="#374151", width=1.5, tags=(seg_tag, "bgm_seg"))
            if idx < len(self.bgm_segments) - 1:
                self.canvas.create_line(x2, 108, x2, 144, fill="#374151", width=1.5, tags=(seg_tag, "bgm_seg"))
                
            # fx Badge
            if w >= 36:
                self.canvas.create_rectangle(x1 + 3, 112, x1 + 19, 126, fill="#1F232B", outline="#373D4B", tags=(seg_tag, "bgm_seg"))
                self.canvas.create_text(x1 + 11, 119, text="fx", fill="#9CA3AF", font=("Segoe UI", 7, "bold"), tags=(seg_tag, "bgm_seg"))
                
            # Title & Volume Status Badge
            vol_pct = int(round(vol * 100))
            if vol_pct == 0:
                badge = "🔇 Mute (0%)"
                badge_col = "#6B7280"
            elif vol_pct >= 100:
                badge = f"🔊 {vol_pct}%"
                badge_col = "#10B981"
            elif vol_pct <= 20:
                badge = f"🔈 {vol_pct}%"
                badge_col = "#9CA3AF"
            else:
                badge = f"🔉 {vol_pct}%"
                badge_col = "#D1D5DB"
                
            title_text = f"🎵 BGM #{idx+1} [{badge}]"
            text_x = x1 + 23 if w >= 36 else x1 + 4
            
            if w >= 50:
                self.canvas.create_text(text_x, 119, text=title_text, fill=badge_col, font=(KHMER_FONT_NAME, 8, "bold"), anchor="w", tags=(seg_tag, "bgm_seg"))
                
            # Crisp Emerald Acoustic Waveforms
            wave_col = "#EF4444" if vol_pct > 130 else ("#10B981" if vol_pct >= 50 else ("#34D399" if vol_pct > 0 else "#4B5563"))
            
            if vol <= 0.01:
                self.canvas.create_line(x1 + 2, 138, x2 - 2, 138, fill="#4B5563", width=1, dash=(2, 2), tags=(seg_tag, "bgm_seg"))
            else:
                wave_amp = min(1.8, max(0.15, vol))
                step = 4
                for i in range(x1 + 4, x2 - 4, step):
                    mw = int((2 + abs(math.sin(i * 0.09)) * 8) * wave_amp)
                    mw = min(14, max(1, mw))
                    self.canvas.create_line(i, 141, i, 141 - mw, fill=wave_col, width=1, tags=(seg_tag, "bgm_seg"))

        # 4.5. Copyright Red Highlights (Overlays on tracks & timeline)
        if getattr(self, 'copyright_segments', None):
            for cseg in self.copyright_segments:
                cx1 = int(cseg.get('start', 0.0) * pps)
                cx2 = max(cx1 + 10, int(cseg.get('end', 0.0) * pps))
                # Semi-transparent red highlight across V1, A1, A2
                self.canvas.create_rectangle(cx1, 36, cx2, 144, fill="#EF4444", stipple="gray25", outline="#DC2626", width=2, tags="copyright_hl")
                # Top ruler red stripe
                self.canvas.create_rectangle(cx1, 0, cx2, 8, fill="#EF4444", outline="", tags="copyright_hl")
                # Warning badge with song title
                c_title = cseg.get('title', 'Copyright')
                if len(c_title) > 22:
                    c_title = c_title[:20] + ".."
                self.canvas.create_text(cx1 + 4, 18, text=f"⚠️ {c_title}", fill="#FCA5A5", font=("Segoe UI", 8, "bold"), anchor="w", tags="copyright_hl")

        # 5. Premiere Blue Playhead (Cursor & Vertical Line)

        px = int(self.current_time_sec * pps)
        ph_h = max(144, self.canvas.winfo_height())
        self.canvas.create_line(px, 0, px, ph_h, fill="#23A8F2", width=1.5, tags="playhead")
        self.canvas.create_polygon(
            px - 6, 0,
            px + 6, 0,
            px + 6, 18,
            px, 24,
            px - 6, 18,
            fill="#23A8F2", outline="#38BDF8", tags="playhead"
        )

    def _on_canvas_click(self, event):
        self.canvas.focus_set()
        canvas_x = self.canvas.canvasx(event.x)
        pps = self.pixels_per_sec * self.zoom
        self.current_time_sec = max(0.0, min(self.duration_sec, canvas_x / pps))
        self.set_current_time(self.current_time_sec)
        
        # 1. Razor Tool (Cut video, dialogue, or BGM)
        if self.active_tool == "razor":
            if 36 <= event.y <= 72: # Track V1: Video
                self.split_video_at_time(self.current_time_sec)
                return
            elif 72 <= event.y <= 108: # Track A1: Dialogue / Speech
                self.split_dialogue_at_time(self.current_time_sec)
                return
            elif 108 <= event.y <= 144: # Track A2: BGM
                self.split_bgm_at_time(self.current_time_sec)
                return

        # 2. Track Select Forward Tool (A)
        if self.active_tool == "track_forward":
            self.select_forward_from_time(self.current_time_sec)
            return

        # 3. Standard Selection Tool
        # Track V1: Video Track Selection (Height: 36 to 72)
        if 36 <= event.y <= 72:
            seg_idx = None
            for i, vseg in enumerate(self.video_segments):
                if vseg['start'] <= self.current_time_sec <= vseg['end']:
                    seg_idx = i
                    break
            if seg_idx is None and self.video_segments:
                best_dist = 999999.0
                for i, vseg in enumerate(self.video_segments):
                    d = min(abs(self.current_time_sec - vseg['start']), abs(self.current_time_sec - vseg['end']))
                    if d < best_dist:
                        best_dist = d
                        seg_idx = i
            self.selected_track = "v1"
            self.selected_video_idx = seg_idx
            self.selected_clip_idx = None
            self.selected_clips.clear()
            self.selected_bgm_idx = None
            self.redraw()
            if self.on_seek:
                self.on_seek(self.current_time_sec)
            return

        # Track A1: Dialogue Clips (Height: 72 to 108)
        elif 72 <= event.y <= 108:
            self.selected_track = "a1"
            self.selected_video_idx = None
            self.selected_bgm_idx = None
            self.selected_clips.clear()
            c_idx = None
            items = self.canvas.find_overlapping(canvas_x - 1, event.y - 1, canvas_x + 1, event.y + 1)
            for it in items:
                tags = self.canvas.gettags(it)
                for t in tags:
                    if t.startswith("clip_"):
                        c_idx = int(t.split("_")[1])
                        break
                if c_idx is not None:
                    break
            if c_idx is None:
                c_idx = self._get_dialogue_clip_at_time(self.current_time_sec)
            if c_idx is not None:
                self.selected_clip_idx = c_idx
                self.selected_clips.add(c_idx)
                if self.on_clip_click:
                    self.on_clip_click(c_idx)
            self.redraw()
            if self.on_seek:
                self.on_seek(self.current_time_sec)
            return

        # Track A2: Background Music Track Clicks (Height: 108 to 144)
        elif 108 <= event.y <= 144:
            self.selected_track = "a2"
            self.selected_video_idx = None
            self.selected_clip_idx = None
            self.selected_clips.clear()
            seg_idx = self._get_bgm_segment_at_time(self.current_time_sec)
            if seg_idx is not None:
                self.selected_bgm_idx = seg_idx
                self.redraw()
                self.open_bgm_volume_dialog(seg_idx)
            if self.on_seek:
                self.on_seek(self.current_time_sec)
            return

        if self.on_seek:
            self.on_seek(self.current_time_sec)

    def _on_canvas_drag(self, event):
        self._on_canvas_click(event)

    def set_current_time(self, sec):
        self.current_time_sec = sec
        pps = self.pixels_per_sec * self.zoom
        self.canvas.delete("playhead")
        px = int(self.current_time_sec * pps)
        ph_h = max(144, self.canvas.winfo_height())
        self.canvas.create_line(px, 0, px, ph_h, fill="#23A8F2", width=1.5, tags="playhead")
        self.canvas.create_polygon(
            px - 6, 0,
            px + 6, 0,
            px + 6, 18,
            px, 24,
            px - 6, 18,
            fill="#23A8F2", outline="#38BDF8", tags="playhead"
        )
        self._draw_track_headers()

    def set_duration(self, sec):
        self.duration_sec = max(5.0, sec)
        if hasattr(self, 'duration_display'):
            self.duration_display.configure(text=format_smpte(self.duration_sec, self.fps))
        if len(self.video_segments) <= 1:
            self.video_segments = [{'start': 0.0, 'end': self.duration_sec}]
        elif self.video_segments and self.video_segments[-1]['end'] < self.duration_sec:
            self.video_segments[-1]['end'] = self.duration_sec
            
        if len(self.audio_segments) <= 1:
            self.audio_segments = [{'start': 0.0, 'end': self.duration_sec}]
        elif self.audio_segments and self.audio_segments[-1]['end'] < self.duration_sec:
            self.audio_segments[-1]['end'] = self.duration_sec

        if len(self.bgm_segments) == 1 and self.bgm_segments[0]['start'] == 0:
            self.bgm_segments[0]['end'] = self.duration_sec
        elif self.bgm_segments:
            if self.bgm_segments[-1]['end'] < self.duration_sec:
                self.bgm_segments[-1]['end'] = self.duration_sec
        self.redraw()

    def set_clips(self, clips):
        self.clips = clips
        if clips:
            max_e = max([c.get('end', 0) for c in clips])
            self.duration_sec = max(self.duration_sec, max_e + 2.0)
            if hasattr(self, 'duration_display'):
                self.duration_display.configure(text=format_smpte(self.duration_sec, self.fps))
            if len(self.bgm_segments) == 1 and self.bgm_segments[0]['start'] == 0:
                self.bgm_segments[0]['end'] = self.duration_sec
        self.redraw()

    def zoom_in(self):
        self.zoom = min(4.0, self.zoom * 1.3)
        self.zoom_badge.configure(text=f"{int(self.zoom * 100)}%")
        self.redraw()

    def zoom_out(self):
        self.zoom = max(0.25, self.zoom / 1.3)
        self.zoom_badge.configure(text=f"{int(self.zoom * 100)}%")
        self.redraw()

# ---------------------------------------------------------
# CustomTkinter Desktop Application Class
# ---------------------------------------------------------
class DubbingApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configure Window
        self.title("DUB TV - AI Video Dubbing & Translation")
        self.geometry("1240x950")
        self.minsize(1100, 820)
        
        # Set Window Icon (DUB TV Logo)
        _app_dir = os.path.dirname(os.path.abspath(__file__))
        _ico_path = os.path.join(_app_dir, "logo.ico")
        if os.path.exists(_ico_path):
            try:
                self.iconbitmap(_ico_path)
            except Exception:
                pass
        _png_path = os.path.join(_app_dir, "logo.png")
        if os.path.exists(_png_path):
            try:
                from PIL import ImageTk
                _ico_img = ImageTk.PhotoImage(Image.open(_png_path).resize((32, 32), Image.Resampling.LANCZOS))
                self.iconphoto(True, _ico_img)
                self._app_icon_ref = _ico_img
            except Exception:
                pass
        
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color="#0F1115")
        
        # Multi-Language & Font support
        self.current_lang = get_saved_language()
        self._timeline_deb_id = None
        global KHMER_FONT_NAME
        KHMER_FONT_NAME = get_khmer_ui_font_name()
        
        # State Data
        self.segments_data = []
        self.extracted_audio_path = ""
        self.generated_master_audio = ""
        self.temp_dir = ""
        self.v1_merged_video_path = ""
        self.timeline_visible = True

        self._build_ui()
        
    def t(self, key: str) -> str:
        cur_dict = UI_STRINGS.get(self.current_lang, UI_STRINGS["km"])
        return cur_dict.get(key, UI_STRINGS["km"].get(key, key))

    def _build_ui(self):
        # DUB TV Brand Header (Studio Top Bar)
        header_frame = ctk.CTkFrame(self, fg_color="#181A20", corner_radius=8, border_width=1, border_color="#2E333D")
        header_frame.pack(fill="x", padx=15, pady=(8, 4))
        
        brand_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        brand_box.pack(side="left", padx=8, pady=6)

        logo_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_file):
            try:
                logo_pil = Image.open(logo_file).resize((36, 36), Image.Resampling.LANCZOS)
                self.app_logo_img = ctk.CTkImage(light_image=logo_pil, dark_image=logo_pil, size=(36, 36))
                logo_lbl = ctk.CTkLabel(brand_box, image=self.app_logo_img, text="")
                logo_lbl.pack(side="left", padx=(0, 10))
            except Exception as e:
                print(f"[Warning] Logo load error: {e}")

        title_text_box = ctk.CTkFrame(brand_box, fg_color="transparent")
        title_text_box.pack(side="left")

        title_row = ctk.CTkFrame(title_text_box, fg_color="transparent")
        title_row.pack(anchor="w")

        ctk.CTkLabel(
            title_row,
            text="DUB TV",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=18, weight="bold"),
            text_color="#10B981"
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            title_row,
            text="STUDIO",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=9, weight="bold"),
            text_color="#10B981",
            fg_color="#1A2E26",
            corner_radius=4,
            padx=5, pady=1
        ).pack(side="left", padx=(0, 8))

        self.lbl_app_subtitle = ctk.CTkLabel(
            title_row,
            text=self.t("header_sub"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            text_color="#9CA3AF"
        )
        self.lbl_app_subtitle.pack(side="left")

        # Top-Right Controls: Status Pill & Language Switcher
        r_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        r_box.pack(side="right", padx=8, pady=4)

        self.system_status_pill = ctk.CTkLabel(
            r_box,
            text="● Ready",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            text_color="#10B981",
            fg_color="#1A2E26",
            corner_radius=4,
            padx=8, pady=3
        )
        self.system_status_pill.pack(side="left", padx=(0, 10))

        lang_box = ctk.CTkFrame(r_box, fg_color="transparent")
        lang_box.pack(side="left")
        
        self.lbl_lang_prefix = ctk.CTkLabel(
            lang_box, 
            text=self.t("lang_label"), 
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#9CA3AF"
        )
        self.lbl_lang_prefix.pack(side="left", padx=(0, 4))

        self.lang_option = ctk.CTkOptionMenu(
            lang_box,
            values=["🇰🇭 ភាសាខ្មែរ", "🇺🇸 English", "🇨🇳 中文"],
            command=self._on_language_change,
            width=125,
            height=26,
            fg_color="#262A34",
            button_color="#1E2128",
            button_hover_color="#323846",
            text_color="#E5E7EB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11)
        )
        lang_map_rev = {"km": "🇰🇭 ភាសាខ្មែរ", "en": "🇺🇸 English", "zh": "🇨🇳 中文"}
        self.lang_option.set(lang_map_rev.get(self.current_lang, "🇰🇭 ភាសាខ្មែរ"))
        self.lang_option.pack(side="left")


        # Main Application Container
        self.tab_video = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_video.pack(padx=15, pady=(0, 6), fill="both", expand=True)
        
        # Build Main UI
        self._build_tab1_ui()

        # Apply initial language strings
        self.apply_language()

        # Global Spacebar Shortcut: Press once to play, press again to stop (safe against text entries)
        self.bind_all("<space>", self._on_space_key)

    def _on_space_key(self, event):
        w = event.widget
        w_class = ""
        try:
            w_class = w.winfo_class().lower()
        except Exception:
            pass
        w_str = str(w).lower()
        # If focused inside any text input or entry, do not intercept Space so normal typing works
        if (w_class in ("entry", "text", "ctkentry", "ctktextbox") or 
            "entry" in w_str or "text" in w_str):
            return
        
        # Toggle play/stop for video player
        if hasattr(self, 'video_player') and self.video_player:
            self.video_player.toggle_play()
            return "break"

    def _save_gemini_key_action(self):
        k = self.gemini_key_entry.get().strip()
        save_gemini_key(k)
        if k:
            messagebox.showinfo("ជោគជ័យ", "បានរក្សាទុក Gemini API Key រួចរាល់!\nប្រព័ន្ធនឹងប្រើប្រាស់ Gemini 2.5 Flash សម្រាប់ការបកប្រែសម្រាយរឿង។")
        else:
            messagebox.showinfo("ដំណឹង", "បានលុប Gemini API Key រួចរាល់!")

    def _toggle_show_gemini_key(self):
        cur = self.gemini_key_entry.cget("show")
        if cur == "*":
            self.gemini_key_entry.configure(show="")
            self.gemini_toggle_show_btn.configure(text="🔒")
        else:
            self.gemini_key_entry.configure(show="*")
            self.gemini_toggle_show_btn.configure(text="👁️")

    def get_current_gemini_key(self) -> str:
        if hasattr(self, 'gemini_key_entry'):
            k = self.gemini_key_entry.get().strip()
            if k:
                return k
        return get_saved_gemini_key()

    def is_gemini_enabled(self) -> bool:
        return bool(self.use_gemini_var.get()) if hasattr(self, 'use_gemini_var') else False

    def _on_language_change(self, choice: str):
        if "English" in choice:
            self.current_lang = "en"
        elif "中文" in choice:
            self.current_lang = "zh"
        else:
            self.current_lang = "km"
        save_language(self.current_lang)
        self.apply_language()

    def apply_language(self):
        tr = UI_STRINGS.get(self.current_lang, UI_STRINGS["km"])
        if hasattr(self, 'lbl_app_subtitle'):
            self.lbl_app_subtitle.configure(text=tr["header_sub"])
        if hasattr(self, 'lbl_lang_prefix'):
            self.lbl_lang_prefix.configure(text=tr["lang_label"])
        
        if hasattr(self, 'gemini_switch'):
            self.gemini_switch.configure(text=tr["gemini_title"])
        if hasattr(self, 'lbl_gemini_key'):
            self.lbl_gemini_key.configure(text=tr["gemini_key_lbl"])
        if hasattr(self, 'gemini_save_btn'):
            self.gemini_save_btn.configure(text=tr["save_btn"])
        if hasattr(self, 'gemini_key_entry'):
            self.gemini_key_entry.configure(placeholder_text=tr["gemini_key_placeholder"])
        
        if hasattr(self, 'v1_video_entry'):
            self.v1_video_entry.configure(placeholder_text=tr["video_placeholder"])
        if hasattr(self, 'v1_browse_btn'):
            self.v1_browse_btn.configure(text=tr["browse_video_btn"])
        if hasattr(self, 'v1_remove_video_btn'):
            self.v1_remove_video_btn.configure(text=tr.get("remove_video_btn", "❌ ដកវីដេអូចេញ"))
        if hasattr(self, 'lbl_model'):
            self.lbl_model.configure(text=tr["model_lbl"])
        if hasattr(self, 'lbl_voice'):
            self.lbl_voice.configure(text=tr["voice_lbl"])
        if hasattr(self, 'lbl_speed'):
            self.lbl_speed.configure(text=tr["speed_lbl"])
        if hasattr(self, 'auto_pipeline_cb'):
            self.auto_pipeline_cb.configure(text=tr.get("auto_cb", "⚡ Auto"))
        if hasattr(self, 'v1_extract_btn'):
            self.v1_extract_btn.configure(text=tr.get("scan_translate_btn", tr.get("start_btn", "🔍 ១. ស្កែន & បកប្រែ")))
        if hasattr(self, 'v1_dub_voice_btn'):
            self.v1_dub_voice_btn.configure(text=tr.get("dub_voice_btn", "🎙️ ២. បញ្ចូលសំឡេង"))
        if hasattr(self, 'v1_export_btn'):
            self.v1_export_btn.configure(text=tr.get("export_btn", "📤 ៣. Export វីដេអូ"))
        
        if hasattr(self, 'v1_status_label') and not self.segments_data:
            self.v1_status_label.configure(text=tr["initial_status"])
            
        if hasattr(self, 'video_player'):
            self.video_player.apply_language(self.current_lang)
            
        if hasattr(self, 'timeline'):
            self.timeline.set_language(self.current_lang)

        if hasattr(self, '_cc_settings_dialog') and self._cc_settings_dialog and self._cc_settings_dialog.winfo_exists():
            self._cc_settings_dialog.apply_language(self.current_lang)
            
        if hasattr(self, 'lbl_sub_editor'):
            self.lbl_sub_editor.configure(text=tr["sub_editor_title"])
        if hasattr(self, 'v1_find_replace_btn'):
            self.v1_find_replace_btn.configure(text=tr["find_replace_btn"])
        if hasattr(self, 'v1_retranslate_all_btn'):
            self.v1_retranslate_all_btn.configure(text=tr["retranslate_all_btn"])
        if hasattr(self, 'v1_regen_video_btn'):
            self.v1_regen_video_btn.configure(text=tr["regen_video_btn"])
            
        if hasattr(self, 'lbl_bgm'):
            self.lbl_bgm.configure(text=tr["bgm_lbl"])
        if hasattr(self, 'btn_manage_bgm'):
            self.btn_manage_bgm.configure(text=tr.get("manage_bgm_btn", "✂️ រៀបចំកង់ BGM"))
        if hasattr(self, 'v1_mute_orig_cb'):
            self.v1_mute_orig_cb.configure(text=tr["mute_orig_cb"])
        if hasattr(self, 'v1_demucs_cb'):
            self.v1_demucs_cb.configure(text=tr["demucs_cb"])
            
        if hasattr(self, 'v1_result_info_label'):
            self.v1_result_info_label.configure(text=tr["result_preview_title"])
        if hasattr(self, 'v1_result_path_entry'):
            self.v1_result_path_entry.configure(placeholder_text=tr["result_path_placeholder"])
        if hasattr(self, 'v1_play_video_btn'):
            self.v1_play_video_btn.configure(text=tr["play_video_btn"])
        if hasattr(self, 'v1_locate_video_btn'):
            self.v1_locate_video_btn.configure(text=tr["locate_video_btn"])
            
        if hasattr(self, 'auto_gender_cb'):
            self.auto_gender_cb.configure(text=tr.get("auto_gender_cb", "🎭 អូតូសំឡេងស្រី-ប្រុស"))

        # Timeline Toggle Button text update
        btn_tl_text = tr.get("toggle_timeline_hide", "🎞️ បិទ Timeline") if getattr(self, 'timeline_visible', True) else tr.get("toggle_timeline_show", "🎞️ បើក Timeline")
        if hasattr(self, 'btn_toggle_timeline') and self.btn_toggle_timeline:
            self.btn_toggle_timeline.configure(text=btn_tl_text)

        # CC Subtitle Button state update
        if hasattr(self, 'btn_cc') and self.btn_cc:
            self.update_cc_button_state(getattr(self.video_player, 'cc_enabled', True) if hasattr(self, 'video_player') else True)

        # CC Subtitle Settings Button text update
        if hasattr(self, 'btn_cc_settings') and self.btn_cc_settings:
            self.btn_cc_settings.configure(text=tr.get("toggle_cc_settings", "⚙️ កំណត់ Subtitle"))

        # Voice Dropdown Update
        if hasattr(self, 'v1_voice_dropdown'):
            cur_v = self.v1_voice_dropdown.get()
            new_v_list = tr["voice_options"]
            self.v1_voice_dropdown.configure(values=new_v_list)
            if any(k in cur_v for k in ["Auto", "អូតូ", "自动", "Character", "តាមតួអង្គ"]):
                self.v1_voice_dropdown.set(new_v_list[0])
            elif any(k in cur_v for k in ["Sreymom", "ស្រី", "Female", "女"]):
                self.v1_voice_dropdown.set(new_v_list[2])
            elif any(k in cur_v for k in ["Piseth", "ប្រុស", "Male", "男"]):
                self.v1_voice_dropdown.set(new_v_list[1])
            else:
                self.v1_voice_dropdown.set(new_v_list[0])
                
        # Speed Dropdown Update
        if hasattr(self, 'v1_voice_speed_dropdown'):
            cur_s = self.v1_voice_speed_dropdown.get()
            new_s_list = tr["speed_options"]
            self.v1_voice_speed_dropdown.configure(values=new_s_list)
            if "1.05" in cur_s:
                self.v1_voice_speed_dropdown.set(new_s_list[1])
            elif "1.15" in cur_s:
                self.v1_voice_speed_dropdown.set(new_s_list[3])
            elif "1.1" in cur_s:
                self.v1_voice_speed_dropdown.set(new_s_list[2])
            elif "0.95" in cur_s:
                self.v1_voice_speed_dropdown.set(new_s_list[4])
            else:
                self.v1_voice_speed_dropdown.set(new_s_list[0])
                
        # Update dynamically populated segments
        for s in self.segments_data:
            if 'btn_retrans' in s and s['btn_retrans']:
                s['btn_retrans'].configure(text=tr["segment_retrans_btn"])
            if 'btn_prev' in s and s['btn_prev']:
                s['btn_prev'].configure(text=tr["segment_preview_btn"])
            if 'lbl_orig' in s and s['lbl_orig']:
                orig_t = s.get('orig', '')
                s['lbl_orig'].configure(text=f"{tr['segment_orig_prefix']}{orig_t}")
            if 'voice_widget' in s and s['voice_widget']:
                is_fem = (s.get('gender') == 'female')
                v_choices = [tr["segment_gender_male"], tr["segment_gender_female"]]
                s['voice_widget'].configure(values=v_choices)
                s['voice_widget'].set(v_choices[1] if is_fem else v_choices[0])

        if hasattr(self, 'right_col'):
            try:
                rw = self.right_col.winfo_width()
                if rw > 30:
                    self._adapt_sub_header_layout(rw)
            except Exception:
                pass

    def _on_sub_editor_configure(self, event):
        if hasattr(self, 'right_col') and event.widget == self.right_col:
            w = event.width
            if getattr(self, '_last_sub_hdr_w', 0) == w or w < 20:
                return
            self._last_sub_hdr_w = w
            self._adapt_sub_header_layout(w)

    def _adapt_sub_header_layout(self, w: int):
        if not hasattr(self, 'v1_regen_video_btn'):
            return
        
        tr = UI_STRINGS.get(self.current_lang, UI_STRINGS["km"])
        
        if w >= 740:
            if hasattr(self, 'lbl_sub_editor'):
                if not self.lbl_sub_editor.winfo_ismapped():
                    self.lbl_sub_editor.pack(side="left")
                self.lbl_sub_editor.configure(text=tr.get("sub_editor_title", "✍️ បញ្ជីអត្ថបទកែប្រែខ្មែរ (Subtitle Editor)"), font=ctk.CTkFont(size=12, weight="bold"))
            self.v1_regen_video_btn.configure(text=tr.get("regen_video_btn", "🎬 បញ្ចូលសំឡេងឡើងវិញ"), width=135, font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_find_replace_btn.configure(text=tr.get("find_replace_btn", "🔍 ផ្លាស់ប្ដូរពាក្យ"), width=110, font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_retranslate_all_btn.configure(text=tr.get("retranslate_all_btn", "🔄 បកប្រែឡើងវិញទាំងអស់"), width=130, font=ctk.CTkFont(size=11))
        elif w >= 560:
            if hasattr(self, 'lbl_sub_editor'):
                if not self.lbl_sub_editor.winfo_ismapped():
                    self.lbl_sub_editor.pack(side="left")
                self.lbl_sub_editor.configure(text="✍️ អត្ថបទខ្មែរ" if self.current_lang == "km" else "✍️ Subtitles", font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_regen_video_btn.configure(text="🎬 បញ្ចូលសំឡេង" if self.current_lang == "km" else "🎬 Voice", width=98, font=ctk.CTkFont(size=10, weight="bold"))
            self.v1_find_replace_btn.configure(text="🔍 ផ្លាស់ប្ដូរ" if self.current_lang == "km" else "🔍 Replace", width=80, font=ctk.CTkFont(size=10, weight="bold"))
            self.v1_retranslate_all_btn.configure(text="🔄 បកប្រែឡើងវិញ" if self.current_lang == "km" else "🔄 Retranslate", width=98, font=ctk.CTkFont(size=10))
        elif w >= 420:
            if hasattr(self, 'lbl_sub_editor'):
                if not self.lbl_sub_editor.winfo_ismapped():
                    self.lbl_sub_editor.pack(side="left")
                self.lbl_sub_editor.configure(text="✍️ CC", font=ctk.CTkFont(size=10, weight="bold"))
            self.v1_regen_video_btn.configure(text="🎬 សំឡេង" if self.current_lang == "km" else "🎬 Voice", width=68, font=ctk.CTkFont(size=10, weight="bold"))
            self.v1_find_replace_btn.configure(text="🔍 រក" if self.current_lang == "km" else "🔍 Find", width=58, font=ctk.CTkFont(size=10, weight="bold"))
            self.v1_retranslate_all_btn.configure(text="🔄 បកប្រែ" if self.current_lang == "km" else "🔄 Trans", width=62, font=ctk.CTkFont(size=10))
        elif w >= 320:
            if hasattr(self, 'lbl_sub_editor'):
                if not self.lbl_sub_editor.winfo_ismapped():
                    self.lbl_sub_editor.pack(side="left")
                self.lbl_sub_editor.configure(text="✍️", font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_regen_video_btn.configure(text="🎬", width=36, font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_find_replace_btn.configure(text="🔍", width=36, font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_retranslate_all_btn.configure(text="🔄", width=36, font=ctk.CTkFont(size=11, weight="bold"))
        else:
            if hasattr(self, 'lbl_sub_editor') and self.lbl_sub_editor.winfo_ismapped():
                self.lbl_sub_editor.pack_forget()
            self.v1_regen_video_btn.configure(text="🎬", width=32, font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_find_replace_btn.configure(text="🔍", width=32, font=ctk.CTkFont(size=11, weight="bold"))
            self.v1_retranslate_all_btn.configure(text="🔄", width=32, font=ctk.CTkFont(size=11, weight="bold"))

    def _open_find_replace_dialog(self):
        """Open Find & Replace modal to replace text across all subtitle segments"""
        if not self.segments_data:
            messagebox.showinfo(self.t("notice_title"), self.t("no_segments_to_replace"))
            return
        
        dialog = ctk.CTkToplevel(self)
        dialog.title(self.t("find_replace_dialog_title"))
        dialog.geometry("460x280")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        kh_f = get_khmer_ui_font(12)
        
        ctk.CTkLabel(dialog, text=self.t("find_replace_heading"), font=ctk.CTkFont(size=14, weight="bold"), text_color="#38BDF8").pack(pady=(16, 10))
        
        f_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        f_frame.pack(fill="x", padx=25, pady=4)
        ctk.CTkLabel(f_frame, text=self.t("find_label"), font=kh_f).pack(anchor="w")
        find_sv = tk.StringVar()
        find_entry = ctk.CTkEntry(f_frame, font=kh_f, height=32, textvariable=find_sv)
        find_entry.pack(fill="x", pady=(2, 0))
        attach_context_menu(find_entry, lambda: self.current_lang)
        find_entry.focus_set()
        
        r_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        r_frame.pack(fill="x", padx=25, pady=4)
        ctk.CTkLabel(r_frame, text=self.t("replace_label"), font=kh_f).pack(anchor="w")
        replace_sv = tk.StringVar()
        replace_entry = ctk.CTkEntry(r_frame, font=kh_f, height=32, textvariable=replace_sv)
        replace_entry.pack(fill="x", pady=(2, 0))
        attach_context_menu(replace_entry, lambda: self.current_lang)

        def _setup_sv_heal(sv):
            is_healing = False
            def _heal_cb(*args):
                nonlocal is_healing
                if is_healing:
                    return
                v = sv.get()
                if 'áž' in v or 'á' in v or '\xe1' in v:
                    fixed = restore_mojibake(v)
                    if fixed != v:
                        is_healing = True
                        sv.set(fixed)
                        is_healing = False
            sv.trace_add("write", _heal_cb)

        _setup_sv_heal(find_sv)
        _setup_sv_heal(replace_sv)
        
        def _do_replace():
            f_val = restore_mojibake(find_entry.get().strip())
            r_val = restore_mojibake(replace_entry.get())
            if not f_val:
                messagebox.showwarning(self.t("warning_title"), self.t("empty_find_warning"))
                return
            count = 0
            for seg in self.segments_data:
                w = seg.get('widget')
                if w and hasattr(w, 'get'):
                    old_text = w.get()
                    if f_val in old_text:
                        new_text = old_text.replace(f_val, r_val)
                        w.delete(0, 'end')
                        w.insert(0, new_text)
                        count += 1
            if hasattr(self, 'timeline'):
                self.timeline.redraw()
            dialog.destroy()
            msg = self.t("replace_success").format(n=count)
            messagebox.showinfo(self.t("success_title"), msg)
        
        btn_box = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_box.pack(pady=16)
        
        ctk.CTkButton(
            btn_box, 
            text=self.t("btn_do_replace"), 
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669", 
            hover_color="#047857",
            command=_do_replace
        ).pack(side="left", padx=8)
        
        ctk.CTkButton(
            btn_box, 
            text=self.t("btn_cancel"), 
            font=ctk.CTkFont(size=12),
            fg_color="#64748B", 
            hover_color="#475569",
            command=dialog.destroy
        ).pack(side="left", padx=8)

    # =========================================================
    # TAB 1: Video Subtitle Extraction -> Edit Text -> Voice -> Video
    # =========================================================
    def _build_tab1_ui(self):
        tab = self.tab_video
        
        # =========================================================
        # TOP DASHBOARD: Studio Control Header (Dark Slate #181A20, Border #2E333D)
        # =========================================================
        top_dashboard = ctk.CTkFrame(tab, fg_color="#181A20", corner_radius=8, border_width=1, border_color="#2E333D")
        top_dashboard.pack(fill="x", padx=15, pady=(2, 4))
        
        # --- ROW 1: Media Input & Utility Section ---
        r_row1 = ctk.CTkFrame(top_dashboard, fg_color="transparent")
        r_row1.pack(fill="x", padx=10, pady=(6, 3))
        
        self.v1_video_entry = ctk.CTkEntry(
            r_row1,
            placeholder_text=self.t("video_placeholder"),
            height=28,
            fg_color="#12141A",
            border_color="#2E333D",
            border_width=1,
            text_color="#F3F4F6",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11)
        )
        self.v1_video_entry.pack(side="left", padx=(0, 6), fill="x", expand=True)
        attach_context_menu(self.v1_video_entry, lambda: self.current_lang)
        
        self.v1_browse_btn = ctk.CTkButton(
            r_row1,
            text=self.t("browse_video_btn"),
            command=self._browse_v1_file,
            width=115,
            height=28,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#E5E7EB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold")
        )
        self.v1_browse_btn.pack(side="left", padx=(0, 6))

        self.v1_remove_video_btn = ctk.CTkButton(
            r_row1,
            text=self.t("remove_video_btn"),
            command=self._remove_current_video,
            width=100,
            height=28,
            fg_color="#262A34",
            hover_color="#3B2828",
            border_color="#373D4B",
            border_width=1,
            text_color="#F87171",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold")
        )
        self.v1_remove_video_btn.pack(side="left", padx=(0, 6))

        self.v1_copyright_btn = ctk.CTkButton(
            r_row1,
            text="🛡️ ពិនិត្យ Copyright",
            command=self._open_copyright_scanner_dialog,
            width=135,
            height=28,
            fg_color="#2E181A",
            hover_color="#3F1B1E",
            border_color="#7F1D1D",
            border_width=1,
            text_color="#EF4444",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold")
        )
        self.v1_copyright_btn.pack(side="left", padx=(0, 6))

        self.v1_locate_video_btn = ctk.CTkButton(
            r_row1,
            text="📁 បើក Folder",
            width=110,
            height=28,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#CBD5E1",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._open_output_or_video_folder
        )
        self.v1_locate_video_btn.pack(side="right")
        
        # --- ROW 2: AI Engine Settings & Voice Configuration ---
        r_row2 = ctk.CTkFrame(top_dashboard, fg_color="transparent")
        r_row2.pack(fill="x", padx=10, pady=(2, 4))

        # Gemini 2.5 Flash Switch
        self.use_gemini_var = ctk.BooleanVar(value=True)
        self.gemini_switch = ctk.CTkSwitch(
            r_row2,
            text="✨ Gemini 2.5 Flash",
            variable=self.use_gemini_var,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            progress_color="#10B981"
        )
        self.gemini_switch.pack(side="left", padx=(0, 6))

        # Gemini API Key
        self.lbl_gemini_key = ctk.CTkLabel(
            r_row2,
            text=self.t("gemini_key_lbl"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#9CA3AF"
        )
        self.lbl_gemini_key.pack(side="left", padx=(0, 3))

        self.gemini_key_entry = ctk.CTkEntry(
            r_row2,
            placeholder_text=self.t("gemini_key_placeholder"),
            width=130,
            height=26,
            show="*",
            fg_color="#12141A",
            border_color="#2E333D",
            border_width=1,
            text_color="#F3F4F6",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11)
        )
        self.gemini_key_entry.pack(side="left", padx=(0, 3))
        attach_context_menu(self.gemini_key_entry, lambda: self.current_lang)
        saved_k = get_saved_gemini_key()
        if saved_k:
            self.gemini_key_entry.insert(0, saved_k)

        self.gemini_toggle_show_btn = ctk.CTkButton(
            r_row2,
            text="👁️",
            width=26,
            height=26,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            command=self._toggle_show_gemini_key
        )
        self.gemini_toggle_show_btn.pack(side="left", padx=(0, 3))

        self.gemini_save_btn = ctk.CTkButton(
            r_row2,
            text=self.t("save_btn"),
            width=65,
            height=26,
            command=self._save_gemini_key_action,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#10B981",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold")
        )
        self.gemini_save_btn.pack(side="left", padx=(0, 8))

        # Model Dropdowns
        self.lbl_model = ctk.CTkLabel(
            r_row2,
            text=self.t("model_lbl"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#9CA3AF"
        )
        self.lbl_model.pack(side="left", padx=(0, 2))
        self.v1_whisper_dropdown = ctk.CTkOptionMenu(
            r_row2,
            values=["tiny", "base", "small", "medium"],
            width=76,
            height=26,
            fg_color="#262A34",
            button_color="#1E2128",
            button_hover_color="#323846",
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=11)
        )
        self.v1_whisper_dropdown.set("base")
        self.v1_whisper_dropdown.pack(side="left", padx=(0, 6))
        
        self.lbl_voice = ctk.CTkLabel(
            r_row2,
            text=self.t("voice_lbl"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#9CA3AF"
        )
        self.lbl_voice.pack(side="left", padx=(0, 2))
        self.v1_voice_dropdown = ctk.CTkOptionMenu(
            r_row2,
            values=self.t("voice_options"),
            width=150,
            height=26,
            command=self._on_main_voice_change,
            fg_color="#262A34",
            button_color="#1E2128",
            button_hover_color="#323846",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11)
        )
        self.v1_voice_dropdown.set(self.t("voice_options")[0])
        self.v1_voice_dropdown.pack(side="left", padx=(0, 6))
        
        self.auto_gender_var = ctk.BooleanVar(value=True)
        self.auto_gender_cb = ctk.CTkCheckBox(
            r_row2,
            text=self.t("auto_gender_cb"),
            variable=self.auto_gender_var,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            fg_color="#10B981",
            hover_color="#059669",
            checkmark_color="#FFFFFF",
            command=self._on_auto_gender_toggle
        )
        self.auto_gender_cb.pack(side="left", padx=(0, 6))
        
        self.lbl_speed = ctk.CTkLabel(
            r_row2,
            text=self.t("speed_lbl"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#9CA3AF"
        )
        self.lbl_speed.pack(side="left", padx=(0, 2))
        self.v1_voice_speed_dropdown = ctk.CTkOptionMenu(
            r_row2,
            values=self.t("speed_options"),
            width=88,
            height=26,
            fg_color="#262A34",
            button_color="#1E2128",
            button_hover_color="#323846",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            dropdown_font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11)
        )
        self.v1_voice_speed_dropdown.set(self.t("speed_options")[0])
        self.v1_voice_speed_dropdown.pack(side="left", padx=(0, 8))
        
        self.auto_pipeline_var = ctk.BooleanVar(value=False)

        # --- ROW 3: Dedicated Primary Workflow Pipeline Deck (Never Clipped, 100% Visible) ---
        r_row3 = ctk.CTkFrame(top_dashboard, fg_color="#12141A", corner_radius=6, border_width=1, border_color="#2E333D")
        r_row3.pack(fill="x", padx=10, pady=(2, 6))

        pipe_lbl = ctk.CTkLabel(
            r_row3,
            text="⚡ ដំណើរការស្ទូឌីយោ (STUDIO WORKFLOW):",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#10B981"
        )
        pipe_lbl.pack(side="left", padx=(10, 12))

        # Step 1: Scan & Translate Button (🔍 ១. ស្កែន & បកប្រែ)
        self.v1_extract_btn = ctk.CTkButton(
            r_row3,
            text=self.t("scan_translate_btn"),
            command=self._start_scan_and_translate,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#E5E7EB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            height=30,
            width=150
        )
        self.v1_extract_btn.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            r_row3,
            text="➜",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4B5563"
        ).pack(side="left", padx=(0, 6))

        # Step 2: Dub Voice Button (🎙️ ២. បញ្ចូលសំឡេង)
        self.v1_dub_voice_btn = ctk.CTkButton(
            r_row3,
            text=self.t("dub_voice_btn"),
            command=lambda: self._start_generate_all_voice(auto_merge=False),
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#E5E7EB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            height=30,
            width=150,
            state="disabled"
        )
        self.v1_dub_voice_btn.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            r_row3,
            text="➜",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4B5563"
        ).pack(side="left", padx=(0, 6))

        # Step 3: Export Video Hero CTA Button (📤 ៣. Export វីដេអូ - Emerald Green)
        self.v1_export_btn = ctk.CTkButton(
            r_row3,
            text=self.t("export_btn"),
            command=self._open_export_dialog,
            fg_color="#10B981",
            hover_color="#059669",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            height=30,
            width=160,
            state="disabled"
        )
        self.v1_export_btn.pack(side="left")
        
        # Status Label & Progress Bar (Studio Compact)
        self.v1_status_label = ctk.CTkLabel(
            tab,
            text=self.t("initial_status"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#10B981"
        )
        self.v1_status_label.pack(anchor="w", padx=15, pady=(1, 1))
        
        self.v1_progress_bar = ctk.CTkProgressBar(
            tab,
            width=900,
            height=6,
            progress_color="#10B981",
            fg_color="#181A20",
            border_color="#2E333D",
            border_width=1
        )
        self.v1_progress_bar.set(0.0)
        self.v1_progress_bar.pack(fill="x", padx=15, pady=(0, 2))
        
        # =========================================================
        # PINNED BOTTOM ACTION BAR: Fixed Studio Control Dock
        # =========================================================
        bottom_frame = ctk.CTkFrame(tab, fg_color="#181A20", corner_radius=8, border_width=1, border_color="#2E333D")
        bottom_frame.pack(side="bottom", fill="x", padx=15, pady=(2, 4))
        self.pinned_bottom_bar = bottom_frame

        # =========================================================
        # MAIN VERTICAL SPLIT CONTAINER: Drag Up/Down (Top Video+Subtitles <-> Bottom Timeline)
        # =========================================================
        self.vertical_paned = tk.PanedWindow(
            tab,
            orient="vertical",
            bg="#0F1115",
            sashwidth=4,
            sashrelief="flat",
            bd=0,
            opaqueresize=True
        )
        self.vertical_paned.pack(fill="both", expand=True, padx=15, pady=(2, 2))
        
        # Top Section inside Vertical PanedWindow: Horizontal PanedWindow (50/50 Balanced Split)
        self.middle_paned = tk.PanedWindow(
            self.vertical_paned,
            orient="horizontal",
            bg="#0F1115",
            sashwidth=4,
            sashrelief="flat",
            bd=0,
            opaqueresize=True
        )
        self.vertical_paned.add(self.middle_paned, minsize=260)
        
        # Left Side: Embedded Video Player (Studio Card #181A20, Border #2E333D)
        left_col = ctk.CTkFrame(self.middle_paned, corner_radius=8, fg_color="#181A20", border_width=1, border_color="#2E333D")
        self.left_col = left_col
        self.middle_paned.add(left_col, minsize=320, stretch="always")
        
        def _get_khmer_audio_candidate():
            if hasattr(self, 'temp_dir') and self.temp_dir:
                merged_wav = os.path.join(self.temp_dir, "final_merged_track.wav")
                if os.path.exists(merged_wav):
                    return merged_wav
            if self.generated_master_audio and os.path.exists(self.generated_master_audio):
                return self.generated_master_audio
            if hasattr(self, 'temp_dir') and self.temp_dir:
                master_wav = os.path.join(self.temp_dir, "master_dubbed_voice.wav")
                if os.path.exists(master_wav):
                    return master_wav
            if hasattr(self, 'v1_merged_video_path') and self.v1_merged_video_path and os.path.exists(self.v1_merged_video_path):
                return self.v1_merged_video_path
            return ""

        def _request_generate_voice():
            if not self.segments_data:
                self._start_scan_and_translate()
            else:
                self._start_generate_all_voice(auto_merge=False)

        def _on_player_resize(w, h):
            try:
                self.middle_paned.sash_place(0, w + 24, 0)
            except Exception:
                pass

        self.video_player = EmbeddedVideoPlayer(
            left_col, 
            on_time_update=self._on_player_time_update,
            on_size_change=_on_player_resize,
            get_khmer_audio_cb=_get_khmer_audio_candidate,
            on_request_generate_voice=_request_generate_voice,
            on_play_state_change=self._on_player_play_state_change,
            on_audio_mode_change=lambda mode: self.timeline.set_audio_track_state(mode) if hasattr(self, 'timeline') and self.timeline else None,
            on_remove_video=self._remove_current_video,
            fg_color="transparent"
        )
        self.video_player.pack(fill="both", expand=True, padx=4, pady=4)
        
        # Right Side: Translated Text & Subtitle Editor (Studio Card #181A20, Border #2E333D)
        right_col = ctk.CTkFrame(self.middle_paned, corner_radius=8, fg_color="#181A20", border_width=1, border_color="#2E333D")
        self.right_col = right_col
        self.middle_paned.add(right_col, minsize=320, stretch="always")
        right_col.bind("<Configure>", self._on_sub_editor_configure)
        
        sec_hdr = ctk.CTkFrame(right_col, fg_color="transparent")
        sec_hdr.pack(fill="x", padx=10, pady=(6, 3))
        self.sec_hdr = sec_hdr
        self.lbl_sub_editor = ctk.CTkLabel(
            sec_hdr,
            text=self.t("sub_editor_title"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=12, weight="bold"),
            text_color="#F3F4F6"
        )
        self.lbl_sub_editor.pack(side="left")
        
        self.v1_retranslate_all_btn = ctk.CTkButton(
            sec_hdr,
            text=self.t("retranslate_all_btn"),
            width=135,
            height=26,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#9CA3AF",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            command=self._retranslate_all_segments,
            state="disabled"
        )
        self.v1_retranslate_all_btn.pack(side="right")

        self.v1_find_replace_btn = ctk.CTkButton(
            sec_hdr,
            text=self.t("find_replace_btn"),
            width=115,
            height=26,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#E5E7EB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._open_find_replace_dialog
        )
        self.v1_find_replace_btn.pack(side="right", padx=(0, 6))

        self.v1_regen_video_btn = ctk.CTkButton(
            sec_hdr,
            text=self.t("regen_video_btn"),
            width=135,
            height=26,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#10B981",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=lambda: self._start_generate_all_voice(auto_merge=False),
            state="disabled"
        )
        self.v1_regen_video_btn.pack(side="right", padx=(0, 6))
        
        self.scroll_frame = ctk.CTkScrollableFrame(
            right_col,
            height=240,
            fg_color="#12141A",
            border_color="#2E333D",
            border_width=1,
            corner_radius=6
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        
        # Bottom Section inside Vertical PanedWindow: Timeline Container
        self.bottom_pane = ctk.CTkFrame(self.vertical_paned, fg_color="transparent")
        self.vertical_paned.add(self.bottom_pane, minsize=140, height=186)

        # Multi-Track Dubbing Timeline Canvas
        self.timeline = DubbingTimeline(
            self.bottom_pane, 
            on_clip_click=self._on_timeline_clip_click,
            on_seek=self._on_timeline_seek,
            on_close=self._toggle_timeline_visibility,
            on_play=lambda: self.video_player.toggle_play(),
            on_pause=lambda: self.video_player.pause(),
            on_stop=lambda: self.video_player.stop(),
            on_rewind=lambda: self.video_player.rewind(),
            on_step_back=lambda: self.video_player.step_backward(1.0),
            on_step_fwd=lambda: self.video_player.step_forward(1.0),
            on_switch_audio_mode=lambda mode: self.video_player.switch_audio_mode(mode),
            on_toggle_cc=self._on_toggle_cc_subtitles,
            on_open_cc_settings=self._open_cc_settings_dialog,
            on_delete_dialogue=self._on_timeline_delete_dialogue,
            on_remove_video=self._remove_current_video
        )
        self.timeline.pack(fill="both", expand=True, padx=0, pady=(1, 2))
        
        # Row 1: Audio Mix & Background Music (BGM) Controls
        row_audio = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        row_audio.pack(fill="x", padx=10, pady=(4, 2))
        
        self.lbl_bgm = ctk.CTkLabel(
            row_audio,
            text=self.t("bgm_lbl"),
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#D1D5DB"
        )
        self.lbl_bgm.pack(side="left", padx=(0, 4))
        self.v1_bg_slider = ctk.CTkSlider(
            row_audio,
            from_=0.0, to=2.0,
            number_of_steps=40,
            width=110,
            progress_color="#10B981",
            button_color="#10B981",
            button_hover_color="#059669",
            command=self._v1_slider_label
        )
        self.v1_bg_slider.set(0.3)
        self.v1_bg_slider.pack(side="left", padx=(0, 4))
        self.v1_bg_label = ctk.CTkLabel(
            row_audio,
            text="30%",
            width=38,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#10B981"
        )
        self.v1_bg_label.pack(side="left", padx=(0, 6))
        
        self.btn_manage_bgm = ctk.CTkButton(
            row_audio,
            text=self.t("manage_bgm_btn"),
            width=120,
            height=25,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#E5E7EB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10, weight="bold"),
            command=self._open_bgm_manager
        )
        self.btn_manage_bgm.pack(side="left", padx=(0, 6))

        self.custom_bgm_path = ""
        self.btn_select_bgm = ctk.CTkButton(
            row_audio,
            text="🎵 ភ្លេង BGM ផ្ទាល់ខ្លួន...",
            width=130,
            height=25,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#D1D5DB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=10),
            command=self._select_custom_bgm
        )
        self.btn_select_bgm.pack(side="left", padx=(0, 4))
        
        self.lbl_custom_bgm = ctk.CTkLabel(
            row_audio,
            text="",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#10B981"
        )
        self.lbl_custom_bgm.pack(side="left", padx=(0, 4))

        self.btn_clear_bgm = ctk.CTkButton(
            row_audio,
            text="✕",
            width=22,
            height=22,
            fg_color="#2E181A",
            hover_color="#3F1B1E",
            border_color="#7F1D1D",
            border_width=1,
            text_color="#EF4444",
            font=ctk.CTkFont(size=10, weight="bold"),
            command=self._clear_custom_bgm
        )

        # Right-aligned Audio Checkboxes in Row 1
        self.v1_demucs_var = ctk.BooleanVar(value=True)
        self.v1_demucs_cb = ctk.CTkCheckBox(
            row_audio,
            text="✨ AI Demucs (ស្រង់ភ្លេង BGM)",
            variable=self.v1_demucs_var,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            fg_color="#10B981",
            checkmark_color="#FFFFFF"
        )
        self.v1_demucs_cb.pack(side="right", padx=(6, 0))

        self.v1_mute_orig_voice_var = ctk.BooleanVar(value=True)
        self.v1_mute_orig_cb = ctk.CTkCheckBox(
            row_audio,
            text="🔇 បិទសំឡេងដើម (Mute Orig)",
            variable=self.v1_mute_orig_voice_var,
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            fg_color="#10B981",
            checkmark_color="#FFFFFF"
        )
        self.v1_mute_orig_cb.pack(side="right", padx=(6, 8))

        # Row 2: Subtitle Controls & Timeline Toggle
        sub_row = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        sub_row.pack(fill="x", padx=10, pady=(2, 5))

        # CC Subtitle Toggle Button
        self.btn_cc = ctk.CTkButton(
            sub_row,
            text="💬 CC Subtitle: ON",
            width=140,
            height=26,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#10B981",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._on_toggle_cc
        )
        self.btn_cc.pack(side="left", padx=(0, 6))

        # CC Subtitle Settings Button
        self.btn_cc_settings = ctk.CTkButton(
            sub_row,
            text=self.t("toggle_cc_settings"),
            width=145,
            height=26,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#E5E7EB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._open_cc_settings_dialog
        )
        self.btn_cc_settings.pack(side="left", padx=(0, 6))

        # Copyright Check Button on Subtitle & Timeline Row (Soft Red Studio Badge)
        self.btn_check_copyright = ctk.CTkButton(
            sub_row,
            text="🛡️ ពិនិត្យ Copyright",
            width=140,
            height=26,
            fg_color="#2E181A",
            hover_color="#3F1B1E",
            border_color="#7F1D1D",
            border_width=1,
            text_color="#EF4444",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._open_copyright_scanner_dialog
        )
        self.btn_check_copyright.pack(side="left", padx=(0, 6))

        # Persistent Toggle Timeline Button on Pinned Bottom Bar
        self.btn_toggle_timeline = ctk.CTkButton(
            sub_row,
            text=self.t("toggle_timeline_hide"),
            width=135,
            height=26,
            fg_color="#262A34",
            hover_color="#323846",
            border_color="#373D4B",
            border_width=1,
            text_color="#D1D5DB",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            command=self._toggle_timeline_visibility
        )
        self.btn_toggle_timeline.pack(side="right", padx=(6, 0))
        
        def _adjust_vertical_sash():
            try:
                vh = self.vertical_paned.winfo_height()
                if vh > 260:
                    self.vertical_paned.sash_place(0, 0, max(220, vh - 192))
            except Exception:
                pass
            try:
                mw = self.middle_paned.winfo_width()
                if mw > 600:
                    self.middle_paned.sash_place(0, mw // 2, 0)
            except Exception:
                pass
        self.after(250, _adjust_vertical_sash)
        self.after(650, _adjust_vertical_sash)
        
    def _toggle_timeline_visibility(self):
        """Toggle timeline pane visibility inside vertical paned window."""
        self.timeline_visible = not getattr(self, 'timeline_visible', True)
        tr = UI_STRINGS.get(self.current_lang, UI_STRINGS["km"])
        btn_text = tr.get("toggle_timeline_hide", "🎞️ បិទ Timeline") if self.timeline_visible else tr.get("toggle_timeline_show", "🎞️ បើក Timeline")
        btn_col = "#262A34"
        btn_hcol = "#323846"

        if hasattr(self, 'btn_toggle_timeline') and self.btn_toggle_timeline:
            self.btn_toggle_timeline.configure(text=btn_text, fg_color=btn_col, hover_color=btn_hcol, border_color="#373D4B", border_width=1)

        if self.timeline_visible:
            try:
                self.vertical_paned.add(self.bottom_pane, minsize=140, height=186)
                vh = self.vertical_paned.winfo_height()
                if vh > 260:
                    self.vertical_paned.sash_place(0, 0, max(220, vh - 192))
            except Exception as e:
                print(f"[Warning] Failed to show timeline pane: {e}")
            if hasattr(self, 'timeline') and self.timeline:
                self.after(50, self.timeline.redraw)
        else:
            try:
                self.vertical_paned.forget(self.bottom_pane)
            except Exception as e:
                print(f"[Warning] Failed to hide timeline pane: {e}")

    def _open_output_or_video_folder(self):
        """Locate dubbed video file in Windows Explorer, or input video folder, or workspace folder."""
        target = ""
        if hasattr(self, 'v1_merged_video_path') and self.v1_merged_video_path and os.path.exists(self.v1_merged_video_path):
            target = self.v1_merged_video_path
        elif hasattr(self, 'v1_video_entry') and self.v1_video_entry.get().strip():
            vid = self.v1_video_entry.get().strip()
            if os.path.exists(vid):
                target = vid
        if target:
            safe_locate_file(target)
        else:
            safe_open_folder(os.path.dirname(os.path.abspath(__file__)))

    def _v1_slider_label(self, val):
        pct = int(round(val * 100))
        if pct == 0:
            txt = "0% 🔇"
        elif pct >= 100:
            txt = f"{pct}% 🔊"
        else:
            txt = f"{pct}%"
        self.v1_bg_label.configure(text=txt)
        if hasattr(self, 'timeline') and self.timeline:
            self.timeline.set_default_bgm_volume(val)

    def _open_bgm_manager(self):
        if hasattr(self, 'timeline') and self.timeline:
            self.timeline.open_bgm_volume_dialog()

    def _select_custom_bgm(self):
        filetypes = [
            ("Audio files", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"),
            ("All files", "*.*")
        ]
        chosen = filedialog.askopenfilename(title="ជ្រើសរើសឯកសារភ្លេង Background (BGM)", filetypes=filetypes)
        if chosen:
            self.custom_bgm_path = chosen
            base_n = os.path.basename(chosen)
            disp_n = base_n[:16] + "..." if len(base_n) > 18 else base_n
            self.lbl_custom_bgm.configure(text=f"🎵 {disp_n}")
            self.btn_clear_bgm.pack(side="left", padx=(2, 4))
            messagebox.showinfo("ភ្លេង Background", f"បានជ្រើសរើសភ្លេង BGM៖\n{chosen}\n\nប្រព័ន្ធនឹងប្រើប្រាស់ភ្លេងនេះជា Background Music ជំនួសសំឡេងដើម។")

    def _clear_custom_bgm(self):
        self.custom_bgm_path = ""
        self.lbl_custom_bgm.configure(text="")
        self.btn_clear_bgm.pack_forget()

    def _get_tts_base_rate(self) -> str:
        """Returns Edge-TTS speech rate percentage based on user's selected speed."""
        if hasattr(self, 'v1_voice_speed_dropdown'):
            choice = self.v1_voice_speed_dropdown.get()
            if "1.05x" in choice:
                return "+5%"
            elif "1.1x" in choice:
                return "+10%"
            elif "1.15x" in choice:
                return "+15%"
            elif "0.95x" in choice:
                return "-5%"
        return "+0%"

    def is_auto_character_mode(self) -> bool:
        """Determines if Auto Female/Male character mode is active across all UI languages"""
        if hasattr(self, 'auto_gender_var') and self.auto_gender_var.get():
            return True
        if hasattr(self, 'v1_voice_dropdown'):
            choice = self.v1_voice_dropdown.get()
            return any(k in choice for k in ["តាមតួអង្គ", "ស្រី-ប្រុស", "Auto", "自动", "Character"])
        return False

    def _on_auto_gender_toggle(self):
        tr = TRANSLATIONS.get(self.current_lang, TRANSLATIONS["km"])
        if self.auto_gender_var.get():
            self.v1_voice_dropdown.set(tr["voice_options"][0])
            self._on_main_voice_change(tr["voice_options"][0])
        else:
            self.v1_voice_dropdown.set(tr["voice_options"][1])
            self._on_main_voice_change(tr["voice_options"][1])

    def _on_main_voice_change(self, choice):
        is_auto = any(k in choice for k in ["តាមតួអង្គ", "ស្រី-ប្រុស", "Auto", "自动", "Character"])
        if hasattr(self, 'auto_gender_var'):
            self.auto_gender_var.set(is_auto)

        tr = TRANSLATIONS.get(self.current_lang, TRANSLATIONS["km"])
        male_text = tr["segment_gender_male"]
        fem_text = tr["segment_gender_female"]

        if is_auto:
            for seg in self.segments_data:
                g = seg.get('gender', 'male')
                is_fem = (g == 'female')
                w = seg.get('voice_widget')
                if w:
                    w.set(fem_text if is_fem else male_text)
                    w.configure(
                        fg_color="#BE185D" if is_fem else "#1D4ED8",
                        button_color="#9D174D" if is_fem else "#1E40AF",
                        button_hover_color="#831843" if is_fem else "#1E3A8A"
                    )
        else:
            is_fem = any(k in choice for k in ["Sreymom", "ស្រី", "Female", "女"])
            target_text = fem_text if is_fem else male_text
            for seg in self.segments_data:
                seg['gender'] = "female" if is_fem else "male"
                w = seg.get('voice_widget')
                if w:
                    w.set(target_text)
                    w.configure(
                        fg_color="#BE185D" if is_fem else "#1D4ED8",
                        button_color="#9D174D" if is_fem else "#1E40AF",
                        button_hover_color="#831843" if is_fem else "#1E3A8A"
                    )
        if hasattr(self, 'timeline'):
            self.timeline.redraw()

    def _on_player_time_update(self, sec):
        if hasattr(self, 'timeline'):
            self.timeline.set_current_time(sec)

    def update_cc_button_state(self, enabled: bool):
        lang = getattr(self, 'current_lang', 'km')
        lbl_on = "💬 CC Subtitle: ON" if lang != "zh" else "💬 CC 字幕: 开启"
        lbl_off = "💬 CC Subtitle: OFF" if lang != "zh" else "💬 CC 字幕: 关闭"
        for btn in [getattr(self, 'btn_cc', None), getattr(self.timeline, 'btn_cc', None) if hasattr(self, 'timeline') else None]:
            if btn:
                if enabled:
                    btn.configure(text=lbl_on, fg_color="#1E3A8A", hover_color="#1D4ED8", text_color="#FFFFFF")
                else:
                    btn.configure(text=lbl_off, fg_color="#374151", hover_color="#4B5563", text_color="#9CA3AF")

    def update_cc_bg_button_state(self, enabled: bool):
        if not hasattr(self, 'btn_cc_bg') or not self.btn_cc_bg:
            return
        tr = UI_STRINGS.get(self.current_lang, UI_STRINGS["km"])
        if enabled:
            lbl = tr.get("toggle_cc_bg_on", "🔲 ផ្ទៃខាងក្រោយ: បើក")
            self.btn_cc_bg.configure(text=lbl, fg_color="#0284C7", hover_color="#0369A1", text_color="#FFFFFF")
        else:
            lbl = tr.get("toggle_cc_bg_off", "🔲 ផ្ទៃខាងក្រោយ: បិទ")
            self.btn_cc_bg.configure(text=lbl, fg_color="#374151", hover_color="#4B5563", text_color="#9CA3AF")

    def _on_toggle_cc_bg(self):
        if not hasattr(self, 'video_player') or not self.video_player:
            return
        is_bg = not getattr(self.video_player, 'cc_bg_enabled', True)
        self.video_player.cc_bg_enabled = is_bg
        if is_bg and (getattr(self.video_player, 'cc_base_bg_color', '') == 'transparent' or getattr(self.video_player, 'cc_bg_opacity', 0) <= 5):
            self.video_player.cc_base_bg_color = "#000000"
            self.video_player.cc_bg_opacity = 90
        self.update_cc_bg_button_state(is_bg)
        if hasattr(self, '_cc_settings_dialog') and self._cc_settings_dialog and self._cc_settings_dialog.winfo_exists():
            if hasattr(self._cc_settings_dialog, 'sw_bg_enable'):
                if is_bg:
                    self._cc_settings_dialog.sw_bg_enable.select()
                else:
                    self._cc_settings_dialog.sw_bg_enable.deselect()
            if hasattr(self._cc_settings_dialog, 'bg_preview_badge'):
                col = getattr(self.video_player, 'cc_base_bg_color', '#000000') if is_bg else "#374151"
                self._cc_settings_dialog.bg_preview_badge.configure(
                    fg_color=col,
                    text_color="#FFFFFF" if is_bg else "#9CA3AF"
                )
        self.video_player.refresh_current_frame()

    def _on_toggle_cc_subtitles(self):
        if not hasattr(self, 'video_player') or not self.video_player:
            return
        
        # If no subtitles exist yet, offer to automatically generate subtitles
        if not self.segments_data:
            video_path = self.v1_video_entry.get().strip() if hasattr(self, 'v1_video_entry') else ""
            if video_path and os.path.exists(video_path):
                res = messagebox.askyesno(
                    "បង្កើត Subtitle ស្វ័យប្រវត្តិ",
                    "⚠️ មិនទាន់មាន Subtitle សម្រាប់វីដេអូនេះនៅឡើយទេ!\n\nតើអ្នកចង់ឱ្យ AI ស្កែនសំឡេង និងបង្កើត Subtitle ស្វ័យប្រវត្តិតាមវីដេអូឥឡូវនេះដែរឬទេ?\n(Auto-Generate Subtitles via AI Speech Recognition)"
                )
                if res:
                    self._v1_start_dubbing()
                    return
            else:
                messagebox.showinfo("Subtitle", "សូមជ្រើសរើសវីដេអូជាមុនសិន ដើម្បីបង្កើត Subtitle!")
                return

        self.video_player.cc_enabled = not self.video_player.cc_enabled
        self.update_cc_button_state(self.video_player.cc_enabled)
        if hasattr(self, 'timeline') and self.timeline:
            self.timeline.update_cc_button_state(self.video_player.cc_enabled)
        self.video_player.refresh_current_frame()

    def _on_toggle_cc(self):
        self._on_toggle_cc_subtitles()

    def _open_cc_settings_dialog(self):
        if not hasattr(self, 'video_player') or not self.video_player:
            return
        if hasattr(self, '_cc_settings_dialog') and self._cc_settings_dialog and self._cc_settings_dialog.winfo_exists():
            self._cc_settings_dialog.apply_language(self.current_lang)
            self._cc_settings_dialog.lift()
            self._cc_settings_dialog.focus_force()
            return
        self._cc_settings_dialog = SubtitleSettingsDialog(
            self,
            self.video_player,
            lang=self.current_lang,
            on_auto_generate=self._start_scan_and_translate,
            on_change_state=lambda: (
                self.update_cc_button_state(self.video_player.cc_enabled),
                self.update_cc_bg_button_state(getattr(self.video_player, 'cc_bg_enabled', True)),
                self.timeline.update_cc_button_state(self.video_player.cc_enabled) if hasattr(self, 'timeline') and self.timeline else None
            )
        )

    def _on_player_play_state_change(self, is_playing: bool):
        if hasattr(self, 'timeline'):
            self.timeline.set_play_state(is_playing)

    def _on_timeline_seek(self, sec):
        if hasattr(self, 'video_player'):
            self.video_player.seek(sec)

    def _on_timeline_clip_click(self, clip_idx):
        if 0 <= clip_idx < len(self.segments_data):
            seg = self.segments_data[clip_idx]
            if hasattr(self, 'video_player'):
                self.video_player.seek(seg['start'])
            w = seg.get('widget')
            txt = w.get().strip() if w else ""
            if txt:
                vw = seg.get('voice_widget')
                if vw and any(k in vw.get() for k in ["ស្រី", "Female", "女", "Sreymom"]):
                    v_name = "km-KH-SreymomNeural"
                elif vw and any(k in vw.get() for k in ["ប្រុស", "Male", "男", "Piseth"]):
                    v_name = "km-KH-PisethNeural"
                else:
                    v_choice = self.v1_voice_dropdown.get()
                    v_name = "km-KH-SreymomNeural" if any(k in v_choice for k in ["ស្រី", "Female", "女", "Sreymom"]) else "km-KH-PisethNeural"
                self._preview_single_segment(txt, v_name, clip_idx)
            if w and hasattr(w, 'focus_set'):
                try:
                    w.focus_set()
                except Exception:
                    pass

    def _on_timeline_delete_dialogue(self, idx: int):
        """Handle dialogue clip deleted directly from DubbingTimeline."""
        if 0 <= idx < len(self.segments_data):
            seg = self.segments_data.pop(idx)
            f = seg.get('frame')
            if f and hasattr(f, 'destroy'):
                try:
                    f.destroy()
                except Exception:
                    pass
            self._renumber_segment_cards()
            if hasattr(self, 'video_player'):
                self.video_player.set_subtitles(self.segments_data)
                self.video_player.refresh_current_frame()

    def _renumber_segment_cards(self):
        """Renumber subtitle editor cards sequentially after a segment deletion."""
        for i, s in enumerate(self.segments_data):
            lbl = s.get('lbl_orig')
            if lbl and hasattr(lbl, 'configure'):
                t_str = f"[{format_time(s['start'])} - {format_time(s['end'])}]"
                lbl.configure(text=f"#{i+1} {t_str} {self.t('segment_orig_prefix')}{s.get('orig', '')}")

    def _browse_v1_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[("Video Files", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All Files", "*.*")]
        )
        if file_path:
            self.v1_video_entry.delete(0, "end")
            self.v1_video_entry.insert(0, file_path)
            self.video_info = get_video_info(file_path)
            dur = self.video_info.get("duration", 0.0) if self.video_info else 0.0
            if hasattr(self, 'video_player'):
                self.video_player.load_video(file_path)
            if hasattr(self, 'timeline'):
                if dur > 0:
                    self.timeline.set_duration(dur)
                self.timeline.set_video_name(os.path.basename(file_path))

    def _remove_current_video(self):
        """Unload and remove current video from player, inputs, and workspace."""
        current_vid = self.v1_video_entry.get().strip() if hasattr(self, 'v1_video_entry') else ""
        has_player_video = bool(getattr(self.video_player, 'video_path', '')) if hasattr(self, 'video_player') else False
        
        if not current_vid and not has_player_video:
            messagebox.showinfo(
                self.t("notice_title"),
                "មិនមានវីដេអូនៅក្នុងកម្មវិធីសម្រាប់ដកចេញទេ! (No video loaded)",
                parent=self
            )
            return

        clear_all = False
        if self.segments_data:
            choice = messagebox.askyesnocancel(
                "ដកវីដេអូចេញ",
                "🎬 តើអ្នកចង់ដកវីដេអូចេញបែបណា?\n\n"
                "• ចុច 'Yes' (បាទ/ចាស)៖ សម្អាតទាំងអស់ (ដកវីដេអូ + ជម្រះ Subtitle ចាស់ ដើម្បីចាប់ផ្ដើមវីដេអូថ្មី)\n"
                "• ចុច 'No' (ទេ)៖ ដកតែវីដេអូចេញប៉ុណ្ណោះ (រក្សាទុក Subtitle និងសម្លេងដែលបានបកប្រែ)\n"
                "• ចុច 'Cancel' (បោះបង់)៖ មិនធ្វើអ្វីទាំងអស់",
                parent=self
            )
            if choice is None:
                return
            clear_all = (choice is True)
        else:
            if not messagebox.askyesno(
                "បញ្ជាក់ការដកវីដេអូ",
                "តើអ្នកពិតជាចង់ដកវីដេអូនេះចេញពីកម្មវិធីមែនទេ?\n(Are you sure you want to remove this video?)",
                parent=self
            ):
                return

        # 1. Stop audio preview if playing
        if hasattr(self, 'current_playing_widget'):
            self.current_playing_widget = None
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

        # 2. Unload video in video player
        if hasattr(self, 'video_player'):
            self.video_player.unload_video()

        # 3. Clear entry and video metadata
        if hasattr(self, 'v1_video_entry'):
            self.v1_video_entry.delete(0, "end")
        self.video_info = {}

        # 4. Clear timeline video name and clips if full reset
        if hasattr(self, 'timeline'):
            self.timeline.set_video_name("")
            if clear_all:
                self.timeline.set_clips([])
                self.timeline.set_duration(60.0)
            self.timeline.set_current_time(0.0)

        # 5. Clear export result displays
        if hasattr(self, 'v1_result_path_entry'):
            self.v1_result_path_entry.delete(0, "end")
        if hasattr(self, 'v1_result_info_label'):
            self.v1_result_info_label.configure(
                text=self.t("result_preview_title"),
                text_color="#94A3B8"
            )
        if hasattr(self, 'v1_thumb_label'):
            self.v1_thumb_label.configure(image=None, text="📺 គ្មានរូបភាព")
            self.v1_thumb_label.image = None
        if hasattr(self, 'v1_play_video_btn'):
            self.v1_play_video_btn.configure(state="disabled")

        # 6. Reset paths
        self.v1_merged_video_path = ""
        self.extracted_audio_path = ""
        self.generated_master_audio = ""

        # 7. If full reset selected, clear segments and disable steps
        if clear_all:
            self.segments_data.clear()
            if hasattr(self, 'scroll_frame'):
                for w in self.scroll_frame.winfo_children():
                    w.destroy()
            if hasattr(self, 'v1_extract_btn'):
                self.v1_extract_btn.configure(state="normal")
            if hasattr(self, 'v1_dub_voice_btn'):
                self.v1_dub_voice_btn.configure(state="disabled")
            if hasattr(self, 'v1_export_btn'):
                self.v1_export_btn.configure(state="disabled")
            if hasattr(self, 'v1_retranslate_all_btn'):
                self.v1_retranslate_all_btn.configure(state="disabled")
            if hasattr(self, 'v1_regen_video_btn'):
                self.v1_regen_video_btn.configure(state="disabled")

        # 8. Reset progress & status
        if hasattr(self, 'v1_progress_bar'):
            self.v1_progress_bar.set(0.0)
        if hasattr(self, 'v1_status_label'):
            self.v1_status_label.configure(
                text="✅ បានដកវីដេអូចេញរួចរាល់! សូមជ្រើសរើសវីដេអូថ្មីដើម្បីបន្ត។",
                text_color="#38BDF8"
            )

    # Step 1: Scan and Translate Video Subtitles
    def _start_scan_and_translate(self):
        video_path = self.v1_video_entry.get().strip()
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror("កំហុស", "សូមជ្រើសរើសវីដេអូដែលត្រឹមត្រូវ!")
            return
            
        if hasattr(self, 'video_player') and self.video_player.video_path != video_path:
            self.video_player.load_video(video_path)
        if hasattr(self, 'timeline'):
            self.timeline.set_video_name(os.path.basename(video_path))
            
        self.video_info = get_video_info(video_path)
        self.v1_extract_btn.configure(state="disabled")
        if hasattr(self, 'v1_dub_voice_btn'):
            self.v1_dub_voice_btn.configure(state="disabled")
        if hasattr(self, 'v1_export_btn'):
            self.v1_export_btn.configure(state="disabled")
        if hasattr(self, 'v1_regen_video_btn'):
            self.v1_regen_video_btn.configure(state="disabled")
        self.v1_retranslate_all_btn.configure(state="disabled")
        
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.segments_data.clear()
        
        def run():
            try:
                if not self.temp_dir or not os.path.exists(self.temp_dir):
                    self.temp_dir = tempfile.mkdtemp(prefix="dubbing_editor_")
                    
                self._v1_update_status("1/2 កំពុងទាញយកសំឡេងចេញពីវីដេអូ...", 0.15)
                self.extracted_audio_path = extract_audio_from_video(video_path, self.temp_dir)
                
                # Preload audio and update Timeline duration and waveform
                orig_full_audio = None
                try:
                    orig_full_audio = AudioSegment.from_file(self.extracted_audio_path)
                    if hasattr(self, 'timeline') and orig_full_audio:
                        self.timeline.set_duration(len(orig_full_audio) / 1000.0)
                        self.timeline.load_audio_waveform(self.extracted_audio_path)
                except Exception as e:
                    print(f"[Warning] Loading audio: {e}")

                model_name = self.v1_whisper_dropdown.get()
                self._v1_update_status(f"2/2 កំពុងស្កែន និងបកប្រែជាភាសាខ្មែរ (Whisper: {model_name})...", 0.35)
                
                model = whisper.load_model(model_name)
                result = model.transcribe(self.extracted_audio_path, task="transcribe")
                raw_segments = result.get("segments", [])
                
                g_key = self.get_current_gemini_key()
                use_g = self.is_gemini_enabled()
                engine_name = "Gemini 2.5 Flash (Dubbing)" if (use_g and g_key) else "Google Translate"
                
                # Voice Mode: Single unified voice or auto character detection
                is_auto_gender = self.is_auto_character_mode()
                main_v_choice = self.v1_voice_dropdown.get()
                if any(k in main_v_choice for k in ["Sreymom", "ស្រី", "Female", "女"]) and not is_auto_gender:
                    unified_gender = "female"
                else:
                    unified_gender = "male"
                
                # 1. Fast preliminary preparation of segments & gender classification
                valid_segments = []
                for idx, seg in enumerate(raw_segments):
                    text_orig = seg['text'].strip()
                    if not text_orig:
                        continue
                    start_ms = max(0, int(seg['start'] * 1000))
                    end_ms = max(start_ms + 100, int(seg['end'] * 1000))
                    if is_auto_gender and orig_full_audio:
                        seg_chunk = orig_full_audio[start_ms:min(len(orig_full_audio), end_ms)]
                        detected_gender = detect_voice_gender(seg_chunk, text_orig)
                    else:
                        detected_gender = unified_gender
                    valid_segments.append({
                        "index": idx,
                        "start": seg['start'],
                        "end": seg['end'],
                        "orig": text_orig,
                        "gender": detected_gender,
                        "khmer": ""
                    })

                total = len(valid_segments)
                translated_list = []
                if total > 0:
                    from concurrent.futures import ThreadPoolExecutor, as_completed
                    completed_trans = 0
                    trans_map = {}
                    def _trans_item(item):
                        try:
                            res = translate_text(item['orig'], source_lang="auto", target_lang="km", api_key=g_key, use_gemini=use_g)
                            return item['index'], clean_translation_text(res, item['orig'])
                        except Exception as ex:
                            print(f"[Translation Warning] seg {item['index']}: {ex}")
                            return item['index'], clean_translation_text(item['orig'])

                    with ThreadPoolExecutor(max_workers=8) as executor:
                        future_map = {executor.submit(_trans_item, itm): itm for itm in valid_segments}
                        for fut in as_completed(future_map):
                            idx_done, trans_res = fut.result()
                            trans_map[idx_done] = trans_res
                            completed_trans += 1
                            prog = 0.35 + (0.6 * (completed_trans / max(total, 1)))
                            self._v1_update_status(f"⚡ កំពុងបកប្រែជាភាសាខ្មែរល្បឿនលឿន ({completed_trans}/{total}) តាម {engine_name}...", prog)

                    for itm in valid_segments:
                        itm['khmer'] = trans_map.get(itm['index'], itm['orig'])
                        translated_list.append(itm)
                    
                self.after(0, lambda: self._populate_segment_ui(translated_list))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._v1_on_error(err))

        threading.Thread(target=run, daemon=True).start()

    def _populate_segment_ui(self, segments_list):
        self.v1_extract_btn.configure(state="normal")
        if hasattr(self, 'v1_dub_voice_btn'):
            self.v1_dub_voice_btn.configure(state="normal")
        if hasattr(self, 'v1_export_btn'):
            self.v1_export_btn.configure(state="normal")
        self.v1_retranslate_all_btn.configure(state="normal")
        self.v1_progress_bar.set(1.0)
        self.v1_status_label.configure(
            text=f"✅ ស្កែន និងបកប្រែបាន {len(segments_list)} ប្រយោគ! អ្នកអាចកែសម្រួលអត្ថបទខ្មែរខាងក្រោម រួចចុច '2. បង្កើតសំឡេងរួម'",
            text_color="#10B981"
        )
        
        if not segments_list:
            lbl = ctk.CTkLabel(self.scroll_frame, text="មិនមានសំឡេងនិយាយនៅក្នុងវីដេអូនេះទេ!", text_color="#EF4444")
            lbl.pack(pady=20)
            return

        is_auto = self.is_auto_character_mode()
        voice_raw = self.v1_voice_dropdown.get()
        single_is_fem = (any(k in voice_raw for k in ["Sreymom", "ស្រី", "Female", "女"]) and not is_auto)

        female_count = sum(1 for item in segments_list if (item.get('gender') == 'female' if is_auto else single_is_fem))
        male_count = len(segments_list) - female_count

        # Visual Character Voice Summary Banner
        summary_card = ctk.CTkFrame(self.scroll_frame, fg_color="#182334", border_color="#334155", border_width=1, corner_radius=6)
        summary_card.pack(fill="x", padx=5, pady=(2, 6))
        summary_row = ctk.CTkFrame(summary_card, fg_color="transparent")
        summary_row.pack(fill="x", padx=10, pady=5)
        
        mode_text = "🎭 ស្វ័យប្រវត្តិតាមតួអង្គ (Auto Character)" if is_auto else ("👩 សំឡេងស្រីសុទ្ធ" if single_is_fem else "👨 សំឡេងប្រុសសុទ្ធ")
        ctk.CTkLabel(
            summary_row,
            text=f"🎙️ របៀបសំឡេង: {mode_text}",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
            text_color="#9CA3AF"
        ).pack(side="left")

        badges_frame = ctk.CTkFrame(summary_row, fg_color="transparent")
        badges_frame.pack(side="right")
        
        ctk.CTkLabel(
            badges_frame,
            text=f"👨 ប្រុស: {male_count}",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            text_color="#93C5FD",
            fg_color="#1E293B",
            corner_radius=4,
            padx=8, pady=2
        ).pack(side="left", padx=3)

        ctk.CTkLabel(
            badges_frame,
            text=f"👩 ស្រី: {female_count}",
            font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
            text_color="#FBCFE8",
            fg_color="#2E1B26",
            corner_radius=4,
            padx=8, pady=2
        ).pack(side="left", padx=3)

        for idx, item in enumerate(segments_list):
            seg_frame = ctk.CTkFrame(self.scroll_frame, fg_color="#181A20", border_color="#2E333D", border_width=1, corner_radius=6)
            seg_frame.pack(fill="x", padx=4, pady=3)
            
            t_str = f"[{format_time(item['start'])} - {format_time(item['end'])}]"
            top_line = ctk.CTkFrame(seg_frame, fg_color="transparent")
            top_line.pack(fill="x", padx=8, pady=(4, 2))
            
            lbl_orig = ctk.CTkLabel(
                top_line,
                text=f"#{idx+1} {t_str} {self.t('segment_orig_prefix')}{item['orig']}",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
                text_color="#9CA3AF"
            )
            lbl_orig.pack(side="left")
            
            # Voice Gender Selector for this segment
            if is_auto:
                is_fem = (item.get('gender') == 'female')
            else:
                is_fem = single_is_fem
            item['gender'] = "female" if is_fem else "male"
            gender_choices = [self.t("segment_gender_male"), self.t("segment_gender_female")]
            default_v_text = gender_choices[1] if is_fem else gender_choices[0]
            seg_gender = "female" if is_fem else "male"

            voice_menu = ctk.CTkOptionMenu(
                top_line,
                values=gender_choices,
                width=135,
                height=24,
                fg_color="#262A34",
                button_color="#1E2128",
                button_hover_color="#323846",
                text_color="#E5E7EB",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11)
            )
            voice_menu.set(default_v_text)
            def _make_gender_handler(v_menu, s_idx):
                def _h(choice):
                    is_f = any(k in choice for k in ["ស្រី", "Female", "女"])
                    if s_idx < len(self.segments_data):
                        self.segments_data[s_idx]['gender'] = "female" if is_f else "male"
                    if hasattr(self, 'timeline'):
                        self.timeline.redraw()
                return _h
            voice_menu.configure(command=_make_gender_handler(voice_menu, idx))
            voice_menu.pack(side="right")

            edit_line = ctk.CTkFrame(seg_frame, fg_color="transparent")
            edit_line.pack(fill="x", padx=8, pady=(0, 5))
            
            kh_font = ctk.CTkFont(family=KHMER_FONT_NAME, size=13)
            kh_sv = tk.StringVar(value=clean_translation_text(item['khmer']))
            kh_entry = ctk.CTkEntry(
                edit_line,
                font=kh_font,
                height=30,
                textvariable=kh_sv,
                fg_color="#12141A",
                border_color="#2E333D",
                border_width=1,
                text_color="#F3F4F6"
            )
            try:
                kh_entry._entry.configure(font=(KHMER_FONT_NAME, 13))
            except Exception:
                pass
            kh_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
            attach_context_menu(kh_entry, lambda: self.current_lang)

            is_healing_seg = False
            def _on_kh_change(*args):
                nonlocal is_healing_seg
                if is_healing_seg:
                    return
                val = kh_sv.get()
                if 'áž' in val or 'á' in val or '\xe1' in val:
                    fixed = restore_mojibake(val)
                    if fixed != val:
                        is_healing_seg = True
                        kh_sv.set(fixed)
                        is_healing_seg = False
                        val = fixed
                item['khmer'] = val
                if hasattr(self, '_timeline_deb_id') and self._timeline_deb_id:
                    try:
                        self.after_cancel(self._timeline_deb_id)
                    except Exception:
                        pass
                if hasattr(self, 'timeline'):
                    self._timeline_deb_id = self.after(200, self.timeline.redraw)
                if hasattr(self, 'video_player'):
                    self.video_player.refresh_current_frame()

            kh_sv.trace_add("write", _on_kh_change)

            # Ensure internal entry bindings also support select-all and paste
            inner_ent = kh_entry._entry if hasattr(kh_entry, '_entry') else kh_entry
            def _select_all_kh(e):
                inner_ent.select_range(0, 'end')
                inner_ent.icursor('end')
                return "break"
            inner_ent.bind("<Control-a>", _select_all_kh)
            inner_ent.bind("<Control-A>", _select_all_kh)
            
            btn_retrans = ctk.CTkButton(
                edit_line,
                text=self.t("segment_retrans_btn"),
                width=100,
                height=26,
                fg_color="#262A34",
                hover_color="#323846",
                border_color="#373D4B",
                border_width=1,
                text_color="#D1D5DB",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11),
                command=lambda e=kh_entry, o=item['orig']: self._single_retranslate(e, o)
            )
            btn_retrans.pack(side="right", padx=(0, 5))

            btn_prev = ctk.CTkButton(
                edit_line,
                text=self.t("segment_preview_btn"),
                width=100,
                height=26,
                fg_color="#262A34",
                hover_color="#323846",
                border_color="#373D4B",
                border_width=1,
                text_color="#10B981",
                font=ctk.CTkFont(family=KHMER_FONT_NAME, size=11, weight="bold"),
                command=lambda e=kh_entry, vm=voice_menu, i=idx, st=item['start']: (
                    self.video_player.seek(st) if hasattr(self, 'video_player') else None,
                    self._preview_single_segment(
                        e.get(),
                        ("km-KH-SreymomNeural" if any(k in vm.get() for k in ["ស្រី", "Female", "女"]) else "km-KH-PisethNeural"),
                        i
                    )
                )
            )
            btn_prev.pack(side="right")
            
            self.segments_data.append({
                "start": item['start'],
                "end": item['end'],
                "orig": item['orig'],
                "khmer": item['khmer'],
                "widget": kh_entry,
                "voice_widget": voice_menu,
                "lbl_orig": lbl_orig,
                "btn_retrans": btn_retrans,
                "btn_prev": btn_prev,
                "gender": seg_gender,
                "frame": seg_frame,
                "tts_path": ""
            })
            
        if hasattr(self, 'v1_regen_video_btn'):
            self.v1_regen_video_btn.configure(state="normal")

        # Update Timeline Clips & Video Player Subtitles
        if hasattr(self, 'timeline'):
            if segments_list:
                max_end = max([s['end'] for s in segments_list])
                self.timeline.set_duration(max_end + 3.0)
            self.timeline.set_clips(self.segments_data)
        if hasattr(self, 'video_player'):
            self.video_player.set_subtitles(self.segments_data)

        # Auto Dubbing Pipeline: Automatically proceed to voice generation & merging
        if getattr(self, 'auto_pipeline_var', None) and self.auto_pipeline_var.get():
            self.v1_status_label.configure(
                text=f"✅ បកប្រែបាន {len(segments_list)} ប្រយោគ! កំពុងបន្តបង្កើតសំឡេង និងបញ្ចូលក្នុងវីដេអូដោយស្វ័យប្រវត្តិ...",
                text_color="#10B981"
            )
            self.after(300, lambda: self._start_generate_all_voice(auto_merge=True))
        else:
            self.v1_status_label.configure(
                text=f"✅ ស្កែន និងបកប្រែបាន {len(segments_list)} ប្រយោគ! អ្នកអាចពិនិត្យកែសម្រួលអក្សរខ្មែរខាងក្រោម រួចចុច '🎙️ ២. បញ្ចូលសំឡេង' ឬ '📤 ៣. Export វីដេអូ'",
                text_color="#10B981"
            )

    def _single_retranslate(self, entry_widget, orig_text):
        g_key = self.get_current_gemini_key()
        use_g = self.is_gemini_enabled()
        def run():
            trans = clean_translation_text(translate_text(orig_text, source_lang="auto", target_lang="km", api_key=g_key, use_gemini=use_g))
            self.after(0, lambda: [entry_widget.delete(0, "end"), entry_widget.insert(0, trans)])
        threading.Thread(target=run, daemon=True).start()

    def _retranslate_all_segments(self):
        if not self.segments_data:
            return
        g_key = self.get_current_gemini_key()
        use_g = self.is_gemini_enabled()
        engine_name = "Gemini 2.5 Flash" if (use_g and g_key) else "Google Translate"
        def run():
            total = len(self.segments_data)
            completed_retrans = 0
            from concurrent.futures import ThreadPoolExecutor, as_completed
            def _retrans_one(idx, seg):
                try:
                    trans = clean_translation_text(translate_text(seg['orig'], source_lang="auto", target_lang="km", api_key=g_key, use_gemini=use_g), seg['orig'])
                except Exception as ex:
                    print(f"[Retranslate Error] seg {idx}: {ex}")
                    trans = seg['orig']
                return idx, seg['widget'], trans

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(_retrans_one, i, s) for i, s in enumerate(self.segments_data)]
                for fut in as_completed(futures):
                    _, widget, t_text = fut.result()
                    completed_retrans += 1
                    self.after(0, lambda w=widget, t=t_text: [w.delete(0, "end"), w.insert(0, t)])
                    self._v1_update_status(f"⚡ កំពុងបកប្រែឡើងវិញល្បឿនលឿន ({completed_retrans}/{total}) តាម {engine_name}...", completed_retrans / max(total, 1))

            self._v1_update_status(f"✅ បកប្រែឡើងវិញទាំងអស់តាម {engine_name} រួចរាល់!", 1.0)

        threading.Thread(target=run, daemon=True).start()

    def _preview_single_segment(self, text, voice, index):
        cleaned_text = clean_tts_text(text)
        if not cleaned_text.strip():
            return
        
        base_rate = self._get_tts_base_rate()
        def run():
            try:
                out_p = os.path.join(self.temp_dir, f"preview_seg_{index}_{int(time.time())}.mp3")
                generate_tts(cleaned_text, voice, out_p, rate=base_rate)
                play_audio_file(out_p)
            except Exception as e:
                print(f"Preview seg error: {e}")
                err_s = str(e)
                if "getaddrinfo failed" in err_s or "speech.platform.bing.com" in err_s:
                    self.after(0, lambda: messagebox.showwarning(
                        "បញ្ហាតភ្ជាប់អ៊ីនធឺណិត", 
                        "មិនអាចទាញសំឡេងស្តាប់បានទេ ដោយសារបញ្ហាតភ្ជាប់អ៊ីនធឺណិត (getaddrinfo failed)។ សូមពិនិត្យមើល Wi-Fi របស់អ្នក រួចសាកល្បងម្ដងទៀត។"
                    ))

        threading.Thread(target=run, daemon=True).start()

    def _generate_voices_sync_worker(self, on_progress=None, on_done=None, on_error=None):
        try:
            if not self.temp_dir or not os.path.exists(self.temp_dir):
                self.temp_dir = tempfile.mkdtemp(prefix="dubbing_editor_")
            voice_mode = self.v1_voice_dropdown.get()
            is_auto_mode = self.is_auto_character_mode()
            single_voice = "km-KH-SreymomNeural" if (any(k in voice_mode for k in ["Sreymom", "ស្រី", "Female", "女"]) and not is_auto_mode) else "km-KH-PisethNeural"
            base_rate = self._get_tts_base_rate()
            
            segments_to_process = []
            for idx, seg in enumerate(self.segments_data):
                try:
                    kh_text = clean_tts_text(seg['widget'].get().strip())
                except Exception:
                    kh_text = ""
                vw = seg.get('voice_widget')
                if vw:
                    seg_v = "km-KH-SreymomNeural" if any(k in vw.get() for k in ["ស្រី", "Female", "女", "Sreymom"]) else "km-KH-PisethNeural"
                elif is_auto_mode:
                    seg_v = "km-KH-SreymomNeural" if seg.get('gender') == 'female' else "km-KH-PisethNeural"
                else:
                    seg_v = single_voice
                segments_to_process.append({
                    'index': idx,
                    'text': kh_text,
                    'voice': seg_v,
                    'start_ms': int(seg['start'] * 1000),
                    'end_ms': int(seg['end'] * 1000),
                })

            if on_progress:
                on_progress("កំពុងរៀបចំសំឡេងដើម និងដំណើរការ AI Demucs...", 0.1)
            else:
                self._v1_update_status("កំពុងរៀបចំសំឡេងដើម និងដំណើរការ AI Demucs...", 0.1)

            # Start AI Demucs BGM isolation concurrently with Voice Dubbing
            video_path = self.v1_video_entry.get().strip() if hasattr(self, 'v1_video_entry') else ""
            use_demucs = bool(self.v1_demucs_var.get()) if hasattr(self, 'v1_demucs_var') else True
            demucs_container = [None]
            demucs_thread = None

            if use_demucs and video_path and os.path.exists(video_path):
                def _demucs_task():
                    try:
                        hq_audio = extract_high_quality_audio(video_path, self.temp_dir)
                        if hq_audio and os.path.exists(hq_audio):
                            no_voc = extract_demucs_bgm(hq_audio, self.temp_dir)
                            if no_voc and os.path.exists(no_voc):
                                demucs_container[0] = no_voc
                    except Exception as ex_dem:
                        print(f"[Demucs Extraction Error]: {ex_dem}")

                demucs_thread = threading.Thread(target=_demucs_task, daemon=True)
                demucs_thread.start()

            orig_audio = AudioSegment.from_file(self.extracted_audio_path).set_frame_rate(44100).set_channels(2)
            total_duration_ms = len(orig_audio)
            dubbed_audio = AudioSegment.silent(duration=total_duration_ms, frame_rate=44100).set_channels(2)

            total = len(segments_to_process)
            failed_segments = []
            tts_tasks = []

            # 1. Pre-calculate durations and check cached TTS audio
            for i, item in enumerate(segments_to_process):
                kh_edited_text = item['text']
                start_ms = item['start_ms']
                end_ms = item['end_ms']
                base_dur_ms = max(500, end_ms - start_ms)

                if i + 1 < total:
                    next_start_ms = segments_to_process[i + 1]['start_ms']
                    gap_ms = next_start_ms - end_ms
                    if gap_ms > 0:
                        available_dur_ms = base_dur_ms + max(0, gap_ms - 150)
                    else:
                        available_dur_ms = max(base_dur_ms, next_start_ms - start_ms - 50)
                else:
                    available_dur_ms = max(base_dur_ms, total_duration_ms - start_ms)

                item['target_dur_ms'] = max(base_dur_ms, available_dur_ms)
                
                if kh_edited_text:
                    text_hash = hashlib.md5((kh_edited_text + item['voice'] + base_rate).encode('utf-8')).hexdigest()[:8]
                    item['seg_tts_path'] = os.path.join(self.temp_dir, f"master_tts_{item['index']}_{text_hash}.mp3")
                    if not (os.path.exists(item['seg_tts_path']) and os.path.getsize(item['seg_tts_path']) > 200):
                        tts_tasks.append(item)
                else:
                    item['seg_tts_path'] = None

            # 2. Fast Parallel Edge-TTS Generation (Multi-Threaded 6x-10x Speedup)
            completed_count = total - len(tts_tasks)
            def _download_tts_item(itm):
                try:
                    generate_tts(itm['text'], itm['voice'], itm['seg_tts_path'], rate=base_rate)
                    return (itm['index'], True, None)
                except Exception as t_err:
                    return (itm['index'], False, t_err)

            if tts_tasks:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_map = {executor.submit(_download_tts_item, itm): itm for itm in tts_tasks}
                    for fut in as_completed(future_map):
                        idx, success, err = fut.result()
                        completed_count += 1
                        prog = 0.1 + (0.75 * (completed_count / max(total, 1)))
                        msg = f"⚡ កំពុងបង្កើតសំឡេងខ្មែរល្បឿនលឿន ({completed_count}/{total})..."
                        if on_progress:
                            on_progress(msg, prog)
                        else:
                            self._v1_update_status(msg, prog)
                        if not success:
                            failed_segments.append(idx + 1)
            else:
                if on_progress:
                    on_progress(f"⚡ សំឡេងខ្មែរទាំងអស់មានស្រាប់ក្នុង Cache ({total}/{total})...", 0.85)

            # 3. Fast Parallel Audio Alignment & Speed Adjustment
            if on_progress:
                on_progress("កំពុងតម្រៀបសំឡេង និងលៃលកល្បឿនលឿន...", 0.88)
            else:
                self._v1_update_status("កំពុងតម្រៀបសំឡេង និងលៃលកល្បឿនលឿន...", 0.88)

            def _align_seg(item):
                target_dur_ms = item['target_dur_ms']
                seg_tts_path = item.get('seg_tts_path')
                seg_audio = None
                if seg_tts_path and os.path.exists(seg_tts_path) and os.path.getsize(seg_tts_path) > 100:
                    try:
                        seg_audio = AudioSegment.from_file(seg_tts_path).set_frame_rate(44100).set_channels(2)
                    except Exception:
                        seg_audio = None

                if seg_audio is None:
                    seg_audio = AudioSegment.silent(duration=int(target_dur_ms), frame_rate=44100).set_channels(2)

                aligned_seg_audio = adjust_audio_speed(seg_audio, target_dur_ms).set_frame_rate(44100).set_channels(2)
                if aligned_seg_audio.dBFS > -90:
                    aligned_seg_audio = aligned_seg_audio.apply_gain(-12.0 - aligned_seg_audio.dBFS)
                return (aligned_seg_audio, item['start_ms'])

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as align_exec:
                aligned_audio_tuples = list(align_exec.map(_align_seg, segments_to_process))

            # 4. Lightning-Fast Timeline Audio Stitching (NumPy buffer)
            dubbed_audio = stitch_audio_segments_fast(aligned_audio_tuples, total_duration_ms, frame_rate=44100, channels=2)

            if dubbed_audio.dBFS > -90 and dubbed_audio.dBFS < -14:
                dubbed_audio = dubbed_audio.apply_gain(min(12.0, -12.0 - dubbed_audio.dBFS))

            master_path = os.path.join(self.temp_dir, "master_dubbed_voice.wav")
            dubbed_audio.export(master_path, format="wav", parameters=["-ar", "44100", "-ac", "2"])
            self.generated_master_audio = master_path

            # Keep Demucs running asynchronously in background without blocking Khmer voice preview
            self.demucs_thread = demucs_thread
            self.demucs_container = demucs_container
            if demucs_container[0] and os.path.exists(demucs_container[0]):
                self.isolated_bgm_path = demucs_container[0]
                print(f"[Demucs] BGM extraction completed and cached: {self.isolated_bgm_path}")


            if failed_segments:
                msg_fail = f"⚠️ បានបង្កើតសំឡេងស្ទើរតែទាំងអស់ ប៉ុន្តែមានល្បះចំនួន {len(failed_segments)} មិនអាចទាញយកបានដោយសារបញ្ហាអ៊ីនធឺណិត (Edge-TTS)។"
                self.after(500, lambda: messagebox.showwarning("ការជូនដំណឹងសំឡេង", msg_fail))

            if on_done:
                on_done()
        except Exception as e:
            err = str(e)
            if on_error:
                on_error(err)
            else:
                self.after(0, lambda: self._v1_on_error(err))

    # Step 2: Generate all combined Audio with edited segments
    def _start_generate_all_voice(self, auto_merge=False):
        if not self.segments_data:
            return
            
        if hasattr(self, 'v1_extract_btn'):
            self.v1_extract_btn.configure(state="disabled")
        if hasattr(self, 'v1_dub_voice_btn'):
            self.v1_dub_voice_btn.configure(state="disabled")
        if hasattr(self, 'v1_export_btn'):
            self.v1_export_btn.configure(state="disabled")
        if hasattr(self, 'v1_regen_video_btn'):
            self.v1_regen_video_btn.configure(state="disabled")

        def _prog(m, p):
            self._v1_update_status(m, p)

        def _done():
            self.after(0, lambda: self._on_voice_generated_success(auto_merge=auto_merge))

        def _err(e):
            self.after(0, lambda: self._v1_on_error(e))

        threading.Thread(target=lambda: self._generate_voices_sync_worker(_prog, _done, _err), daemon=True).start()

    def _on_voice_generated_success(self, auto_merge=False):
        if hasattr(self, 'v1_extract_btn'):
            self.v1_extract_btn.configure(state="normal")
        if hasattr(self, 'v1_dub_voice_btn'):
            self.v1_dub_voice_btn.configure(state="normal")
        if hasattr(self, 'v1_export_btn'):
            self.v1_export_btn.configure(state="normal")
        if hasattr(self, 'v1_regen_video_btn'):
            self.v1_regen_video_btn.configure(state="normal")
        self.v1_progress_bar.set(1.0)
        
        if hasattr(self, 'video_player') and self.generated_master_audio and os.path.exists(self.generated_master_audio):
            self.video_player.set_khmer_audio(self.generated_master_audio)
            self.video_player.switch_audio_mode("khmer")

        if auto_merge:
            self.v1_status_label.configure(
                text="🎉 បង្កើតសំឡេងរួមរួចរាល់! កំពុងបើកផ្ទាំង Export វីដេអូ...",
                text_color="#10B981"
            )
            self.after(300, self._open_export_dialog)
        else:
            self.v1_status_label.configure(
                text="🎉 បញ្ចូលសំឡេងខ្មែររួចរាល់! អ្នកអាចចាក់ស្តាប់សាកល្បង ឬចុច '📤 ៣. Export វីដេអូ' ដើម្បីកំណត់ Quality និងទាញយកវីដេអូ",
                text_color="#10B981"
            )

    def _play_master_audio(self):
        if self.generated_master_audio and os.path.exists(self.generated_master_audio):
            play_audio_file(self.generated_master_audio)

    # Step 3: Direct 1-Click Video Export Engine
    def _open_export_dialog(self):
        video_path = self.v1_video_entry.get().strip() if hasattr(self, 'v1_video_entry') else ""
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror(self.t("warning_title"), "សូមជ្រើសរើសវីដេអូជាមុនសិន!")
            return
        if not self.segments_data:
            messagebox.showerror(self.t("warning_title"), "មិនទាន់មានអត្ថបទសម្រាយរឿង / Subtitle នៅឡើយទេ! សូមចុច '🔍 ១. ស្កែន & បកប្រែ' ជាមុនសិន។")
            return
        if not getattr(self, 'generated_master_audio', None) or not os.path.exists(self.generated_master_audio):
            messagebox.showwarning("ការជូនដំណឹង", "សូមចុច '🎙️ ២. បញ្ចូលសំឡេង' ជាមុនសិន មុននឹង Export វីដេអូ!")
            return

        base_dir = os.path.dirname(video_path)
        base_name, _ = os.path.splitext(os.path.basename(video_path))
        default_name = f"{base_name}_Dubbed_Khmer.mp4"

        # Ask user where to save the output video in 1 step
        out_path = filedialog.asksaveasfilename(
            title="ជ្រើសរើសកន្លែងរក្សាទុកវីដេអូ Export",
            initialdir=base_dir,
            initialfile=default_name,
            filetypes=[("MP4 Video", "*.mp4"), ("All files", "*.*")],
            parent=self
        )
        if not out_path:
            return

        if not out_path.lower().endswith(".mp4"):
            out_path += ".mp4"

        # Disable buttons while exporting
        if hasattr(self, 'v1_export_btn'):
            self.v1_export_btn.configure(state="disabled")
        if hasattr(self, 'v1_dub_voice_btn'):
            self.v1_dub_voice_btn.configure(state="disabled")

        burn_sub = getattr(self.video_player, 'cc_enabled', False) if hasattr(self, 'video_player') else False

        def _prog(m, p):
            self._v1_update_status(m, p)

        def _done(final_path):
            def _ui_done():
                if hasattr(self, 'v1_export_btn'):
                    self.v1_export_btn.configure(state="normal")
                if hasattr(self, 'v1_dub_voice_btn'):
                    self.v1_dub_voice_btn.configure(state="normal")
                self.v1_progress_bar.set(1.0)
                self._on_merge_success(final_path)
                ans = messagebox.askyesno(
                    "Export ជោគជ័យ!",
                    f"🎉 បាន Export វីដេអូច្របាច់សំឡេងខ្មែរដោយជោគជ័យ!\n\nទីតាំង File:\n{final_path}\n\nតើអ្នកចង់បើកមើល Folder ដែរឬទេ?",
                    parent=self
                )
                if ans:
                    safe_open_folder(os.path.dirname(final_path))
            self.after(0, _ui_done)

        def _err(e):
            def _ui_err():
                if hasattr(self, 'v1_export_btn'):
                    self.v1_export_btn.configure(state="normal")
                if hasattr(self, 'v1_dub_voice_btn'):
                    self.v1_dub_voice_btn.configure(state="normal")
                self._v1_on_error(e)
            self.after(0, _ui_err)

        threading.Thread(
            target=lambda: self._execute_merge_video(
                target_h=None,
                crf=20,
                burn_subtitles=burn_sub,
                output_video_path=out_path,
                on_progress=_prog,
                on_done=_done,
                on_error=_err
            ),
            daemon=True
        ).start()

    def _open_copyright_scanner_dialog(self):
        video_path = self.v1_video_entry.get().strip() if hasattr(self, 'v1_video_entry') else ""
        if not video_path or not os.path.exists(video_path):
            messagebox.showerror(self.t("warning_title"), "សូមជ្រើសរើសវីដេអូជាមុនសិន!")
            return
        
        dlg = CopyrightScannerDialog(self, video_path=video_path, timeline_ref=getattr(self, 'timeline', None))
        dlg.grab_set()

    def _start_merge_video(self):
        self._open_export_dialog()

    def _execute_merge_video(self, target_h=None, crf=22, burn_subtitles=False, output_video_path="", on_progress=None, on_done=None, on_error=None):
        video_path = self.v1_video_entry.get().strip() if hasattr(self, 'v1_video_entry') else ""
        if not video_path or not os.path.exists(video_path):
            if on_error: on_error("សូមជ្រើសរើសវីដេអូ!")
            return
            
        if not self.generated_master_audio or not os.path.exists(self.generated_master_audio):
            if on_error: on_error("សូមចុចបង្កើតសំឡេងរួមជាមុនសិន!")
            return

        def _notify(m, p):
            if on_progress:
                on_progress(m, p)
            else:
                self._v1_update_status(m, p)

        try:
            _notify("កំពុងរៀបចំសំឡេងដើមពីវីដេអូ...", 0.2)
            bg_vol = self.v1_bg_slider.get() if hasattr(self, 'v1_bg_slider') else 0.3
            custom_dir = self.v1_output_dir_entry.get().strip() if hasattr(self, 'v1_output_dir_entry') else ""
            mute_orig = bool(self.v1_mute_orig_voice_var.get()) if hasattr(self, 'v1_mute_orig_voice_var') else True
            use_demucs = bool(self.v1_demucs_var.get()) if hasattr(self, 'v1_demucs_var') else True
            selected_bgm = getattr(self, 'custom_bgm_path', '')
            bgm_segments_snapshot = self.timeline.get_bgm_segments() if hasattr(self, 'timeline') else None
            
            segments_snapshot = []
            for s in self.segments_data:
                segments_snapshot.append({'start': s['start'], 'end': s['end']})
                
            hq_audio_path = extract_high_quality_audio(video_path, self.temp_dir)
            
            has_isolated_bgm = False
            if selected_bgm and os.path.exists(selected_bgm):
                has_isolated_bgm = True
                bg_source = AudioSegment.silent(duration=1000, frame_rate=44100).set_channels(2)
            elif hasattr(self, 'isolated_bgm_path') and self.isolated_bgm_path and os.path.exists(self.isolated_bgm_path):
                _notify("កំពុងប្រើប្រាស់ភ្លេង BGM ដែលបានស្រង់តាម AI Demucs រួចរាល់...", 0.35)
                bg_source = AudioSegment.from_file(self.isolated_bgm_path).set_frame_rate(44100).set_channels(2)
                has_isolated_bgm = True
            elif hasattr(self, 'demucs_thread') and self.demucs_thread and self.demucs_thread.is_alive():
                _notify("កំពុងរង់ចាំ AI Demucs បញ្ចប់ការស្រង់ BGM...", 0.35)
                self.demucs_thread.join(timeout=10.0)
                if hasattr(self, 'demucs_container') and self.demucs_container and self.demucs_container[0] and os.path.exists(self.demucs_container[0]):
                    self.isolated_bgm_path = self.demucs_container[0]
                    bg_source = AudioSegment.from_file(self.isolated_bgm_path).set_frame_rate(44100).set_channels(2)
                    has_isolated_bgm = True
                else:
                    _notify("ប្រើប្រព័ន្ធបិទសំឡេងនិយាយដើម ១០០% (លឿនបំផុត)...", 0.45)
                    bg_source = AudioSegment.from_file(hq_audio_path).set_frame_rate(44100).set_channels(2)
            elif use_demucs and bg_vol > 0.01:
                _notify("កំពុងប្រើ AI Demucs ដើម្បីស្រង់យកតែភ្លេង BGM...", 0.35)
                no_voc_p = extract_demucs_bgm(hq_audio_path, self.temp_dir)
                if no_voc_p and os.path.exists(no_voc_p):
                    bg_source = AudioSegment.from_file(no_voc_p).set_frame_rate(44100).set_channels(2)
                    has_isolated_bgm = True
                    self.isolated_bgm_path = no_voc_p
                else:
                    _notify("ប្រើប្រព័ន្ធបិទសំឡេងនិយាយដើម ១០០%...", 0.45)
                    bg_source = AudioSegment.from_file(hq_audio_path).set_frame_rate(44100).set_channels(2)
            else:
                bg_source = AudioSegment.from_file(hq_audio_path).set_frame_rate(44100).set_channels(2)

                
            _notify("កំពុងច្របាច់សំឡេងខ្មែរជាមួយភ្លេង Background...", 0.6)
            clean_bg = create_clean_background_track(
                bg_source,
                segments_snapshot,
                bg_vol=bg_vol,
                mute_original_speech=mute_orig,
                has_isolated_bgm=has_isolated_bgm,
                custom_bgm_path=selected_bgm,
                bgm_segments=bgm_segments_snapshot
            )
            
            dubbed_audio = AudioSegment.from_file(self.generated_master_audio).set_frame_rate(44100).set_channels(2)
            if dubbed_audio.dBFS > -90:
                dubbed_audio = dubbed_audio.apply_gain(-12.0 - dubbed_audio.dBFS)
                
            final_mixed = clean_bg.overlay(dubbed_audio)
            if final_mixed.dBFS > -90 and final_mixed.dBFS < -14:
                final_mixed = final_mixed.apply_gain(min(8.0, -12.0 - final_mixed.dBFS))
                
            final_audio_wav = os.path.join(self.temp_dir, "final_merged_track.wav")
            final_mixed.export(final_audio_wav, format="wav", parameters=["-ar", "44100", "-ac", "2"])
            
            if not output_video_path:
                out_dir = custom_dir if (custom_dir and os.path.isdir(custom_dir)) else os.path.dirname(video_path)
                output_video_path = os.path.join(out_dir, f"dubbed_khmer_{int(time.time())}.mp4")
                
            _notify("កំពុង Render និង Export វីដេអូតាម FFmpeg...", 0.8)
            
            # Calculate target video dimensions for output
            vw = self.video_info.get('width', 1920) if hasattr(self, 'video_info') and self.video_info else 1920
            vh = self.video_info.get('height', 1080) if hasattr(self, 'video_info') and self.video_info else 1080
            if hasattr(self, 'video_player') and self.video_player.cap and self.video_player.cap.isOpened():
                vw = int(self.video_player.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or vw)
                vh = int(self.video_player.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or vh)

            # Check transform settings from video_player (Flip & Crop)
            flip_h = getattr(self.video_player, 'flip_horizontal', False) if hasattr(self, 'video_player') else False
            flip_v = getattr(self.video_player, 'flip_vertical', False) if hasattr(self, 'video_player') else False
            crop_box = self.video_player.get_effective_crop_box(vw, vh) if hasattr(self, 'video_player') else None

            eff_vw = vw
            eff_vh = vh
            vf_parts = []
            
            if crop_box is not None:
                cx1, cy1, cx2, cy2 = crop_box
                cw = cx2 - cx1
                ch = cy2 - cy1
                if cw % 2 != 0: cw -= 1
                if ch % 2 != 0: ch -= 1
                cw = max(2, cw)
                ch = max(2, ch)
                vf_parts.append(f"crop={cw}:{ch}:{cx1}:{cy1}")
                eff_vw = cw
                eff_vh = ch

            if flip_h:
                vf_parts.append("hflip")
            if flip_v:
                vf_parts.append("vflip")

            out_h = target_h if target_h else eff_vh
            out_w = int(round((eff_vw / max(1, eff_vh)) * out_h))
            if out_w % 2 != 0:
                out_w += 1

            if target_h and target_h < eff_vh:
                vf_parts.append(f"scale=-2:{target_h}")

            # Generate matching .ass subtitle file alongside output_video_path
            ass_file_path = os.path.splitext(output_video_path)[0] + ".ass"
            if hasattr(self, 'video_player') and self.segments_data:
                try:
                    style_cfg = self.video_player.get_subtitle_style_config()
                    generate_ass_subtitle_file(
                        self.segments_data,
                        ass_file_path,
                        video_w=out_w,
                        video_h=out_h,
                        font_family=style_cfg.get("font_family", "Khmer OS Battambang"),
                        font_size=style_cfg.get("font_size", 24),
                        text_color=style_cfg.get("text_color", "#FFFFFF"),
                        bg_color=style_cfg.get("bg_color", "#000000"),
                        bg_opacity=style_cfg.get("bg_opacity", 90),
                        enable_subtitle_background=style_cfg.get("enable_subtitle_background", True),
                        pos_x_pct=style_cfg.get("pos_x_pct", 50.0),
                        pos_y_pct=style_cfg.get("pos_y_pct", 85.0),
                        box_full_width=style_cfg.get("box_full_width", False)
                    )
                except Exception as ex_ass:
                    print(f"[Warning] Failed to generate ASS: {ex_ass}")
                    
            escaped_ass = Path(ass_file_path).as_posix().replace(":", r"\:")
            if burn_subtitles and os.path.exists(ass_file_path):
                vf_parts.append(f"ass='{escaped_ass}'")
                
            if vf_parts:
                vf_filter = ",".join(vf_parts)
                cmd_merge = [
                    FFMPEG_EXE, "-y",
                    "-nostdin",
                    "-i", video_path,
                    "-i", final_audio_wav,
                    "-vf", vf_filter,
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", str(crf),
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "44100",
                    "-ac", "2",
                    "-map", "0:v:0?",
                    "-map", "1:a:0",
                    "-shortest",
                    output_video_path
                ]
            else:
                cmd_merge = [
                    FFMPEG_EXE, "-y",
                    "-nostdin",
                    "-i", video_path,
                    "-i", final_audio_wav,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "44100",
                    "-ac", "2",
                    "-map", "0:v:0?",
                    "-map", "1:a:0",
                    "-shortest",
                    output_video_path
                ]
                
            run_kwargs = {
                "capture_output": True,
                "text": True,
                "stdin": subprocess.DEVNULL,
                "env": os.environ
            }
            if sys.platform == "win32":
                run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

            p_res = subprocess.run(cmd_merge, **run_kwargs)
            
            is_success = False
            if p_res.returncode == 0:
                is_success = True
            elif os.path.exists(output_video_path) and os.path.getsize(output_video_path) > 1000:
                # If FFmpeg exited gracefully upon shortest stream completion (signal 15 / 143 / 255)
                # and the output video file was created properly, treat as success!
                if "Exiting normally" in p_res.stderr or p_res.returncode in (143, 255):
                    print(f"[FFmpeg Notice] Video exported successfully ({os.path.getsize(output_video_path)} bytes) despite graceful code {p_res.returncode}.")
                    is_success = True
                    
            if not is_success:
                print(f"[FFmpeg Merge Error] Returncode: {p_res.returncode}\n{p_res.stderr}")
                raise RuntimeError(f"FFmpeg error: {p_res.stderr[-300:]}")
            _notify("✨ រួចរាល់!", 1.0)
            
            if on_done:
                on_done(output_video_path)
            else:
                self.after(0, lambda: self._on_merge_success(output_video_path))
                
        except Exception as e:
            err = str(e)
            if on_error:
                on_error(err)
            else:
                self.after(0, lambda: self._v1_on_error(err))

    def _on_merge_success(self, output_video_path):
        self.v1_merged_video_path = output_video_path
        if hasattr(self, 'v1_extract_btn'):
            self.v1_extract_btn.configure(state="normal")
        if hasattr(self, 'v1_dub_voice_btn'):
            self.v1_dub_voice_btn.configure(state="normal")
        if hasattr(self, 'v1_export_btn'):
            self.v1_export_btn.configure(state="normal")
        if hasattr(self, 'v1_regen_video_btn'):
            self.v1_regen_video_btn.configure(state="normal")
        self.v1_progress_bar.set(1.0)
        self.v1_status_label.configure(
            text=f"✨ រួចរាល់! វីដេអូត្រូវរក្សាទុកនៅ៖ {os.path.basename(output_video_path)}",
            text_color="#10B981"
        )

        # Update Result & Video Preview Area
        info = get_video_info(output_video_path)
        sz = f"{info['size_mb']} MB" if info['size_mb'] > 0 else ""
        dur = format_time(info['duration']) if info['duration'] > 0 else ""
        res_str = f"{info['width']}x{info['height']}" if info['width'] > 0 else ""
        meta_parts = [p for p in [sz, dur, res_str] if p]
        meta_info = f" ({' | '.join(meta_parts)})" if meta_parts else ""

        if hasattr(self, 'v1_result_info_label'):
            self.v1_result_info_label.configure(
                text=f"✅ វីដេអូច្របាច់រួច៖ {os.path.basename(output_video_path)}{meta_info}",
                text_color="#10B981"
            )
        if hasattr(self, 'v1_result_path_entry'):
            self.v1_result_path_entry.delete(0, "end")
            self.v1_result_path_entry.insert(0, output_video_path)

        if hasattr(self, 'v1_thumb_label'):
            thumb = extract_video_thumbnail(output_video_path)
            if thumb:
                self.v1_thumb_label.configure(image=thumb, text="")
                self.v1_thumb_label.image = thumb

        if hasattr(self, 'v1_play_video_btn'):
            self.v1_play_video_btn.configure(state="normal")
        if hasattr(self, 'v1_locate_video_btn'):
            self.v1_locate_video_btn.configure(state="normal")

        if hasattr(self, 'video_player'):
            orig_vid = self.v1_video_entry.get().strip()
            final_wav = os.path.join(self.temp_dir, "final_merged_track.wav") if hasattr(self, 'temp_dir') and self.temp_dir else ""
            kh_track = final_wav if (final_wav and os.path.exists(final_wav)) else output_video_path
            self.video_player.load_video(output_video_path, keep_khmer_audio=True)
            self.video_player.khmer_audio_path = kh_track
            if orig_vid and os.path.exists(orig_vid):
                def _prep_orig():
                    try:
                        temp_orig = os.path.join(tempfile.gettempdir(), f"vplay_orig_{int(time.time()*1000)}.wav")
                        cmd = [
                            FFMPEG_EXE, "-y",
                            "-nostdin",
                            "-i", orig_vid,
                            "-vn", "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
                            temp_orig
                        ]
                        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)
                        if p.returncode == 0 and os.path.exists(temp_orig):
                            self.video_player.orig_audio_path = temp_orig
                    except Exception:
                        pass
                threading.Thread(target=_prep_orig, daemon=True).start()
            if hasattr(self, 'timeline') and hasattr(self.timeline, 'btn_track_khmer'):
                self.timeline.btn_track_khmer.configure(text="🇰🇭 ស្តាប់ភាសាខ្មែរ (រួចរាល់)", fg_color="#059669")
            if hasattr(self.video_player, 'btn_track_khmer'):
                self.video_player.btn_track_khmer.configure(text="🇰🇭 ស្តាប់ភាសាខ្មែរ (រួចរាល់)", fg_color="#059669")
            self.video_player.switch_audio_mode("khmer")
        if hasattr(self, 'timeline'):
            self.timeline.set_video_name(os.path.basename(output_video_path))

        res = messagebox.askyesno(
            "🎉 ច្របាច់វីដេអូជោគជ័យ!",
            f"វីដេអូដែលបញ្ចូលសំឡេងខ្មែររួចរាល់!\n\nទីតាំង៖\n{output_video_path}\n\nតើអ្នកចង់ [ចាក់មើលវីដេអូ] ឥឡូវនេះដែរឬទេ?\n(ចុច Yes ដើម្បីចាក់មើលវីដេអូ, ចុច No ដើម្បីបើកទីតាំង Folder)"
        )
        if res:
            play_video_file(output_video_path)
        else:
            safe_locate_file(output_video_path)

    def _v1_update_status(self, text: str, progress_val: float):
        def _update():
            self.v1_status_label.configure(text=text)
            self.v1_progress_bar.set(progress_val)
        self.after(0, _update)

    def _v1_on_error(self, err_msg: str):
        self.v1_extract_btn.configure(state="normal")
        if hasattr(self, 'v1_dub_voice_btn') and self.segments_data:
            self.v1_dub_voice_btn.configure(state="normal")
        if hasattr(self, 'v1_export_btn') and self.segments_data:
            self.v1_export_btn.configure(state="normal")
        if hasattr(self, 'v1_regen_video_btn'):
            self.v1_regen_video_btn.configure(state="normal")
            
        if "speech.platform.bing.com" in err_msg or "getaddrinfo failed" in err_msg:
            friendly_text = "⚠️ បញ្ហាតភ្ជាប់អ៊ីនធឺណិត (DNS / Connection Error)៖ មិនអាចទាក់ទងទៅម៉ាស៊ីនបម្រើសំឡេង Microsoft Edge-TTS បានទេ។ សូមពិនិត្យមើល Wi-Fi/Internet ឬបិទ VPN រួចចុច 'បញ្ចូលសំឡេងឡើងវិញ'។"
            self.v1_status_label.configure(text=f"❌ {friendly_text}", text_color="#EF4444")
            messagebox.showerror("បញ្ហាតភ្ជាប់អ៊ីនធឺណិត (Network Error)", f"{friendly_text}\n\nព័ត៌មានលម្អិតបច្ចេកទេស:\n{err_msg}")
            return
            
        self.v1_status_label.configure(text=f"❌ កំហុសកើតឡើង: {err_msg}", text_color="#EF4444")
        messagebox.showerror("កំហុសដំណើការ", err_msg)

if __name__ == "__main__":
    app = DubbingApp()
    app.mainloop()
