import requests
import time
import hashlib
import hmac
import json
import os

# ----------------- CONFIG -----------------
API_KEY    = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
BASE_URL   = "https://api.india.delta.exchange"  # LIVE endpoint
PRODUCT_ID = 27                                   # BTCUSD Perpetual (live)

# ----------------- POSITION SIZING (AGGRESSIVE) -----------------
#
# !! LIVE ACCOUNT -- REAL MONEY !!
#
# Balance            : ~$57.65
# Leverage           : 10x  (set on Delta Exchange UI)
# BTC price (approx) : ~$70,500
# 1 contract value   : $70.50 (0.001 BTC)
# Margin/contract    : $7.05  at 10x
#
# ORDER_SIZE = 3 contracts  (maximum safe for reversal orders)
#   -> Notional value      : $211.50  (~Rs.19,712)
#   -> Normal margin       : $21.15   (36.7% of balance)
#   -> Reversal margin     : $42.30   (73.4% of balance)  <-- 2x order
#   -> Liquidation buffer  : $36.50   (63.3% of balance)
#   -> Fee per trade       : $0.1248  (~Rs.11.63)
#   -> Daily fees (4 trades): $0.50   (~Rs.47)
#   -> Monthly fees        : $10.98   (~Rs.1,023)
#
# WHY 3 AND NOT 7?
#   When reversing (SHORT->LONG or LONG->SHORT), the bot places
#   a 2x order (ORDER_SIZE * 2 = 6 contracts). That reversal
#   order needs $42.30 margin. Going above 3 contracts would
#   push the reversal margin past 90% of balance, risking
#   insufficient_margin errors and liquidation on volatile moves.
#
# PROFIT POTENTIAL:
#   0.5% BTC move in your favour = +$0.81 (~Rs.75) per trade
#   1.0% BTC move in your favour = +$1.87 (~Rs.174) per trade
#   Break-even = 0.118% move     = ~$83 price change

ORDER_SIZE = 3   # aggressive but safe maximum for $57.65 balance at 10x

# ----------------- POSITION STATE -----------------
# Always synced from Delta API on startup -- never assumes None
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

# ----------------- SYNC POSITION FROM DELTA -----------------
# Called every time the server starts/restarts. This is the fix
# that prevents duplicate trades when Render free tier restarts.
# Instead of blindly assuming no position, we ask Delta directly.
def sync_position_from_exchange():
    global current_position

    print("🔄 Syncing position from Delta Exchange...")
    result = make_request("GET", f"/v2/positions?product_id={PRODUCT_ID}")

    try:
        positions = result.get("result", [])

        if not positions:
            current_position = None
            print("📊 Synced: No open position (flat)")
            return

        for pos in positions:
            size = float(pos.get("size", 0))
            entry = pos.get("entry_price", "N/A")
            side  = pos.get("side", "")

            if size > 0 and side == "buy":
                current_position = "LONG"
                print(f"📊 Synced: LONG | size={size} contracts | entry={entry}")
                return
            elif size > 0 and side == "sell":
                current_position = "SHORT"
                print(f"📊 Synced: SHORT | size={size} contracts | entry={entry}")
                return

        current_position = None
        print("📊 Synced: No open position (flat)")

    except Exception as e:
        print(f"⚠️ Sync failed: {e} — defaulting to None")
        current_position = None

# Sync immediately on startup before any signal arrives
sync_position_from_exchange()

# ----------------- GET FREE BALANCE -----------------
def get_free_balance():
    result = make_request("GET", "/v2/wallet/balances")
    try:
        for b in result.get("result", []):
            if b.get("asset_symbol") == "USD":
                available = float(b.get("available_balance", 0))
                total     = float(b.get("balance", 0))
                print(f"💰 Total: ${total:.2f} (~Rs.{total*93.2:.0f}) | Free: ${available:.2f} (~Rs.{available*93.2:.0f})")
                return available
    except Exception as e:
        print(f"⚠️ Balance fetch failed: {e}")
    return None

