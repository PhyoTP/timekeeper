import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from datetime import datetime
import pytz
import requests

load_dotenv()

# Initializes your app with your bot token and socket mode handler
app = App(token=os.getenv("SLACK_BOT_TOKEN"))

# get time 
@app.command("/get_time")
def handle_get_time(ack, respond, command):
    ack()
    timezone_args = command.get("text", "").strip().split()

    try:
        org_timezone_name = timezone_args[0] if len(timezone_args) > 0 else "UTC"
        org_timezone = pytz.timezone(org_timezone_name)

        if len(timezone_args) > 1:
            time_parts = list(map(int, timezone_args[1].split(":")))
        else:
            time_parts = [0, 0, 0, 0]  # hour, min, sec, microsec

        while len(time_parts) < 4:
            time_parts.append(0)

        now = datetime.now()
        default_day = now.day
        default_month = now.month
        default_year = now.year

        if len(timezone_args) > 2:
            date_parts = list(map(int, timezone_args[2].split("/")))

            # Fill in missing values from current date
            if len(date_parts) == 1:
                day = date_parts[0]
                month = default_month
                year = default_year
            elif len(date_parts) == 2:
                day, month = date_parts
                year = default_year
            elif len(date_parts) == 3:
                day, month, year = date_parts
            else:
                raise ValueError("Invalid date format. Use DD, DD/MM, or DD/MM/YYYY.")
        else:
            # Default to today
            day = default_day
            month = default_month
            year = default_year
        # Format: datetime(year, month, day, hour, minute, second, microsecond)
        dt = datetime(
            year=year,
            month=month,
            day=day,
            hour=time_parts[0],
            minute=time_parts[1],
            second=time_parts[2],
            microsecond=time_parts[3],
        )

        # Localize in origin timezone
        dt = org_timezone.localize(dt)
        if len(timezone_args) > 3:
            user_tz_name = timezone_args[3]
        else:
            response = requests.get(
                f"https://slack.com/api/users.info?user={command['user_id']}",
                headers={"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"}
            ).json()
            user_tz_name = response.get("user", {}).get("tz", "UTC")
            
        res_timezone = pytz.timezone(user_tz_name)
        # Convert to result timezone
        converted = dt.astimezone(res_timezone)

        respond(f"🕒 Time in `{user_tz_name}`: `{converted.strftime('%Y-%m-%d %H:%M:%S')}`")

    except pytz.UnknownTimeZoneError:
        respond("❌ Unknown timezone. Please use a valid timezone like `Asia/Singapore`, `US/Pacific`, or `Europe/Berlin`.")
    except Exception as e:
        respond(f"❌ Error parsing time: `{str(e)}`")

# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN")).start()