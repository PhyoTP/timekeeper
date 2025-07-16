import os
from slack_bolt import App
from dotenv import load_dotenv
from datetime import datetime
import pytz
import requests
import json

load_dotenv()

# Initializes your app with your bot token and socket mode handler
app = App(token=os.getenv("SLACK_BOT_TOKEN"), signing_secret=os.getenv("SLACK_SIGNING_SECRET"))
# Get the directory of the current file (__init__.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Construct full path to events.json inside the same folder
events_path = os.path.join(BASE_DIR, "events.json")
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
            time_parts = list(datetime.now(org_timezone).timetuple()[:6][3:7])  # Get current time in org timezone

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

@app.command("/get_event")
def handle_get_event(ack, respond, command):
    ack()
    command_args = command.get("text", "").strip().split()
    event_id = command_args[0] if command_args else None
    if len(command_args) > 1:
        timezone_name = command_args[1]
    else:
        response = requests.get(
            f"https://slack.com/api/users.info?user={command['user_id']}",
            headers={"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"}
        ).json()
        timezone_name = response.get("user", {}).get("tz", "UTC")
    if not event_id:
        respond("❌ Please provide an event ID.")
        return

    try:
        with open(events_path, "r") as f:
            events = json.load(f)

        event = events.get(event_id)
        if not event:
            respond(f"❌ No event found with ID `{event_id}`.")
            return
        
        timestamp = datetime.fromtimestamp(event["timestamp"], pytz.timezone(timezone_name))
        respond(f"📅 Event: \n```{event['description']}```\n"
                f"🕒 Time: `{timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}`\n"
                f"👤 Created by: <@{event['created_by']}>")

    except FileNotFoundError:
        respond("❌ Events file not found.")
    except json.JSONDecodeError:
        respond("❌ Error reading events file.")
    except Exception as e:
        respond(f"❌ Error retrieving event: `{str(e)}`")

@app.command("/set_event")
def handle_set_event(ack, respond, command, client):
    ack()
    code = command.get("text", "").strip()
    if not code:
        respond("❌ Please provide an event ID.")
        return
    try:
        # Get user's timezone
        response = requests.get(
            f"https://slack.com/api/users.info?user={command['user_id']}",
            headers={"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"}
        ).json()
        user_timezone_name = response.get("user", {}).get("tz", "UTC")
        user_timezone = pytz.timezone(user_timezone_name)
        
        with open(events_path, "r") as f:
            events = json.load(f)

        event = events.get(code)
        if event:
            if command["user_id"] != event["created_by"]:
                respond("❌ Event has been created by another user.")
                return
        else:
            event = {
                "description": "",
                "timestamp": datetime.now().timestamp(),
                "created_by": command["user_id"]
            }
        # Convert event timestamp to user's timezone for display
        event_datetime_utc = datetime.fromtimestamp(event["timestamp"], pytz.UTC)
        event_datetime_user_tz = event_datetime_utc.astimezone(user_timezone)
        
        client.views_open(
            trigger_id=command["trigger_id"],
            view={
                "type": "modal",
                "callback_id": "save_event",
                "title": {
                    "type": "plain_text",
                    "text": "Event Details",
                    "emoji": True
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Submit",
                    "emoji": True
                },
                "close": {
                    "type": "plain_text",
                    "text": "Cancel",
                    "emoji": True
                },
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "code_block",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "code_input",
                            "initial_value": code
                        },
                        "label": {
                            "type": "plain_text",
                            "text": "Event code",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "block_id": "datepicker_block",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Date (in {user_timezone_name}):"
                        },
                        "accessory": {
                            "type": "datepicker",
                            "initial_date": event_datetime_user_tz.strftime("%Y-%m-%d"),
                            "placeholder": {
                                "type": "plain_text",
                                "text": "Select a date",
                                "emoji": True
                            },
                            "action_id": "datepicker"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"Time (in {user_timezone_name}):"
                        }
                    },
                    {
                        "type": "actions",
                        "block_id": "timepicker_block",
                        "elements": [
                            {
                                "type": "timepicker",
                                "initial_time": event_datetime_user_tz.strftime("%H:%M"),
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "Select time",
                                    "emoji": True
                                },
                                "action_id": "timepicker"
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Current time and day",
                                    "emoji": True
                                },
                                "value": "click_me_123",
                                "action_id": "reset_time"
                            }
                        ]
                    },
                    {
                        "type": "input",
                        "block_id": "description_block",
                        "element": {
                            "type": "plain_text_input",
                            "multiline": True,
                            "action_id": "description_input",
                            "initial_value": event["description"]
                        },
                        "label": {
                            "type": "plain_text",
                            "text": "Description",
                            "emoji": True
                        }
                    }
                ],
                "private_metadata": json.dumps({
                    "original_code": code,
                    "user_timezone": user_timezone_name
                }),
            }
        )
    except FileNotFoundError:
        respond("❌ Events file not found.")
    except json.JSONDecodeError:
        respond("❌ Error reading events file.")
    except Exception as e:
        respond(f"❌ Error retrieving event: `{str(e)}`")

