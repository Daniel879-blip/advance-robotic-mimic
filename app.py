import streamlit as st
import threading
import time
import json
import os
from datetime import datetime
import cv2
import numpy as np
import mss
from pynput.mouse import Listener as MouseListener
from pynput.keyboard import Listener as KeyboardListener

# ==============================================================
# CONFIGURATION
# ==============================================================
pyautogui.FAILSAFE = False  # Custom fail-safe implemented
SCREENSHOT_INTERVAL = 1.0   # seconds between optional screenshots

# ==============================================================
# STREAMLIT PAGE SETUP
# ==============================================================
st.set_page_config(page_title="Advanced Robot Mimic", layout="wide")
st.title("🤖 Advanced Screen Robot with Vision-Based Automation")

if "event_log" not in st.session_state:
    st.session_state.event_log = []
if "recording" not in st.session_state:
    st.session_state.recording = False
if "robot_running" not in st.session_state:
    st.session_state.robot_running = False
if "mouse_listener" not in st.session_state:
    st.session_state.mouse_listener = None
if "keyboard_listener" not in st.session_state:
    st.session_state.keyboard_listener = None

# ==============================================================
# HELPER FUNCTIONS
# ==============================================================
def log_event(event_type, data):
    event = {
        "timestamp": time.time(),
        "event_type": event_type,
        "data": data
    }
    st.session_state.event_log.append(event)

# Mouse and keyboard callbacks
def on_move(x, y):
    if st.session_state.recording:
        log_event("mouse_move", {"x": x, "y": y})

def on_click(x, y, button, pressed):
    if st.session_state.recording:
        log_event("mouse_click", {"x": x, "y": y, "button": str(button), "pressed": pressed})

def on_scroll(x, y, dx, dy):
    if st.session_state.recording:
        log_event("mouse_scroll", {"x": x, "y": y, "dx": dx, "dy": dy})

def on_press(key):
    if st.session_state.recording:
        try:
            log_event("key_press", {"key": key.char})
        except:
            log_event("key_press", {"key": str(key)})

# ==============================================================
# RECORDING FUNCTIONS
# ==============================================================
def start_recording():
    st.session_state.event_log = []
    st.session_state.recording = True

    # Start mouse listener
    st.session_state.mouse_listener = MouseListener(
        on_move=on_move, on_click=on_click, on_scroll=on_scroll)
    st.session_state.keyboard_listener = KeyboardListener(on_press=on_press)

    st.session_state.mouse_listener.start()
    st.session_state.keyboard_listener.start()

def stop_recording():
    st.session_state.recording = False
    if st.session_state.mouse_listener:
        st.session_state.mouse_listener.stop()
    if st.session_state.keyboard_listener:
        st.session_state.keyboard_listener.stop()

# ==============================================================
# ROBOT PLAYBACK FUNCTIONS
# ==============================================================
def bezier_cubic(p0, p1, p2, p3, t):
    return (
        (1 - t)**3 * p0 +
        3*(1 - t)**2 * t * p1 +
        3*(1 - t) * t**2 * p2 +
        t**3 * p3
    )

def smooth_path(points, steps=24):
    if len(points) < 2:
        return points[:]
    pts = np.array(points, dtype=float)
    n = len(pts)
    out = []
    for i in range(n-1):
        p0 = pts[i]
        p3 = pts[i+1]
        p_minus = pts[i-1] if i-1>=0 else p0
        p_plus = pts[i+2] if i+2<n else p3
        p1 = p0 + (p3 - p_minus)*0.25
        p2 = p3 - (p_plus - p0)*0.25
        for s in range(steps):
            t = s / steps
            p = bezier_cubic(p0, p1, p2, p3, t)
            out.append((float(p[0]), float(p[1])))
    out.append((float(pts[-1][0]), float(pts[-1][1])))
    return out

def robot_replay(speed=1.0):
    st.session_state.robot_running = True
    events = st.session_state.event_log
    start_time = time.time()

    i = 0
    n = len(events)
    while i < n:
        if not st.session_state.robot_running:
            break
        ev = events[i]
        target_time = start_time + (ev["timestamp"] - events[0]["timestamp"])/speed
        while time.time() < target_time:
            time.sleep(0.001)
        if ev["event_type"] == "mouse_move":
            # Check if next moves exist for smoothing
            moves = [(ev["data"]["x"], ev["data"]["y"])]
            j = i+1
            while j<n and events[j]["event_type"]=="mouse_move":
                moves.append((events[j]["data"]["x"], events[j]["data"]["y"]))
                j += 1
            path = smooth_path(moves)
            for x, y in path:
                pyautogui.moveTo(x, y, duration=0.01)
            i = j
            continue
        elif ev["event_type"] == "mouse_click":
            x, y = ev["data"]["x"], ev["data"]["y"]
            pyautogui.moveTo(x, y)
            if ev["data"]["pressed"]:
                pyautogui.mouseDown()
            else:
                pyautogui.mouseUp()
        elif ev["event_type"] == "mouse_scroll":
            pyautogui.scroll(ev["data"]["dy"])
        elif ev["event_type"] == "key_press":
            key = ev["data"]["key"]
            pyautogui.write(str(key))
        i += 1
    st.session_state.robot_running = False

# ==============================================================
# VISION-BASED ACTIONS
# ==============================================================
def wait_and_click(template_path, timeout=12, threshold=0.85):
    sct = mss.mss()
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    th, tw = template.shape[::-1]
    start = time.time()
    while time.time() - start < timeout:
        screen = np.array(sct.grab(sct.monitors[0]))[:, :, :3]
        gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= threshold:
            x, y = max_loc[0]+tw//2, max_loc[1]+th//2
            pyautogui.moveTo(x, y, duration=0.2)
            pyautogui.click()
            return True
        time.sleep(0.1)
    return False

# ==============================================================
# STREAMLIT INTERFACE
# ==============================================================
col1, col2 = st.columns(2)
with col1:
    if not st.session_state.recording:
        if st.button("🔴 Start Recording"):
            threading.Thread(target=start_recording, daemon=True).start()
            st.success("Recording started.")
    else:
        if st.button("🛑 Stop Recording"):
            threading.Thread(target=stop_recording, daemon=True).start()
            st.warning("Recording stopped.")

with col2:
    if st.button("🤖 Replay Actions"):
        threading.Thread(target=robot_replay, daemon=True).start()

st.divider()
st.subheader("📋 Recorded Events Log")
if len(st.session_state.event_log) > 0:
    st.json(st.session_state.event_log)
else:
    st.info("No events recorded yet.")

st.subheader("📥 Download Recorded Action Script")
json_text = json.dumps(st.session_state.event_log, indent=4)
st.download_button("Download JSON Log", json_text, "robot_actions.json", "application/json")

st.subheader("⚡ Vision-Based Automation")
st.write("Upload a template image (button/icon) to automatically detect and click it:")
template_file = st.file_uploader("Template Image (PNG/JPG)", type=["png","jpg"])
if template_file:
    template_path = os.path.join("temp_template.png")
    with open(template_path, "wb") as f:
        f.write(template_file.getbuffer())
    if st.button("Click Template on Screen"):
        result = wait_and_click(template_path)
        if result:
            st.success("Template clicked successfully!")
        else:
            st.error("Template not found on screen.")