# ----------------- PLACE ORDER -----------------
def place_order(side, size=ORDER_SIZE):
    body = {
        "product_id": PRODUCT_ID,
        "order_type": "market_order",
        "side":        side,
        "size":        size
    }
    notional = round(size * 70.5, 2)   # approx, updates with BTC price
    margin   = round(size * 7.05, 2)
    fee_est  = round(notional * 0.00059, 4)
    print(f"📤 {side.upper()} | {size} contracts | Notional ~${notional} | Margin ~${margin} | Fee ~${fee_est}")

    result = make_request("POST", "/v2/orders", body)

    if result.get("success"):
        r = result["result"]
        fill_price = r.get("average_fill_price", "N/A")
        comm       = r.get("paid_commission", "N/A")
        pnl        = r.get("meta_data", {}).get("pnl", "N/A")
        print(f"✅ Filled at: {fill_price} | PnL: {pnl} | Commission: {comm}")
    elif result:
        error = result.get("error", {})
        code  = error.get("code", "unknown")
        ctx   = error.get("context", {})
        print(f"❌ Failed — {code}")

        if code == "insufficient_margin":
            print(f"💡 Free: ${ctx.get('available_balance','?')} | Need extra: ${ctx.get('required_additional_balance','?')}")
            print(f"💡 Reduce ORDER_SIZE or deposit more capital")
        elif code == "ip_not_whitelisted_for_api_key":
            print(f"💡 Add {ctx.get('client_ip')} to API key whitelist on Delta")
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
        # Single order of 2x size closes existing SHORT and opens new LONG
        # This is more efficient than two separate orders (saves one fee)
        print(f"🔄 Reversing SHORT → LONG ({ORDER_SIZE * 2} contracts)")
        result = place_order("buy", ORDER_SIZE * 2)
    else:
        print(f"🟢 Opening LONG ({ORDER_SIZE} contracts)")
        result = place_order("buy", ORDER_SIZE)

    if result and result.get("success"):
        current_position = "LONG"
        print(f"📊 Position: LONG | {ORDER_SIZE} contracts | Break-even: +0.118%")
    else:
        # Re-sync so we know the true state after a failed order
        print("⚠️ Order failed — re-syncing from Delta...")
        sync_position_from_exchange()

    return result

# ----------------- SELL LOGIC -----------------
def sell():
    global current_position

    if current_position == "SHORT":
        print("🔴 Already SHORT — skipping")
        return

    if current_position == "LONG":
        # Single order of 2x size closes existing LONG and opens new SHORT
        print(f"🔄 Reversing LONG → SHORT ({ORDER_SIZE * 2} contracts)")
        result = place_order("sell", ORDER_SIZE * 2)
    else:
        print(f"🔴 Opening SHORT ({ORDER_SIZE} contracts)")
        result = place_order("sell", ORDER_SIZE)

    if result and result.get("success"):
        current_position = "SHORT"
        print(f"📊 Position: SHORT | {ORDER_SIZE} contracts | Break-even: +0.118%")
    else:
        print("⚠️ Order failed — re-syncing from Delta...")
        sync_position_from_exchange()

    return result

# ----------------- SIGNAL HANDLER -----------------
def handle_signal(signal):
    signal = signal.strip().upper()
    print(f"\n{'='*58}")
    print(f"📩 Signal     : {signal}")
    print(f"📊 Position   : {current_position}")
    print(f"📐 Size       : {ORDER_SIZE} contracts | 10x | LIVE | AGGRESSIVE")
    print(f"💸 Break-even : 0.118% BTC move (~Rs.11.63 fee per trade)")

    if not API_KEY or not API_SECRET:
        print("❌ API_KEY or API_SECRET missing in Render environment!")
        return

    get_free_balance()
    print(f"{'='*58}")

    if "BUY" in signal:
        buy()
    elif "SELL" in signal:
        sell()
    else:
        print(f"⚠️ Unknown signal: '{signal}'")
        print("   Valid signals: BUY | SELL")
