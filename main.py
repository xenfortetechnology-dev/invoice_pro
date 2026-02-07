# import os
# import threading

# from app import app

# def new_func():
#     return True

# app.debug = new_func()

# def run_flask():
#     app.run(
#         host='127.0.0.1',
#         port=5004,
#         debug=False,
#         use_reloader=False
#     )

# def on_closed():
#     os._exit(0) 

# if __name__ == '__main__':
#     flask_thread = threading.Thread(target=run_flask)
#     flask_thread.daemon = True
#     flask_thread.start()

#     window = webview.create_window(
#         title='Revolutionary Invoice',
#         url='http://127.0.0.1:5004',
#         width=1200,
#         height=800,
#         resizable=True
#     )

#     window.events.closed += on_closed
#     webview.start(gui='edgechromium')



# import threading
# import webview
# from app import app


# def start_flask():
#     app.run(
#         host="127.0.0.1",
#         port=5004,
#         debug=False,        # ❌ NEVER True in exe
#         use_reloader=False # ❌ MUST be False
#     )


# if __name__ == "__main__":
#     threading.Thread(target=start_flask, daemon=True).start()

#     webview.create_window(
#         title="Invoice Application",
#         url="http://127.0.0.1:5004",
#         width=1200,
#         height=800
#     )

#     webview.start()



# for web application testing

import threading
import webview
from app import app


def start_flask():
    app.run(
        host="127.0.0.1",
        port=5004,
        debug=False,        # ❌ NEVER True in exe
        use_reloader=False # ❌ MUST be False
    )


if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()

    webview.create_window(
        title="Invoice Application",
        url="http://127.0.0.1:5004",
        width=1200,
        height=800
    )

    webview.start()

