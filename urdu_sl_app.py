# ====================================================================
# URDU SIGN LANGUAGE RECOGNITION - WITH NATURAL EDGE TTS
# EXE COMPATIBLE VERSION - ALL FIXES INCLUDED
# ====================================================================

import flet as ft
import cv2
import numpy as np
import mediapipe as mp
from tensorflow import keras
import pickle
from collections import deque
import time
import threading
import base64
from datetime import datetime
from sklearn.preprocessing import LabelEncoder
import os
import sys
from pathlib import Path
import asyncio

# TTS - Edge TTS for Natural Voices
try:
    import edge_tts
    import pygame
    TTS_AVAILABLE = True
except:
    TTS_AVAILABLE = False
    print(" Installing Edge TTS...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "edge-tts", "pygame"])
    import edge_tts
    import pygame
    TTS_AVAILABLE = True

# ====================================================================
# RESOURCE PATH FUNCTION FOR EXE COMPATIBILITY
# ====================================================================

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ====================================================================
# CONFIGURATION - WITH RESOURCE PATHS
# ====================================================================

# Model paths (will work in both development and EXE)
MODEL_PATH = resource_path('models_urdu_sl/urdu_sl_model_20251026_001348.h5')
LABEL_ENCODER_PATH = resource_path('models_urdu_sl/urdu_sl_model_20251026_001348_labels.pkl')
TTS_CACHE_DIR = resource_path('tts_cache_natural')

# Create local cache directory if bundled cache doesn't exist
if not os.path.exists(TTS_CACHE_DIR):
    TTS_CACHE_DIR = 'tts_cache_natural'
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)

SEQUENCE_LENGTH = 30
CONFIDENCE_THRESHOLD = 0.7

# Ensure cache directory exists
os.makedirs(TTS_CACHE_DIR, exist_ok=True)

# ====================================================================
# CREATE PLACEHOLDER IMAGE
# ====================================================================

def create_placeholder_image():
    """Create a black placeholder image"""
    placeholder = np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.putText(placeholder, "Camera will appear here", (400, 360), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
    _, buffer = cv2.imencode('.jpg', placeholder)
    return base64.b64encode(buffer).decode()

# ====================================================================
# NATURAL URDU TTS ENGINE - EDGE TTS
# ====================================================================

class NaturalUrduTTS:
    """Natural Urdu Text-to-Speech with Edge TTS"""
    
    def __init__(self):
        self.enabled = True
        self.cache_dir = Path(TTS_CACHE_DIR)
        self.cache_dir.mkdir(exist_ok=True)
        self.is_speaking = False
        
        # Best Urdu voice - Pakistani Female (Most Natural)
        self.voice = 'ur-PK-UzmaNeural'
        
        if TTS_AVAILABLE:
            try:
                pygame.mixer.init()
                print(" Natural Urdu TTS initialized")
                print(f" Voice: Pakistani Female (Uzma)")
            except:
                self.enabled = False
        else:
            self.enabled = False
    
    async def _generate_audio(self, text, filename):
        """Generate audio file using Edge TTS"""
        try:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(filename)
            return True
        except Exception as e:
            print(f" TTS generation error: {e}")
            return False
    
    def cache_gesture(self, text):
        """Generate and cache audio for a gesture"""
        filename = self.cache_dir / f"{hash(text)}.mp3"
        
        if filename.exists():
            return filename
        
        # Generate using async
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(self._generate_audio(text, str(filename)))
            loop.close()
            
            if success:
                return filename
        except Exception as e:
            print(f" Cache error: {e}")
        
        return None
    
    def cache_all_gestures(self, gesture_list):
        """Pre-cache all gestures"""
        print(" Generating natural Urdu TTS cache...")
        
        cached_count = 0
        generated_count = 0
        
        for i, gesture in enumerate(gesture_list, 1):
            filename = self.cache_dir / f"{hash(gesture)}.mp3"
            if filename.exists():
                cached_count += 1
                print(f"   {i}/25: ✓ Already cached - {gesture[:35]}...")
            else:
                print(f"   {i}/25: Generating - {gesture[:35]}...")
                result = self.cache_gesture(gesture)
                if result:
                    generated_count += 1
                    print(f"           Done!")
        
        print(f"\n TTS Ready! (Cached: {cached_count}, Generated: {generated_count})\n")
    
    def speak(self, text):
        """Play cached audio"""
        if not self.enabled or self.is_speaking:
            return
        
        def play():
            self.is_speaking = True
            try:
                audio_file = self.cache_dir / f"{hash(text)}.mp3"
                
                # Generate if not cached
                if not audio_file.exists():
                    self.cache_gesture(text)
                
                if audio_file.exists():
                    pygame.mixer.music.load(str(audio_file))
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.1)
            except Exception as e:
                print(f"TTS play error: {e}")
            finally:
                self.is_speaking = False
        
        threading.Thread(target=play, daemon=True).start()
    
    def stop(self):
        """Stop audio"""
        try:
            pygame.mixer.music.stop()
        except:
            pass
    
    def set_enabled(self, enabled):
        """Enable/disable TTS"""
        self.enabled = enabled
        if not enabled:
            self.stop()

