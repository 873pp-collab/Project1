import requests
import time
import hashlib
import hmac
import json
import os

# ----------------- CONFIG -----------------
API_KEY    = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
BASE_URL   = "https://cdn-ind.testnet.deltaex.org"
PRODUCT_ID = 84       # BTCUSD Perpetual

# ----------------- POSITION SIZING (100x LEVERAGE) -----------------
#
# !! TESTNET ONLY -- DO NOT USE ON LIVE ACCOUNT !!
#
# Capital          : $195 USD (testnet balance)
# Leverage         : 100x (must be set manually on Delta Exchange UI)
# 1 contract value : ~$71 (0.001 BTC notional at ~$71,000 BTC)
# Margin/contract  : $0.71 at 100x
#
# ORDER_SIZE = 50 (safe starting point to confirm orders work)
# Once confirmed working, increase back to 137
#
# To change size: update ORDER_SIZE below and push to GitHub

ORDER_SIZE = 50       # start here to confirm orders work, then increase to 137

# ----------------- POSITION STATE -----------------
current_position = None

# ----------------- SIGNATURE -----------------
def generate_signature(secret, message):
    return hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

# ----------------- API REQUEST -----------------
def make_request(method, path, body=None):
    timestamp = str(int(time.time()))
    body_str  = json.dumps(body, separators=(',', ':')) if body else ""
    message   = method + timestamp + path + body_str
    signature = generate_signature(API_SECRET, message)

    headers = {
        "api-key":      API_KEY,
        "timestamp":    timestamp,
        "signature":    signature,
        "Content-Type": "application/json"
    }

    try:
        if method == "POST":
            response = requests.post(BASE_URL + path, headers=headers, data=body_str, timeout=10)
        else:
            response = requests.get(BASE_URL + path, headers=headers, timeout=10)

        print(f"🌐 HTTP {response.status_code} from Delta Exchange")
        return response.json()

    except requests.exceptions.Timeout:
        print("❌ ERROR: Request timed out — Delta Exchange did not respond in 10s")
        return {}
    except requests.exceptions.ConnectionError as e:
        print(f"❌ ERROR: Connection failed — {e}")
        return {}
    except Exception as e:
        print(f"❌ ERROR: Unexpected error — {e}")
        return {}

# ----------------- PLACE ORDER -----------------
def place_order(side, size=ORDER_SIZE):
    body = {
        "product_id": PRODUCT_ID,
        "order_type": "market_order",
        "side":        side,
        "size":        size
    }
    notional = round(size * 71, 2)
    margin   = round(size * 0.71, 2)
    print(f"📤 Placing {side.upper()} | {size} contracts | Notional ~${notional} | Margin ~${margin}")
    print(f"📦 Request body: {json.dumps(body)}")

    result = make_request("POST", "/v2/orders", body)

    print(f"📨 Full response: {result}")   # print full response always

    if result.get("success"):
        fill_price = result["result"].get("average_fill_price", "N/A")
        print(f"✅ Filled at: {fill_price}")
    elif result:
        error = result.get("error", {})
        code  = error.get("code", "unknown")
        ctx   = error.get("context", {})
        print(f"❌ Order failed — code: {code} | context: {ctx}")
    else:
        print("❌ Empty response from Delta Exchange")

    return result

# ----------------- BUY LOGIC -----------------
def buy():
    global current_position

    if current_position == "LONG":
        print("🟢 Already LONG — skipping buy")
        return

    if current_position == "SHORT":
        print(f"🔄 Reversing SHORT → LONG ({ORDER_SIZE * 2} contracts)")
        result = place_order("buy", ORDER_SIZE * 2)
    else:
        print(f"🟢 Opening LONG ({ORDER_SIZE} contracts)")
        result = place_order("buy", ORDER_SIZE)

    current_position = "LONG"
    print(f"📊 Position: LONG | {ORDER_SIZE} contracts")
    return result

# ----------------- SELL LOGIC -----------------
def sell():
    global current_position

    if current_position == "SHORT":
        print("🔴 Already SHORT — skipping sell")
        return

    if current_position == "LONG":
        print(f"🔄 Reversing LONG → SHORT ({ORDER_SIZE * 2} contracts)")
        result = place_order("sell", ORDER_SIZE * 2)
    else:
        print(f"🔴 Opening SHORT ({ORDER_SIZE} contracts)")
        result = place_order("sell", ORDER_SIZE)

    current_position = "SHORT"
    print(f"📊 Position: SHORT | {ORDER_SIZE} contracts")
    return result

# ----------------- SIGNAL HANDLER -----------------
def handle_signal(signal):
    signal = signal.strip().upper()
    print(f"\n{'='*50}")
    print(f"📩 Signal   : {signal}")
    print(f"📊 Position : {current_position}")
    print(f"💰 Size     : {ORDER_SIZE} contracts | Leverage: 100x")
    print(f"🔑 API Key  : {API_KEY[:8]}..." if API_KEY else "❌ API_KEY is missing!")
    print(f"🔑 Secret   : {'SET' if API_SECRET else '❌ MISSING'}")
    print(f"{'='*50}")

    if not API_KEY or not API_SECRET:
        print("❌ CRITICAL: API_KEY or API_SECRET environment variable is not set!")
        print("   Go to Render → Environment → add API_KEY and API_SECRET")
        return

    if "BUY" in signal:
        buy()
    elif "SELL" in signal:
        sell()
    else:
        print(f"⚠️ Unknown signal: '{signal}'")
