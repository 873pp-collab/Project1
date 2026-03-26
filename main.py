import requests
import time
import hashlib
import hmac
import json
import os

# ----------------- CONFIG -----------------
API_KEY    = os.environ.get("API_KEY")
API_SECRET = os.environ.get("API_SECRET")
BASE_URL   = "https://api.india.delta.exchange"
PRODUCT_ID = 27  # BTCUSD Perpetual (live)

# ----------------- POSITION SIZING -----------------
ORDER_SIZE = 7

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
            response = requests.post(
                BASE_URL + path, headers=headers, data=body_str, timeout=10
            )
        else:
            response = requests.get(
                BASE_URL + path, headers=headers, timeout=10
            )

        print(f"🌐 HTTP {response.status_code} | {method} {path}")

        # Always print first 500 chars of raw body so we can debug
        raw_text = response.text
        print(f"📥 Raw response: {raw_text[:500]}")

        # Guard: parse JSON safely
        try:
            data = response.json()
        except Exception as e:
            print(f"⚠️ JSON parse failed: {e}")
            return {}

        # Guard: must be a dict
        if not isinstance(data, dict):
            print(f"⚠️ Response is not a dict, got {type(data)}: {str(data)[:300]}")
            return {}

        return data

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
def sync_position_from_exchange():
    global current_position

    print("🔄 Syncing position from Delta Exchange...")

    if not API_KEY or not API_SECRET:
        print("❌ API_KEY or API_SECRET not set — cannot sync!")
        current_position = None
        return

    # Retry up to 3x — cold boot network may not be ready
    for attempt in range(1, 4):
        result = make_request("GET", f"/v2/positions?product_id={PRODUCT_ID}")

        if not result:
            print(f"⚠️ Sync attempt {attempt}/3 got empty dict — retrying in 3s...")
            time.sleep(3)
            continue

        # Check for API-level errors
        if not result.get("success", False):
            print(f"⚠️ API returned success=false: {result}")
            time.sleep(3)
            continue

        try:
            raw = result.get("result", [])
            print(f"📋 Positions raw result: {raw}")

            # Flat account: result can be {}, [], or None
            if not raw:
                current_position = None
                print("📊 Synced: No open position (flat)")
                return

            # Normalise: could be a single dict or a list
            positions = raw if isinstance(raw, list) else [raw]

            matched = False
            for pos in positions:
                if not isinstance(pos, dict):
                    continue
                size  = float(pos.get("size", 0))
                side  = pos.get("side", "")
                entry = pos.get("entry_price", "N/A")

                if size > 0 and side == "buy":
                    current_position = "LONG"
                    print(f"📊 Synced: LONG | size={size} contracts | entry={entry}")
                    matched = True
                    return
                elif size > 0 and side == "sell":
                    current_position = "SHORT"
                    print(f"📊 Synced: SHORT | size={size} contracts | entry={entry}")
                    matched = True
                    return

            if not matched:
                current_position = None
                print("📊 Synced: No open position (flat)")
            return

        except Exception as e:
            print(f"⚠️ Sync parse error on attempt {attempt}/3: {e}")
            print(f"   Full result: {result}")
            time.sleep(3)

    print("❌ Sync failed after 3 attempts — position set to None")
    print("   ⚠️ Check API key, secret, and IP whitelist on Delta Exchange!")
    current_position = None

# Runs immediately when server boots
sync_position_from_exchange()

# ----------------- GET FREE BALANCE -----------------
def get_free_balance():
    result = make_request("GET", "/v2/wallet/balances")
    try:
        for b in result.get("result", []):
            if isinstance(b, dict) and b.get("asset_symbol") == "USD":
                available = float(b.get("available_balance", 0))
                total     = float(b.get("balance", 0))
                print(
                    f"💰 Total: ${total:.2f} (~Rs.{total*93.2:.0f}) "
                    f"| Free: ${available:.2f} (~Rs.{available*93.2:.0f})"
                )
                return available
    except Exception as e:
        print(f"⚠️ Balance fetch failed: {e}")
    return None

