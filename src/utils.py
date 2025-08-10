from datetime import datetime

import pytz


def ist_timestamp():
    dt = datetime.now(pytz.timezone("Asia/Kolkata"))
    milliseconds = dt.microsecond // 1000  # Convert microseconds to milliseconds
    dt = dt.replace(
        microsecond=milliseconds * 1000
    )  # Set precision to 3 decimal places
    return dt.isoformat()


def string_to_timestamp(s):
    if s is None or s == "":
        return None

    s = s.strip()

    if " " in s:
        s = s.replace(" ", "T", 1)  # Replace first space with 'T'
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"  # Replace 'Z' with '+00:00'
    dt = datetime.fromisoformat(s)  # Parse ISO string
    return dt.astimezone(pytz.timezone("Asia/Kolkata")).isoformat()


def python_string_to_timestamp(s):
    if s is None or s == "":
        return None

    dt = datetime.fromisoformat(s)
    return dt.astimezone(pytz.timezone("Asia/Kolkata")).isoformat()
