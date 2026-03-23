import requests
import time
import hashlib
import hmac
import json
import os

# ----------------- CONFIG -----------------
API_KEY    = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")

# !! LIVE ACCOUNT -- REAL MONEY !!
BASE_URL = "https://api.india.delta.exchange"      # LIVE endpoint
PRODUCT_ID = 84                                  # BTCUSD Perpetual

# ----------------- POSITION SIZING (10x LEVERAGE) -----------------
#
# !! LIVE ACCOUNT -- REAL MONEY !!
#
# Capital            : Rs.5,000 (~$53.65 at Rs.93.2/USD)
# Leverage           : 10x  (set manually on Delta Exchange UI)
# BTC price (approx) : ~$84,000
# 1 contract value   : $84  (0.001 BTC notional)
# Margin/contract    : $8.40 at 10x
#
# ORDER_SIZE = 1 contract
#   -> Notional value      : $84     (~Rs.7,829)
#   -> Margin per trade    : $8.40   (15.7% of capital)
#   -> Reversal margin     : $16.80  (31.3% of capital)
#   -> Liquidation buffer  : $45.25  (84.3% of capital -- very safe)
#   -> Fee per order       : $0.0496 (~Rs.4.62)  [0.05% + 18% GST]
#   -> Round trip fee      : $0.0991 (~Rs.9.24)
#   -> Break-even BTC move : 0.118%  (~$99 price move)
#   -> Daily fees (4 trades): Rs.37
#   -> Monthly fees (22 days): Rs.813
#
# Why 10x and not 25x?
#   -> Lower fees (fees are on notional, not margin)
#   -> Much safer liquidation buffer
#   -> 1 contract keeps monthly fees at Rs.813 (vs Rs.1,219 at 25x)
#   -> Still profitable if win rate is 55%+

ORDER_SIZE = 1        # 1 contract -- optimal for Rs.5,000 live capital

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

        print(f"🌐 HTTP {response.status_code}")
        return response.json()

    except requests.exceptions.Timeout:
        print("❌ Request timed out")
        return {}
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {e}")
        return {}
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return {}

# ----------------- GET FREE BALANCE -----------------
def get_free_balance():
    result = make_request("GET", "/v2/wallet/balances")
    try:
        for b in result.get("result", []):
            if b.get("asset_symbol") == "USD":
                available = float(b.get("available_balance", 0))
                total     = float(b.get("balance", 0))
                print(f"💰 Balance — Total: ${total:.2f} (~Rs.{total*93.2:.0f}) | Free: ${available:.2f} (~Rs.{available*93.2:.0f})")
                return available
    except Exception as e:
        print(f"⚠️ Could not fetch balance: {e}")
    return None

# ----------------- PLACE ORDER -----------------
def place_order(side, size=ORDER_SIZE):
    body = {
        "product_id": PRODUCT_ID,
        "order_type": "market_order",
        "side":        side,
        "size":        size
    }
    notional = round(size * 84, 2)
    margin   = round(size * 8.40, 2)
    fee_est  = round(notional * 0.00059, 4)   # 0.05% + 18% GST
    print(f"📤 {side.upper()} | {size} contract(s) | Notional ~${notional} | Margin ~${margin} | Est. fee ~${fee_est}")

    result = make_request("POST", "/v2/orders", body)
    print(f"📨 Response: {result}")

    if result.get("success"):
        fill_price = result["result"].get("average_fill_price", "N/A")
        print(f"✅ Filled at: {fill_price}")
    elif result:
        error = result.get("error", {})
        code  = error.get("code", "unknown")
        ctx   = error.get("context", {})
        print(f"❌ Failed — {code} | {ctx}")

        if code == "insufficient_margin":
            avail = ctx.get("available_balance", "?")
            extra = ctx.get("required_additional_balance", "?")
            print(f"💡 Free: ${avail} | Need extra: ${extra}")
            print(f"💡 Set leverage to 10x on Delta Exchange UI first")
        elif code == "ip_not_whitelisted_for_api_key":
            ip = ctx.get("client_ip", "?")
            print(f"💡 Add {ip} to your live API key whitelist on Delta Exchange")
        elif code == "order_size_too_small":
            print(f"💡 Minimum order size not met — check Delta Exchange minimums")
    else:
        print("❌ Empty response from Delta Exchange")

    return result

# ----------------- BUY LOGIC -----------------
def buy():
    global current_position

    if current_position == "LONG":
        print("🟢 Already LONG — skipping")
        return

    if current_position == "SHORT":
        # 2x order: closes SHORT (1) + opens LONG (1) in single order
        print(f"🔄 Reversing SHORT → LONG ({ORDER_SIZE * 2} contract(s))")
        result = place_order("buy", ORDER_SIZE * 2)
    else:
        print(f"🟢 Opening LONG ({ORDER_SIZE} contract(s))")
        result = place_order("buy", ORDER_SIZE)

    if result and result.get("success"):
        current_position = "LONG"
        print(f"📊 Position: LONG | {ORDER_SIZE} contract(s) | Break-even: +0.118% BTC move")
    else:
        print(f"⚠️ Order failed — position unchanged: {current_position}")

    return result

# ----------------- SELL LOGIC -----------------
def sell():
    global current_position

    if current_position == "SHORT":
        print("🔴 Already SHORT — skipping")
        return

    if current_position == "LONG":
        # 2x order: closes LONG (1) + opens SHORT (1) in single order
        print(f"🔄 Reversing LONG → SHORT ({ORDER_SIZE * 2} contract(s))")
        result = place_order("sell", ORDER_SIZE * 2)
    else:
        print(f"🔴 Opening SHORT ({ORDER_SIZE} contract(s))")
        result = place_order("sell", ORDER_SIZE)

    if result and result.get("success"):
        current_position = "SHORT"
        print(f"📊 Position: SHORT | {ORDER_SIZE} contract(s) | Break-even: +0.118% BTC move")
    else:
        print(f"⚠️ Order failed — position unchanged: {current_position}")

    return result

# ----------------- SIGNAL HANDLER -----------------
def handle_signal(signal):
    signal = signal.strip().upper()
    print(f"\n{'='*55}")
    print(f"📩 Signal     : {signal}")
    print(f"📊 Position   : {current_position}")
    print(f"📐 Size       : {ORDER_SIZE} contract | 10x | LIVE ACCOUNT")
    print(f"💸 Break-even : 0.118% BTC move (~Rs.9.24 profit needed)")

    if not API_KEY or not API_SECRET:
        print("❌ API_KEY or API_SECRET missing in Render environment!")
        return

    get_free_balance()
    print(f"{'='*55}")

    if "BUY" in signal:
        buy()
    elif "SELL" in signal:
        sell()
    else:
        print(f"⚠️ Unknown signal: '{signal}'")
        print("   Valid: BUY | SELL")