# ====================================================================
# LOAD MODEL - WITH ERROR HANDLING
# ====================================================================

def load_label_encoder():
    """Load or create label encoder"""
    gesture_classes = [
        'آپ بہت خوبصورت ہیں۔', 'آپ کا نام کیا ہے؟', 'آہِستہ', 'ادھر آو!',
        'السلام وعلیکم', 'آپ کہاں رہتے ہیں؟', 'آپ کیسے ہیں؟',
        'ایمبولینس کو کال کریں', 'بھائی', 'حالات کیسے ہیں؟', 'خوش رہو',
        'شکریہ', 'فون کہاں ہے؟', 'مبارک ہو', 'میں اشاروں کی زبان سیکھ رہا ہوں',
        'میں واش روم جا سکتا ہوں؟', 'میں ٹھیک ہوں', 'نہیں', 'چھونا مت',
        'کمپیوٹر', 'کیا آپ تیار ہیں؟', 'کیا آپ پاس یا ناکام ہوئے ہیں؟',
        'کیا تم بہرے ہو؟', 'کیا میں اپ کی مدد کر سکتا ہوں؟', 'گھبرائیں نہیں'
    ]
    
    try:
        with open(LABEL_ENCODER_PATH, 'rb') as f:
            encoder = pickle.load(f)
            print(f" Label encoder loaded from: {LABEL_ENCODER_PATH}")
            return encoder
    except Exception as e:
        print(f" Creating new label encoder: {e}")
        encoder = LabelEncoder()
        encoder.fit(gesture_classes)
        return encoder

# Load model and encoder
print(f"Loading model from: {MODEL_PATH}")
model = keras.models.load_model(MODEL_PATH)
print(" Model loaded successfully")

label_encoder = load_label_encoder()

# Initialize Natural TTS
tts_engine = NaturalUrduTTS()
tts_engine.cache_all_gestures(label_encoder.classes_)

print(" System Ready!\n")

# MediaPipe initialization
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    model_complexity=0
)

# ====================================================================
# FEATURE EXTRACTION
# ====================================================================

def extract_landmarks_from_results(results):
    """Extract hand landmarks from MediaPipe results"""
    if not results.multi_hand_landmarks:
        return None
    
    all_features = []
    for i in range(2):
        if i < len(results.multi_hand_landmarks):
            hand_landmarks = results.multi_hand_landmarks[i]
            
            raw_coords = []
            for lm in hand_landmarks.landmark:
                raw_coords.extend([lm.x, lm.y, lm.z])
            all_features.extend(raw_coords)
            
            wrist = hand_landmarks.landmark[0]
            norm_coords = []
            for lm in hand_landmarks.landmark:
                norm_coords.extend([lm.x - wrist.x, lm.y - wrist.y, lm.z - wrist.z])
            all_features.extend(norm_coords)
        else:
            all_features.extend([0.0] * 126)
    
    num_hands = len(results.multi_hand_landmarks)
    all_features.extend([num_hands / 2.0, 1.0 if num_hands > 0 else 0.0,
                        1.0 if num_hands > 1 else 0.0, 0.5, 0.5, 0.0])
    
    return np.array(all_features, dtype=np.float32)

# ====================================================================
# GESTURE RECOGNIZER
# ====================================================================

