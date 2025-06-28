from flask import Request
from src.journeylogger.sheet_writer import process_and_log_journey

def entry_point(request: Request):
    data = request.get_json(silent=True) or {}
    short_url = data.get("short_url")
    if not short_url:
        return {"error": "short_url missing"}, 400
    try:
        result = process_and_log_journey(short_url)
        return result
    except Exception as e:
        return {"error": str(e)}, 500
