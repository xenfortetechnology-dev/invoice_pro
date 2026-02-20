from apscheduler.schedulers.background import BackgroundScheduler
from notifications import send_weekly_business_report

import threading
import webview
from app import app


def start_flask():
    app.run(
        host="127.0.0.1",
        port=5004,
        debug=False,
        use_reloader=False
    )


if __name__ == "__main__":

    # Start Flask
    threading.Thread(target=start_flask, daemon=True).start()

    # Start Scheduler
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        send_weekly_business_report,   # ✅ No lambda
        'interval',
        minutes=1   # change to weeks=1 later
    )

    scheduler.start()
    print("Scheduler started ✅")

    # Start Webview
    webview.create_window(
        title="Invoice Application",
        url="http://127.0.0.1:5004",
        width=1200,
        height=800
    )

    webview.start()