class GestureRecognizer:
    """Real-time gesture recognition with prediction smoothing"""
    
    def __init__(self):
        self.frame_buffer = deque(maxlen=SEQUENCE_LENGTH)
        self.prediction_history = deque(maxlen=5)
        self.current_gesture = None
        self.gesture_hold_counter = 0
        self.gesture_history = []
        self.last_spoken = None
        
    def update(self, landmarks):
        """Update with new frame landmarks"""
        if landmarks is not None:
            self.frame_buffer.append(landmarks)
        
        if len(self.frame_buffer) == SEQUENCE_LENGTH:
            sequence = np.expand_dims(np.array(list(self.frame_buffer)), axis=0)
            predictions = model.predict(sequence, verbose=0)[0]
            gesture_idx = np.argmax(predictions)
            confidence = predictions[gesture_idx]
            gesture_name = label_encoder.inverse_transform([gesture_idx])[0]
            
            self.prediction_history.append((gesture_name, confidence))
            
            if len(self.prediction_history) >= 3:
                gestures = [g for g, _ in self.prediction_history]
                most_common = max(set(gestures), key=gestures.count)
                avg_conf = np.mean([c for g, c in self.prediction_history if g == most_common])
                
                if avg_conf > CONFIDENCE_THRESHOLD:
                    if most_common != self.current_gesture:
                        self.current_gesture = most_common
                        self.gesture_hold_counter = 20
                        self.gesture_history.append({
                            'gesture': most_common,
                            'time': datetime.now().strftime("%I:%M:%S %p")
                        })
                        
                        if most_common != self.last_spoken:
                            tts_engine.speak(most_common)
                            self.last_spoken = most_common
                    else:
                        self.gesture_hold_counter = 20
                elif self.gesture_hold_counter > 0:
                    self.gesture_hold_counter -= 1
                else:
                    self.current_gesture = None
    
    def reset(self):
        """Reset recognizer state"""
        self.frame_buffer.clear()
        self.prediction_history.clear()
        self.current_gesture = None

# ====================================================================
# MAIN FLET APPLICATION
# ====================================================================