# ----------------- PLACE ORDER -----------------
def place_order(side, size=ORDER_SIZE, reduce_only=False):
    body = {
        "product_id":  PRODUCT_ID,
        "order_type":  "market_order",
        "side":        side,
        "size":        size,
        "reduce_only": reduce_only
    }
    notional = round(size * 70.5, 2)
    margin   = round(size * 7.05, 2)
    fee_est  = round(notional * 0.00059, 4)
    label    = "CLOSE" if reduce_only else "OPEN"
    print(
        f"📤 [{label}] {side.upper()} | {size} contracts | "
        f"Notional ~${notional} | Margin ~${margin} | Est. fee ~${fee_est}"
    )

    result = make_request("POST", "/v2/orders", body)

    if result.get("success"):
        r          = result["result"]
        fill_price = r.get("average_fill_price", "N/A")
        commission = r.get("paid_commission", "N/A")
        pnl        = r.get("meta_data", {}).get("pnl", "0")
        print(f"✅ [{label}] Filled at: {fill_price} | PnL: {pnl} | Commission: {commission}")
    elif result:
        error = result.get("error", {}) or {}
        code  = error.get("code", "unknown")
        ctx   = error.get("context", {}) or {}
        print(f"❌ [{label}] Failed — {code}")
        if code == "insufficient_margin":
            print(f"💡 Free: ${ctx.get('available_balance','?')} | Extra needed: ${ctx.get('required_additional_balance','?')}")
        elif code == "ip_not_whitelisted_for_api_key":
            print(f"💡 Add {ctx.get('client_ip')} to API key whitelist on Delta")
    else:
        print(f"❌ [{label}] Empty response from Delta Exchange")

    return result

# ----------------- BUY LOGIC -----------------
def buy():
    global current_position

    # Always re-sync from exchange — never trust in-memory state after restart
    sync_position_from_exchange()

    if current_position == "LONG":
        print("🟢 Already LONG — skipping duplicate signal")
        return

    if current_position == "SHORT":
        print(f"🔄 Step 1/2 — Closing SHORT ({ORDER_SIZE} contracts)...")
        close_result = place_order("buy", ORDER_SIZE, reduce_only=True)

        if not close_result.get("success"):
            print("⚠️ Close SHORT failed — aborting open. Re-syncing...")
            sync_position_from_exchange()
            return

        print("✅ SHORT closed")
        time.sleep(0.5)

    print(f"🟢 Opening LONG ({ORDER_SIZE} contracts)...")
    result = place_order("buy", ORDER_SIZE, reduce_only=False)

    if result and result.get("success"):
        current_position = "LONG"
        print(f"📊 Position: LONG | {ORDER_SIZE} contracts | Liq trigger: BTC -10%")
    else:
        print("⚠️ Open LONG failed — re-syncing...")
        sync_position_from_exchange()

    return result

# ----------------- SELL LOGIC -----------------
def sell():
    global current_position

    # Always re-sync from exchange — never trust in-memory state after restart
    sync_position_from_exchange()

    if current_position == "SHORT":
        print("🔴 Already SHORT — skipping duplicate signal")
        return

    if current_position == "LONG":
        print(f"🔄 Step 1/2 — Closing LONG ({ORDER_SIZE} contracts)...")
        close_result = place_order("sell", ORDER_SIZE, reduce_only=True)

        if not close_result.get("success"):
            print("⚠️ Close LONG failed — aborting open. Re-syncing...")
            sync_position_from_exchange()
            return

        print("✅ LONG closed")
        time.sleep(0.5)

    print(f"🔴 Opening SHORT ({ORDER_SIZE} contracts)...")
    result = place_order("sell", ORDER_SIZE, reduce_only=False)

    if result and result.get("success"):
        current_position = "SHORT"
        print(f"📊 Position: SHORT | {ORDER_SIZE} contracts | Liq trigger: BTC +10%")
    else:
        print("⚠️ Open SHORT failed — re-syncing...")
        sync_position_from_exchange()

    return result

# ----------------- SIGNAL HANDLER -----------------
def handle_signal(signal):
    signal = signal.strip().upper()
    print(f"\n{'='*60}")
    print(f"📩 Signal     : {signal}")
    print(f"📐 Size       : {ORDER_SIZE} contracts | 10x | LIVE | Rs.10,000")
    print(f"💸 Break-even : 0.118% BTC move (~Rs.46.52 round-trip fee)")
    print(f"🛡️  Liq safety : 10% BTC move needed to liquidate")

    if not API_KEY or not API_SECRET:
        print("❌ API_KEY or API_SECRET missing in Render environment!")
        return

    get_free_balance()
    print(f"{'='*60}")

    if "BUY" in signal:
        buy()
    elif "SELL" in signal:
        sell()
    else:
        print(f"⚠️ Unknown signal: '{signal}'")
