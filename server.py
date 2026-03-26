from flask import Flask, request, jsonify
import main as bot
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
        thread = threading.Thread(target=bot.handle_signal, args=(raw_signal,))
        thread.daemon = True
        thread.start()

    return jsonify({"status": "ok"})

@app.route('/status', methods=['GET'])
def status():
    """Check what position the bot thinks it has in memory."""
    return jsonify({
        "current_position": bot.current_position,
        "order_size":       bot.ORDER_SIZE,
        "product_id":       bot.PRODUCT_ID,
    })

@app.route('/sync', methods=['GET'])
def sync():
    """Force re-sync position from Delta Exchange and return result."""
    bot.sync_position_from_exchange()
    return jsonify({
        "current_position": bot.current_position,
        "message": "Synced from Delta Exchange"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
