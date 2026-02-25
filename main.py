from apscheduler.schedulers.background import BackgroundScheduler
from notifications import send_weekly_business_report
from app import app


# Start Scheduler
scheduler = BackgroundScheduler()

scheduler.add_job(
    send_weekly_business_report,
    'interval',
    minutes=1   # change to weeks=1 later
)

scheduler.start()
print("Scheduler started ✅")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)