class UrduSignLanguageApp:
    """Main application class"""
    
    def __init__(self):
        self.cap = None
        self.is_running = False
        self.recognizer = GestureRecognizer()
        self.is_dark_mode = False
        
    def get_theme(self):
        """Get current theme colors"""
        if self.is_dark_mode:
            return {
                'primary': "#7C3AED",
                'primary_light': "#A78BFA",
                'secondary': "#10B981",
                'accent': "#F59E0B",
                'bg_primary': "#0F172A",
                'bg_secondary': "#1E293B",
                'surface': "#334155",
                'text_primary': "#F1F5F9",
                'text_secondary': "#CBD5E1",
                'border': "#475569",
                'success': "#10B981",
                'error': "#EF4444",
            }
        else:
            return {
                'primary': "#7C3AED",
                'primary_light': "#DDD6FE",
                'secondary': "#10B981",
                'accent': "#F59E0B",
                'bg_primary': "#FAFBFC",
                'bg_secondary': "#FFFFFF",
                'surface': "#F8FAFC",
                'text_primary': "#0F172A",
                'text_secondary': "#64748B",
                'border': "#E2E8F0",
                'success': "#10B981",
                'error': "#EF4444",
            }
    
    def main(self, page: ft.Page):
        """Main UI setup"""
        page.title = "Urdu Sign Language Recognition"
        page.padding = 0
        page.spacing = 0
        
        self.theme = self.get_theme()
        page.bgcolor = self.theme['bg_primary']
        
        # ================================================================
        # UI COMPONENTS
        # ================================================================
        
        # Video Display with Placeholder
        self.video_image = ft.Image(
            src_base64=create_placeholder_image(),
            fit=ft.ImageFit.COVER,
            border_radius=12,
        )
        
        self.video_container = ft.Container(
            content=self.video_image,
            width=720,
            height=405,
            bgcolor="#000000",
            border_radius=12,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=20,
                color="#00000040",
                offset=ft.Offset(0, 10),
            ),
        )
        
        # Subtitle Display
        self.subtitle_text = ft.Text(
            "اشارہ کریں",
            size=38,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            color=self.theme['text_secondary'],
        )
        
        self.subtitle_display = ft.Container(
            content=self.subtitle_text,
            bgcolor=self.theme['surface'],
            padding=ft.padding.symmetric(horizontal=30, vertical=20),
            border_radius=12,
            border=ft.border.all(2, self.theme['primary_light']),
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=15,
                color=self.theme['primary'] + "20",
                offset=ft.Offset(0, 5),
            ),
        )
        
        # Status Badge
        self.status_dot = ft.Container(
            width=10,
            height=10,
            border_radius=5,
            bgcolor="#94A3B8",
        )
        
        self.status_text = ft.Text(
            "Ready",
            size=14,
            weight=ft.FontWeight.W_500,
            color=self.theme['text_secondary'],
        )
        
        self.status_badge = ft.Container(
            content=ft.Row(
                [
                    self.status_dot,
                    ft.Container(width=8),
                    self.status_text,
                ],
                tight=True,
            ),
            bgcolor=self.theme['surface'],
            padding=ft.padding.symmetric(horizontal=16, vertical=8),
            border_radius=20,
            border=ft.border.all(1, self.theme['border']),
        )
        
        # Control Buttons
        self.start_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.PLAY_CIRCLE_ROUNDED, size=24),
                    ft.Container(width=8),
                    ft.Text("Start Recognition", size=16, weight=ft.FontWeight.W_600),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=self.theme['secondary'],
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=16,
            ),
            on_click=self.start_recognition,
            width=300,
            height=55,
        )
        
        self.stop_btn = ft.ElevatedButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.STOP_CIRCLE_ROUNDED, size=24),
                    ft.Container(width=8),
                    ft.Text("Stop", size=16, weight=ft.FontWeight.W_600),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                tight=True,
            ),
            style=ft.ButtonStyle(
                color=ft.Colors.WHITE,
                bgcolor=self.theme['error'],
                shape=ft.RoundedRectangleBorder(radius=12),
                padding=16,
            ),
            on_click=self.stop_recognition,
            width=300,
            height=55,
            disabled=True,
        )
        
        # Voice Toggle
        self.voice_switch = ft.Switch(
            value=True,
            active_color=self.theme['secondary'],
            on_change=self.toggle_tts,
        )
        
        voice_control = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.VOLUME_UP_ROUNDED, color=self.theme['primary'], size=22),
                    ft.Container(width=10),
                    ft.Text("Voice Output", size=15, weight=ft.FontWeight.W_500, color=self.theme['text_primary']),
                    ft.Container(expand=True),
                    self.voice_switch,
                ],
            ),
            bgcolor=self.theme['surface'],
            padding=ft.padding.symmetric(horizontal=20, vertical=12),
            border_radius=10,
            border=ft.border.all(1, self.theme['border']),
        )
        
        # Theme Toggle Button
        self.theme_btn = ft.IconButton(
            icon=ft.Icons.DARK_MODE_ROUNDED if not self.is_dark_mode else ft.Icons.LIGHT_MODE_ROUNDED,
            icon_color=ft.Colors.WHITE,
            icon_size=22,
            tooltip="Toggle Theme",
            on_click=self.toggle_theme,
        )
        
        # History List
        self.history_list = ft.ListView(
            spacing=8,
            padding=10,
            auto_scroll=False,
        )
        
        # ================================================================
        # LAYOUT STRUCTURE
        # ================================================================
        
        # Header
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SIGN_LANGUAGE_ROUNDED, color=ft.Colors.WHITE, size=28),
                    ft.Container(width=12),
                    ft.Text(
                        "Urdu Sign Language Recognition",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.WHITE,
                    ),
                    ft.Container(expand=True),
                    self.theme_btn,
                ],
            ),
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left,
                end=ft.alignment.center_right,
                colors=[self.theme['primary'], self.theme['primary_light']],
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=16),
        )
        
        # Left Panel - Video Display
        left_panel = ft.Container(
            content=ft.Column(
                [
                    self.subtitle_display,
                    ft.Container(height=20),
                    ft.Column(
                        [
                            self.video_container,
                            ft.Container(height=12),
                            self.status_badge,
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=20,
            expand=True,
        )
        
        # Right Panel - Controls and History
        right_panel = ft.Container(
            content=ft.Column(
                [
                    # Controls Card
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Text(
                                    "Controls",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color=self.theme['text_primary'],
                                ),
                                ft.Divider(height=16, color=self.theme['border']),
                                self.start_btn,
                                ft.Container(height=12),
                                self.stop_btn,
                                ft.Container(height=16),
                                voice_control,
                            ],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        bgcolor=self.theme['bg_secondary'],
                        padding=20,
                        border_radius=12,
                        border=ft.border.all(1, self.theme['border']),
                    ),
                    
                    ft.Container(height=20),
                    
                    # History Card
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.HISTORY_ROUNDED, color=self.theme['primary'], size=20),
                                        ft.Container(width=8),
                                        ft.Text(
                                            "Recent Detections",
                                            size=18,
                                            weight=ft.FontWeight.BOLD,
                                            color=self.theme['text_primary'],
                                        ),
                                    ],
                                ),
                                ft.Divider(height=16, color=self.theme['border']),
                                ft.Container(
                                    content=self.history_list,
                                    height=280,
                                ),
                            ],
                        ),
                        bgcolor=self.theme['bg_secondary'],
                        padding=20,
                        border_radius=12,
                        border=ft.border.all(1, self.theme['border']),
                    ),
                ],
            ),
            width=370,
            padding=20,
        )
        
        # Main Content Area
        content = ft.Row(
            [
                left_panel,
                right_panel,
            ],
            spacing=0,
            expand=True,
        )
        
        # Root Container
        root = ft.Column(
            [
                header,
                ft.Container(
                    content=content,
                    bgcolor=self.theme['bg_primary'],
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )
        
        page.add(root)
        self.page = page
    
    # ================================================================
    # EVENT HANDLERS
    # ================================================================
    
    def toggle_theme(self, e):
        """Toggle between light and dark theme"""
        self.is_dark_mode = not self.is_dark_mode
        was_running = self.is_running
        
        if was_running:
            self.is_running = False
            if self.cap:
                self.cap.release()
            time.sleep(0.2)
        
        self.page.clean()
        self.main(self.page)
        
        if was_running:
            time.sleep(0.2)
            self.start_recognition(None)
    
    def toggle_tts(self, e):
        """Toggle TTS on/off"""
        tts_engine.set_enabled(e.control.value)
    
    def start_recognition(self, e):
        """Start camera and recognition"""
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print(" Cannot open camera!")
            return
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        self.is_running = True
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        
        # Update status to Active
        self.status_dot.bgcolor = self.theme['success']
        self.status_dot.shadow = ft.BoxShadow(
            spread_radius=2,
            blur_radius=8,
            color=self.theme['success'] + "60",
        )
        self.status_text.value = "Active"
        self.status_text.color = self.theme['success']
        
        self.page.update()
        
        # Start threads
        threading.Thread(target=self.video_loop, daemon=True).start()
        threading.Thread(target=self.update_ui, daemon=True).start()
    
    def stop_recognition(self, e):
        """Stop camera and recognition"""
        self.is_running = False
        if self.cap:
            self.cap.release()
        
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        
        # Update status to Stopped
        self.status_dot.bgcolor = self.theme['error']
        self.status_dot.shadow = None
        self.status_text.value = "Stopped"
        self.status_text.color = self.theme['error']
        
        tts_engine.stop()
        self.page.update()
    
    def video_loop(self):
        """Main video capture and processing loop"""
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            # Flip and resize frame
            frame = cv2.flip(frame, 1)
            frame = cv2.resize(frame, (1280, 720))
            
            # Process with MediaPipe
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(frame_rgb)
            landmarks = extract_landmarks_from_results(results)
            self.recognizer.update(landmarks)
            
            # Encode frame for display
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            self.video_image.src_base64 = base64.b64encode(buffer).decode()
            
            time.sleep(0.01)
    
    def update_ui(self):
        """Update UI with recognition results"""
        while self.is_running:
            try:
                # Update subtitle
                if self.recognizer.current_gesture:
                    self.subtitle_text.value = self.recognizer.current_gesture
                    self.subtitle_text.color = self.theme['secondary']
                else:
                    self.subtitle_text.value = "اپنا اشارہ دکھائیں"
                    self.subtitle_text.color = self.theme['text_secondary']
                
                # Update history
                if len(self.recognizer.gesture_history) > len(self.history_list.controls):
                    latest = self.recognizer.gesture_history[-1]
                    
                    self.history_list.controls.insert(
                        0,
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Container(
                                        width=5,
                                        height=45,
                                        bgcolor=self.theme['secondary'],
                                        border_radius=3,
                                    ),
                                    ft.Container(width=10),
                                    ft.Column(
                                        [
                                            ft.Text(
                                                latest['gesture'][:30] + "..." if len(latest['gesture']) > 30 else latest['gesture'],
                                                size=12,
                                                weight=ft.FontWeight.W_600,
                                                color=self.theme['text_primary'],
                                                max_lines=2,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                            ft.Text(
                                                latest['time'],
                                                size=10,
                                                color=self.theme['text_secondary'],
                                            ),
                                        ],
                                        spacing=3,
                                        expand=True,
                                    ),
                                ],
                                spacing=0,
                            ),
                            bgcolor=self.theme['surface'],
                            padding=10,
                            border_radius=8,
                            border=ft.border.all(1, self.theme['border']),
                        )
                    )
                    
                    # Keep only last 10 items
                    if len(self.history_list.controls) > 10:
                        self.history_list.controls.pop()
                
                self.page.update()
            except:
                pass
            
            time.sleep(0.1)

# ====================================================================
# APPLICATION ENTRY POINT
# ====================================================================

if __name__ == "__main__":
    app = UrduSignLanguageApp()
    ft.app(target=app.main)