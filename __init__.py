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
def get_user_timezone(user_id):
    """Fetches the user's timezone from Slack API."""
    response = requests.get(
        f"https://slack.com/api/users.info?user={user_id}",
        headers={"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"}
    )
    if response.status_code == 200:
        user_info = response.json()
        return user_info.get("user", {}).get("tz", "America/New_York")  # Default to New York if not set
    return "America/New_York"
# get time 
@app.command("/get_time")
def handle_get_time(ack, respond, command):
    ack()
    timezone_args = command.get("text", "").strip().split()

    try:
        if len(timezone_args) > 0:
            if timezone_args[0].startswith("<@"):
                # Extract the timezone name from the mention
                org_timezone_name = get_user_timezone(timezone_args[0][2:-1])
            else:
                org_timezone_name = timezone_args[0]
        else:
            org_timezone_name = "America/New_York"
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
            if timezone_args[3].startswith("<@"):
                # Extract the timezone name from the mention
                user_tz_name = get_user_timezone(timezone_args[3][2:-1])
            else:
                user_tz_name = timezone_args[3]
        else:
            user_tz_name = get_user_timezone(command["user_id"])

        res_timezone = pytz.timezone(user_tz_name)
        # Convert to result timezone
        converted = dt.astimezone(res_timezone)

        respond(blocks=[
            
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🕒 Time in `{user_tz_name}`: `{converted.strftime('%Y-%m-%d %H:%M:%S')}`"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Remind me",
                            "emoji": True
                        },
                        "value": json.dumps({"timestamp": converted.timestamp(), 
                                             "timezone": user_tz_name}),
                        "action_id": "reminder"
                    }
                ]
            }
        ])
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
        if command_args[1].startswith("<@"):
            # Extract the timezone name from the mention
            timezone_name = get_user_timezone(command_args[1][2:-1])
        else:
            timezone_name = command_args[1]
    else:
        timezone_name = get_user_timezone(command["user_id"])
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
        respond(blocks=[
            
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📅 Event: \n```{event['description']}```\n"
                            f"🕒 Time: `{timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}`\n"
                            f"👤 Created by: <@{event['created_by']}>"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Remind me",
                            "emoji": True
                        },
                        "value": json.dumps({
                            "timestamp": event["timestamp"],
                            "description": event["description"],
                            "timezone": timezone_name}),
                        "action_id": "reminder"
                    }
                ]
            }
        ])
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
        user_timezone_name = get_user_timezone(command["user_id"])
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
        event_datetime_utc = datetime.fromtimestamp(event["timestamp"])
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
    user_timezone_name = meta.get("user_timezone", "America/New_York")
    errors = {}

    try:
        with open(events_path, "r") as f:
            events = json.load(f)

        # Parse the date/time in user's timezone and convert to UTC timestamp
        user_timezone = pytz.timezone(user_timezone_name)
        naive_datetime = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        localized_datetime = user_timezone.localize(naive_datetime)
        timestamp = localized_datetime.timestamp()

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
    user_timezone_name = meta.get("user_timezone", "America/New_York")
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
@app.action("reminder")
def handle_reminder(ack, client, action, respond, body):
    ack()
    try:
        # Parse the action value
        if isinstance(action["value"], str):
            event_data = json.loads(action["value"])
        else:
            event_data = action["value"]

        timestamp = event_data.get("timestamp")
        if not timestamp:
            respond("❌ Invalid reminder data.")
            return

        # Convert timestamp to datetime
        reminder_time = datetime.fromtimestamp(timestamp, pytz.timezone(event_data.get("timezone", "America/New_York")))
        client.chat_scheduleMessage(
            channel=body["user"]["id"],
            text=f"🔔 Reminder: {event_data.get('description', f'You set a reminder in <#{body["channel"]["id"]}>')}",
            post_at=int(reminder_time.timestamp())
        )
        # Respond with a confirmation message
        respond(f"🔔 Reminder set for {reminder_time.strftime('%Y-%m-%d %H:%M:%S')} America/New_York.")
    except Exception as e:
        respond(f"❌ Error setting reminder: `{str(e)}`")

@app.command("/list_events")
def handle_list_events(ack, respond, command):
    ack()
    interval = command.get("text", "").strip()
    user_timezone = pytz.timezone(get_user_timezone(command["user_id"]))
    now = datetime.now(user_timezone)
    def matches_interval(date):
        match interval:
            case "year":
                return date.year == now.year
            case "month":
                return date.year == now.year and date.month == now.month
            case "day":
                return date.year == now.year and date.month == now.month and date.day == now.day
            case "hour":
                return date.year == now.year and date.month == now.month and date.day == now.day and date.hour == now.hour
            case _:
                return True  # Default to all events if no interval is specified
        
    try:
        with open(events_path, "r") as f:
            events = json.load(f)

        if not events:
            respond("❌ No events found.")
            return

        blocks = []
        for event_id, event in events.items():
            timestamp = datetime.fromtimestamp(event["timestamp"], user_timezone)
            if matches_interval(timestamp):
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Event ID:* `{event_id}`\n"
                                f"*Description:* {event['description']}\n"
                                f"*Time:* {timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                                f"*Created by:* <@{event['created_by']}>"
                    }
                })
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Remind me",
                                "emoji": True
                            },
                            "value": json.dumps({
                                "timestamp": event["timestamp"],
                                "description": event["description"],
                                "timezone": command.get("user_tz", "America/New_York")}),
                            "action_id": "reminder"
                        }
                    ]
                })

        respond(blocks=blocks)
    except FileNotFoundError:
        respond("❌ Events file not found.")
    except json.JSONDecodeError:
        respond("❌ Error reading events file.")
    except Exception as e:
        respond(f"❌ Error listing events: `{str(e)}`")

# Start your app
if __name__ == "__main__":
    app.start(port=int(os.getenv("PORT", 3000)))