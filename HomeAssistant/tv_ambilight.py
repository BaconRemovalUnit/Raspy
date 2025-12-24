#!/usr/bin/env python

import os, subprocess, io, json, sys, struct, time, datetime
import numpy as np
from PIL import Image, ImageFile
import requests
import paho.mqtt.client as mqtt

ImageFile.LOAD_TRUNCATED_IMAGES = True

# ===================== LOAD ENVS =====================
TV_ADDR = os.environ.get("tv_addr", "")
HA_URL  = os.environ.get("ha_url", "")
TOKEN   = os.environ.get("ha_token", "")
LIGHT_ENTITY = os.environ.get("light_entity", "light.wo_shi_bei_deng")

CROP_TOP = int(os.environ.get("CROP_TOP", "0"))
CROP_BOTTOM = int(os.environ.get("CROP_BOTTOM", "0"))

BRIGHTNESS_SCALE = float(os.environ.get("BRIGHTNESS_SCALE", "1.15"))
SATURATION_SCALE = float(os.environ.get("SATURATION_SCALE", "1.25"))

# ===================== MQTT  =====================
MQTT_HOST = os.environ.get("mqtt_broker", "127.0.0.1")
MQTT_PORT = int(os.environ.get("mqtt_port", "1883"))
MQTT_USER = os.environ.get("mqtt_user", "")
MQTT_PASS = os.environ.get("mqtt_password", "")

MQTT_TOPIC_RUN = os.environ.get("MQTT_TOPIC_RUN", "")
MQTT_TOPIC_STATUS = os.environ.get("MQTT_TOPIC_STATUS", "")

# mean / median / kmeans
DEFAULT_COLOR_MODE = os.environ.get("COLOR_MODE", "median").lower()
MIN_INTERVAL = float(os.environ.get("MIN_INTERVAL", "3"))


# ===================== wrapper for basic commands =====================
def run(cmd, timeout=15, check=True):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=check)

def adb(args, timeout=15, check=True):
    cmd = ["adb", "-s", TV_ADDR] + args
    return run(cmd, timeout=timeout, check=check)

