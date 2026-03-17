from flask import Flask, request, jsonify
from main import handle_signal
import os

app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    # TradingView Pine v5 alert() sends plain text
    raw_signal = request.data.decode("utf-8").strip()

    print("\n🔥 ALERT RECEIVED 🔥")
    print(raw_signal)
    print("====================")

    if raw_signal:
        handle_signal(raw_signal)

    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