@app.view("save_event")
def handle_save_event(ack, body, view):
    new_code = view["state"]["values"]["code_block"]["code_input"]["value"]
    date = view["state"]["values"]["datepicker_block"]["datepicker"]["selected_date"]
    time = view["state"]["values"]["timepicker_block"]["timepicker"]["selected_time"]
    description = view["state"]["values"]["description_block"]["description_input"]["value"]
    meta = json.loads(view.get("private_metadata", "{}"))
    original_code = meta.get("original_code", new_code)
    user_timezone_name = meta.get("user_timezone", "UTC")
    errors = {}

    try:
        with open(events_path, "r") as f:
            events = json.load(f)

        # Parse the date/time in user's timezone and convert to UTC timestamp
        user_timezone = pytz.timezone(user_timezone_name)
        naive_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        localized_datetime = user_timezone.localize(naive_datetime)
        timestamp = localized_datetime.astimezone(pytz.UTC).timestamp()

        # check if new code already exists
        if new_code in events and original_code != new_code:
            errors["code_block"] = "❌ Event with this code already exists."
            ack(response_action="errors", errors=errors)
            return
        # delete old event if code has changed
        if original_code != new_code and original_code in events:
            del events[original_code]
        # Save the event
        events[new_code] = {
            "description": description,
            "timestamp": timestamp,
            "created_by": body["user"]["id"]
        }

        with open(events_path, "w") as f:
            json.dump(events, f, indent=4)

        # ✅ Everything is fine — close modal
        ack()

    except FileNotFoundError:
        errors["description_block"] = "❌ Events file not found."
        ack(response_action="errors", errors=errors)

    except json.JSONDecodeError:
        errors["description_block"] = "❌ Error reading events file."
        ack(response_action="errors", errors=errors)

    except Exception as e:
        errors["description_block"] = f"❌ Unexpected error: `{str(e)}`"
        ack(response_action="errors", errors=errors)

@app.action("reset_time")
def handle_reset_time(ack, body, client):
    ack()
    
    # Get user timezone from the modal's private metadata
    view = body["view"]
    meta = json.loads(view.get("private_metadata", "{}"))
    user_timezone_name = meta.get("user_timezone", "UTC")
    user_timezone = pytz.timezone(user_timezone_name)
    
    # Get current time in user's timezone
    current_time_user_tz = datetime.now(user_timezone)
    current_date = current_time_user_tz.strftime("%Y-%m-%d")
    current_time = current_time_user_tz.strftime("%H:%M")
    
    # Update the modal with current date and time
    updated_view = view.copy()
    
    # Update date picker
    for block in updated_view["blocks"]:
        if block.get("block_id") == "datepicker_block":
            block["accessory"]["initial_date"] = current_date
        elif block.get("block_id") == "timepicker_block":
            for element in block["elements"]:
                if element.get("action_id") == "timepicker":
                    element["initial_time"] = current_time
    
    # Update the modal
    client.views_update(
        view_id=view["id"],
        view=updated_view
    )

# Start your app
if __name__ == "__main__":
    app.start(port=int(os.getenv("PORT", 3000)))