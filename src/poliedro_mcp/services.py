from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime
from typing import Any
from zoneinfo import ZoneInfo

from .client import PoliedroClient


def _common_calendar_params(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "ownerId": cfg["calendar"]["owner_id"],
        "schoolId": cfg["student"]["school_id"],
        "rolePmaisId": cfg["calendar"]["role_pmais_id"],
        "timeZone": cfg["calendar"]["time_zone"],
    }


def _js_month_date(dt: datetime) -> str:
    return dt.strftime("%a %b %d %Y 00:00:00 GMT-0300 (Brasilia Standard Time)")


def _js_year_date(dt: datetime) -> str:
    return dt.strftime("%a Jan 02 %Y")


def _js_week_date(dt: datetime) -> str:
    return format_datetime(dt.astimezone(ZoneInfo("UTC")), usegmt=True)


def _parse_date(date_str: str | None, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
    return datetime.now(tz)


class PoliedroService:
    def __init__(self) -> None:
        self.client = PoliedroClient()
        self.cfg = self.client.config

    def health_check(self) -> dict[str, Any]:
        return {
            "ok": True,
            "base_url": self.client.base_url,
            "school_id": self.cfg["student"]["school_id"],
            "school_year": self.cfg["student"]["school_year"],
        }

    def get_grades(self) -> Any:
        params = {
            "schoolId": self.cfg["student"]["school_id"],
            "schoolYear": self.cfg["student"]["school_year"],
            "originId": self.cfg["student"]["origin_id"],
            "emailP4ed": self.cfg["student"]["email_p4ed"],
            "enrollmentId": self.cfg["student"]["enrollment_id"],
        }

        return self.client.get("/pmais/api/v1/gradeStudentReport", params=params)

    def get_messages(self, status: str | None = None, limit: int | None = None, page: int | None = None) -> Any:
        ncfg = self.cfg["notifications"]

        params = {
            "notificationType": ncfg["notification_type"],
            "schoolId": self.cfg["student"]["school_id"],
            "roleId": self.cfg["student"]["role_id"],
            "page": page or ncfg["page"],
            "limit": limit or ncfg["limit"],
            "status": status or ncfg["status"],
        }

        return self.client.get("/pmais/api/v1/notifications", params=params)

    def get_next_events(self) -> Any:
        params = _common_calendar_params(self.cfg)
        return self.client.get("/pmais/api/v1/event/next-events", params=params)

    def get_week_events(self, date: str | None = None) -> Any:
        selected_date = _parse_date(date, self.cfg["calendar"]["time_zone"])
        params = _common_calendar_params(self.cfg)
        params.update({
            "selectedDate": _js_week_date(selected_date),
            "isWidget": str(self.cfg["calendar"]["is_widget"]).lower(),
        })
        return self.client.get("/pmais/api/v1/event/week-events", params=params)

    def get_month_events(self, date: str | None = None) -> Any:
        selected_date = _parse_date(date, self.cfg["calendar"]["time_zone"])
        params = _common_calendar_params(self.cfg)
        params.update({
            "selectedDate": _js_month_date(selected_date),
            "isWidget": str(self.cfg["calendar"]["is_widget"]).lower(),
        })
        return self.client.get("/pmais/api/v1/event/month-events", params=params)

    def get_year_events(self, date: str | None = None) -> Any:
        selected_date = _parse_date(date, self.cfg["calendar"]["time_zone"])
        params = _common_calendar_params(self.cfg)
        params.update({
            "selectedDate": _js_year_date(selected_date),
            "isWidget": str(self.cfg["calendar"]["is_widget"]).lower(),
        })
        return self.client.get("/pmais/api/v1/event/year-events", params=params)