def adb_shell(cmd: str) -> None:
    subprocess.check_call(["adb", "-s", TV_ADDR, "shell", cmd],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def adb_ready() -> bool:
    try:
        r = subprocess.run(
            ["adb", "-s", TV_ADDR, "get-state"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
            check=False,
        )
        out = (r.stdout.decode(errors="ignore").strip() or r.stderr.decode(errors="ignore").strip())
        return ("device" in out)
    except Exception:
        return False

def ensure_connected(force: bool = False):
    if not force and adb_ready():
        return

    # 尝试 start-server + connect
    subprocess.run(["adb", "start-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["adb", "connect", TV_ADDR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if adb_ready():
        return
    subprocess.run(["adb", "kill-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["adb", "start-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["adb", "connect", TV_ADDR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not adb_ready():
        raise RuntimeError(f"ADB not ready for {TV_ADDR}")

# def ensure_connected():
#     run(["adb", "start-server"], timeout=10, check=False)
#     run(["adb", "connect", TV_ADDR], timeout=10, check=False)

#     st = adb(["get-state"], timeout=5, check=False)
#     state = (st.stdout.decode(errors="ignore").strip() or st.stderr.decode(errors="ignore").strip())
#     if "device" not in state:
#         raise RuntimeError(f"ADB not ready for {TV_ADDR}, state={state}")


# ===================== Take RAW screencap to save time=====================
def grab_screenshot_raw() -> Image.Image:
    raw = subprocess.check_output(["adb", "-s", TV_ADDR, "exec-out", "screencap"], stderr=subprocess.DEVNULL)
    if len(raw) < 16:
        raise RuntimeError("RAW screencap too small")

    w, h, fmt = struct.unpack("<III", raw[:12])
    data = raw[12:]
    expected = w * h * 4
    if len(data) < expected:
        raise RuntimeError(f"RAW screencap length mismatch: got={len(data)} expected>={expected}")

    img = Image.frombytes("RGBA", (w, h), data[:expected]).convert("RGB")
    if CROP_TOP or CROP_BOTTOM:
        ww, hh = img.size
        img = img.crop((0, CROP_TOP, ww, hh - CROP_BOTTOM))
    return img

def grab_screenshot_raw_rgb_array():
    raw = subprocess.check_output(["adb", "-s", TV_ADDR, "exec-out", "screencap"], stderr=subprocess.DEVNULL)
    w, h, fmt = struct.unpack("<III", raw[:12])
    data = raw[12:]
    expected = w * h * 4
    if len(data) < expected:
        raise RuntimeError("RAW screencap length mismatch")

    arr = np.frombuffer(data[:expected], dtype=np.uint8).reshape((h, w, 4))
    rgb = arr[:, :, :3]  # Ignore alpha

    if CROP_TOP or CROP_BOTTOM:
        rgb = rgb[CROP_TOP:h - CROP_BOTTOM, :, :]
    return rgb  # dtype=uint8

def median_color_from_rgb(rgb: np.ndarray) -> tuple[int,int,int]:
    # rgb: (h,w,3) uint8
    # downs sample 
    h, w, _ = rgb.shape
    step = max(1, int(os.environ.get("SAMPLE_STEP", "8")))
    sample = rgb[0:h:step, 0:w:step, :].astype(np.float32)

    brightness = sample.mean(axis=2)
    mask = brightness > float(os.environ.get("MEDIAN_MIN_BRIGHTNESS", "18"))

    pixels = sample[mask]
    if pixels.shape[0] < 50:
        return (255, 180, 120)

    r, g, b = np.median(pixels, axis=0)

    r, g, b = r*BRIGHTNESS_SCALE, g*BRIGHTNESS_SCALE, b*BRIGHTNESS_SCALE
    m = (r+g+b)/3.0
    r = m + (r-m)*SATURATION_SCALE
    g = m + (g-m)*SATURATION_SCALE
    b = m + (b-m)*SATURATION_SCALE

    return tuple(int(max(0, min(255, v))) for v in (r,g,b))

def grab_screenshot_png() -> Image.Image:
    png = subprocess.check_output(["adb", "-s", TV_ADDR, "exec-out", "screencap", "-p"], stderr=subprocess.DEVNULL)
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if CROP_TOP or CROP_BOTTOM:
        w, h = img.size
        img = img.crop((0, CROP_TOP, w, h - CROP_BOTTOM))
    return img

def grab_screenshot_fast() -> Image.Image:
    try:
        img = grab_screenshot_raw()
        return img
    except Exception:
        img = grab_screenshot_png()
        return img

# ===================== Get Color =====================
def avg_color(img: Image.Image) -> tuple[int,int,int]:
    img_small = img.resize((96, 54), Image.BILINEAR)
    arr = np.asarray(img_small, dtype=np.float32)
    brightness = arr.mean(axis=2)
    mask = brightness > 18
    if mask.sum() < 50:
        return (255, 180, 120)

    rgb = arr[mask].mean(axis=0)
    r, g, b = rgb
    r, g, b = r*BRIGHTNESS_SCALE, g*BRIGHTNESS_SCALE, b*BRIGHTNESS_SCALE
    m = (r+g+b)/3.0
    r = m + (r-m)*SATURATION_SCALE
    g = m + (g-m)*SATURATION_SCALE
    b = m + (b-m)*SATURATION_SCALE
    return tuple(int(max(0, min(255, v))) for v in (r,g,b))

def median_color(img: Image.Image) -> tuple[int, int, int]:
    DOWNSAMPLE_W, DOWNSAMPLE_H = 96, 54
    MIN_BRIGHTNESS = float(os.environ.get("MEDIAN_MIN_BRIGHTNESS", "18"))
    MIN_SAT = float(os.environ.get("MEDIAN_MIN_SAT", "0"))

    small = img.resize((DOWNSAMPLE_W, DOWNSAMPLE_H), Image.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)

    brightness = arr.mean(axis=2)
    mask = brightness > MIN_BRIGHTNESS

    if MIN_SAT > 0:
        mx = arr.max(axis=2)
        mn = arr.min(axis=2)
        sat = mx - mn
        mask = mask & (sat >= MIN_SAT)

    pixels = arr[mask]
    if pixels.shape[0] < 50:
        return (255, 180, 120)

    r, g, b = np.median(pixels, axis=0)

    r, g, b = r * BRIGHTNESS_SCALE, g * BRIGHTNESS_SCALE, b * BRIGHTNESS_SCALE
    m = (r + g + b) / 3.0
    r = m + (r - m) * SATURATION_SCALE
    g = m + (g - m) * SATURATION_SCALE
    b = m + (b - m) * SATURATION_SCALE

    return tuple(int(max(0, min(255, v))) for v in (r,g,b))

def avg_color_kmeans(img: Image.Image) -> tuple[int, int, int]:
    DOWNSAMPLE_W, DOWNSAMPLE_H = 96, 54
    K = int(os.environ.get("KMEANS_K", "5"))
    ITERS = int(os.environ.get("KMEANS_ITERS", "10"))
    MAX_SAMPLES = int(os.environ.get("KMEANS_MAX_SAMPLES", "2500"))
    MIN_BRIGHTNESS = float(os.environ.get("KMEANS_MIN_BRIGHTNESS", "18"))
    MIN_SAT = float(os.environ.get("KMEANS_MIN_SAT", "0"))
    PICK_MODE = os.environ.get("KMEANS_PICK_MODE", "majority").lower()

    small = img.resize((DOWNSAMPLE_W, DOWNSAMPLE_H), Image.BILINEAR)
    arr = np.asarray(small, dtype=np.float32)

    brightness = arr.mean(axis=2)
    mask = brightness > MIN_BRIGHTNESS

    if MIN_SAT > 0:
        mx = arr.max(axis=2)
        mn = arr.min(axis=2)
        sat = mx - mn
        mask = mask & (sat >= MIN_SAT)

    pixels = arr[mask]
    if pixels.shape[0] < max(50, K * 10):
        return (255, 180, 120)

    if pixels.shape[0] > MAX_SAMPLES:
        idx = np.random.choice(pixels.shape[0], MAX_SAMPLES, replace=False)
        pixels = pixels[idx]

    centers = pixels[np.random.choice(pixels.shape[0], K, replace=False)]

    for _ in range(ITERS):
        d = ((pixels[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = d.argmin(axis=1)

        new_centers = centers.copy()
        for ki in range(K):
            m = labels == ki
            if m.any():
                new_centers[ki] = pixels[m].mean(axis=0)
            else:
                new_centers[ki] = pixels[np.random.randint(0, pixels.shape[0])]

        if np.allclose(new_centers, centers, atol=1.0):
            centers = new_centers
            break
        centers = new_centers

    d = ((pixels[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    labels = d.argmin(axis=1)
    counts = np.bincount(labels, minlength=K)

    if PICK_MODE == "brightest":
        pick = int(centers.mean(axis=1).argmax())
    else:
        pick = int(counts.argmax())

    r, g, b = centers[pick]

    r, g, b = r * BRIGHTNESS_SCALE, g * BRIGHTNESS_SCALE, b * BRIGHTNESS_SCALE
    m = (r + g + b) / 3.0
    r = m + (r - m) * SATURATION_SCALE
    g = m + (g - m) * SATURATION_SCALE
    b = m + (b - m) * SATURATION_SCALE

    return tuple(int(max(0, min(255, v))) for v in (r,g,b))

def pick_color(img: Image.Image, mode: str) -> tuple[int,int,int]:
    mode = (mode or DEFAULT_COLOR_MODE).lower()
    if mode in ("mean", "avg"):
        return avg_color(img)
    if mode == "kmeans":
        return avg_color_kmeans(img)
    # 默认 median
    return median_color(img)

# ===================== HomeAssistant Call =====================
def set_light(rgb: tuple[int,int,int]):
    if not TOKEN:
        raise RuntimeError("HA_TOKEN not set")

    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    data = {"entity_id": LIGHT_ENTITY, "rgb_color": list(rgb), "transition": 1}
    r = requests.post(f"{HA_URL}/api/services/light/turn_on",
                      headers=headers, json=data, timeout=8)
    if r.status_code >= 400:
        raise RuntimeError(f"HA API error {r.status_code}: {r.text}")
    r.raise_for_status()

# ===================== MQTT =====================
_last_run_ts = 0.0

def do_once(mode: str) -> dict:
    t_all = time.time()
    ensure_t0 = time.time()
    ensure_connected()
    t_ensure = time.time() - ensure_t0
    print('ensure_connected', t_ensure)

    grab_t0 = time.time()
    # img = grab_screenshot_fast()

    img = grab_screenshot_raw_rgb_array()

    img1 = Image.fromarray(img, mode="RGB")
    img1.save("output.png")

    t_grab = time.time() - grab_t0
    print('grab_screenshot_fast', t_grab)

    color_t0 = time.time()
    # rgb = pick_color(img, mode)


    rgb = median_color_from_rgb(img)

    t_color = time.time() - color_t0
    print('pick_color', t_color)

    set_t0 = time.time()
    set_light(rgb)
    t_set = time.time() - set_t0
    print('set_light', t_set)

    return {
        "ok": True,
        "mode": mode or DEFAULT_COLOR_MODE,
        "rgb": list(rgb),
        "timing": {
            "ensure_s": round(t_ensure, 3),
            "grab_s": round(t_grab, 3),
            "color_s": round(t_color, 3),
            "set_s": round(t_set, 3),
            "total_s": round(time.time() - t_all, 3),
        },
        "ts": time.time(),
    }

def parse_mode_from_payload(payload: bytes) -> str:
    payload = b'median'
    if not payload:
        return DEFAULT_COLOR_MODE
    try:
        s = payload.decode("utf-8", errors="ignore").strip()
    except Exception:
        return DEFAULT_COLOR_MODE

    if not s:
        return DEFAULT_COLOR_MODE

    if s.startswith("{"):
        try:
            obj = json.loads(s)
            return str(obj.get("mode", DEFAULT_COLOR_MODE))
        except Exception:
            return DEFAULT_COLOR_MODE

    return s

def on_message(client, userdata, msg):
    global _last_run_ts
    now = time.time()
    print(now)
    if MIN_INTERVAL > 0 and (now - _last_run_ts) < MIN_INTERVAL:
        client.publish(MQTT_TOPIC_STATUS, json.dumps({
            "ok": False,
            "error": f"rate_limited: {now - _last_run_ts:.3f}s < {MIN_INTERVAL}s",
            "ts": now
        }))
        return

    _last_run_ts = now
    mode = parse_mode_from_payload(msg.payload)

    try:
        res = do_once(mode)
        client.publish(MQTT_TOPIC_STATUS, json.dumps(res), qos=0, retain=False)
    except Exception as e:
        client.publish(MQTT_TOPIC_STATUS, json.dumps({
            "ok": False,
            "mode": mode,
            "error": str(e),
            "ts": time.time()
        }), qos=0, retain=False)

def main():
    if not TOKEN:
        print("ERROR: HA_TOKEN not set", file=sys.stderr)
        sys.exit(2)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PASS)

    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.subscribe(MQTT_TOPIC_RUN)

    client.loop_forever()

if __name__ == "__main__":
    main()
