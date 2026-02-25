from apscheduler.schedulers.background import BackgroundScheduler
from notifications import send_weekly_business_report

import threading
import webbrowser
import webview
from app import app


# --------------------------------------------------
# PyWebView API — exposed to JavaScript as
#   window.pywebview.api.<method>()
# --------------------------------------------------
class PyWebViewAPI:
    def open_download(self, url):
        """Open a URL in the system default browser so file downloads work.
        PyWebView's embedded browser does not save files to disk via
        <a download>, so we hand off to the real browser instead."""
        webbrowser.open(url)


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
    api = PyWebViewAPI()

    webview.create_window(
        title="Invoice Application",
        url="http://127.0.0.1:5004",
        width=1200,
        height=800,
        js_api=api          # exposes window.pywebview.api in JS
    )

    webview.start()

