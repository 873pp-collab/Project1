from flask import Flask, request, jsonify
from main import handle_signal
import threading
import os

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    raw_signal = request.data.decode("utf-8").strip()

    print("\n🔥 ALERT RECEIVED 🔥")
    print(raw_signal)
    print("====================")

    if raw_signal:
        # KEY FIX: respond to TradingView immediately (within 1-2ms)
        # then process the order in a background thread.
        #
        # Why? TradingView has a strict 5-second webhook timeout.
        # Our bot needs to call Delta's API twice (balance check +
        # order placement) which can take 3-8 seconds total,
        # especially when Render wakes from sleep. By returning
        # {"status": "ok"} instantly, TradingView never times out.
        # The order still executes correctly in the background thread.
        thread = threading.Thread(target=handle_signal, args=(raw_signal,))
        thread.daemon = True   # thread dies cleanly if server restarts
        thread.start()

    # This response goes back to TradingView in <100ms -- no more timeouts!
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
