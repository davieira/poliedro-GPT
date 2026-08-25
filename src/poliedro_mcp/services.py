from __future__ import annotations

import re
from datetime import datetime
from email.utils import format_datetime
from typing import Any
from zoneinfo import ZoneInfo

from .client import PoliedroClient
from .logger import logger


DEFAULT_ANNOUNCEMENTS_BASE_URL = "https://announcement-events-bff.p4ed.com"

_DEEPLINK_ANNOUNCEMENT_RE = re.compile(
    r"announcement-details-screen/(\d+)",
    re.IGNORECASE,
)


def _announcements_base_url(cfg: dict[str, Any]) -> str:
    acfg = cfg.get("announcements") or {}
    return acfg.get("base_url", DEFAULT_ANNOUNCEMENTS_BASE_URL).rstrip("/")


def _parse_announcement_id_from_deeplink(deeplink: str | None) -> int | None:
    if not deeplink:
        return None
    match = _DEEPLINK_ANNOUNCEMENT_RE.search(deeplink)
    if not match:
        return None
    return int(match.group(1))


def _format_message_list_item(item: dict[str, Any]) -> dict[str, Any]:
    mapping = (item.get("notificationsUserMapping") or [{}])[0]
    announcement_id = _parse_announcement_id_from_deeplink(item.get("deeplink"))
    return {
        "notification_id": item.get("id"),
        "title": item.get("title"),
        "preview": item.get("body"),
        "published_at": item.get("publishedAt"),
        "status": mapping.get("status"),
        "announcement_id": announcement_id,
        "deeplink": item.get("deeplink"),
    }


def _format_announcement_detail(raw: dict[str, Any]) -> dict[str, Any]:
    categories = []
    for category in raw.get("categories") or []:
        option = category.get("option") or {}
        if option.get("name"):
            categories.append(option["name"])

    return {
        "announcement_id": raw.get("id"),
        "title": raw.get("title"),
        "content": raw.get("content"),
        "content_rich_text": raw.get("contentRichText"),
        "author_name": raw.get("authorName"),
        "available_at": raw.get("availableAt"),
        "created_at": raw.get("createdAt"),
        "school_id": raw.get("schoolId"),
        "dependent_id": raw.get("dependentId"),
        "categories": categories,
        "is_draft": raw.get("isDraft"),
    }


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


def _assessment_params(cfg: dict[str, Any], school_year: int | None = None) -> dict[str, Any]:
    acfg = cfg.get("assessment") or {}
    pmais_student_id = acfg.get("pmais_student_id") or cfg["calendar"]["owner_id"]

    return {
        "sourceSystem": acfg.get("source_system", "56d92fd9-c2e1-4293-a06a-6f2af49e7357"),
        "viewMode": acfg.get("view_mode", 3),
        "schoolYear": school_year or cfg["student"]["school_year"],
        "compareWith": acfg.get("compare_with", 1),
        "subAssessmentTypeId": acfg.get("sub_assessment_type_id", 2),
        "correctionMethod": acfg.get("correction_method", 0),
        "pmaisStudentId": pmais_student_id,
        "rankingSourceId": acfg.get("ranking_source_id", 2),
    }


def _all_assessments_params(cfg: dict[str, Any], school_year: int | None = None) -> dict[str, Any]:
    acfg = cfg.get("assessment") or {}
    student_id = acfg.get("pmais_student_id") or cfg["calendar"]["owner_id"]

    return {
        "year": school_year or cfg["student"]["school_year"],
        "viewMode": acfg.get("view_mode", 3),
        "studentId": student_id,
    }


def _performance_params(
    cfg: dict[str, Any],
    assessment_id: str,
    compare_with: int | None = None,
) -> dict[str, Any]:
    acfg = cfg.get("assessment") or {}
    student_id = acfg.get("pmais_student_id") or cfg["calendar"]["owner_id"]

    return {
        "compareWith": compare_with if compare_with is not None else acfg.get("performance_compare_with", 0),
        "assessmentId": assessment_id,
        "schoolId": cfg["student"]["school_id"],
        "sourceSystem": acfg.get("source_system", "56d92fd9-c2e1-4293-a06a-6f2af49e7357"),
        "viewMode": acfg.get("view_mode", 3),
        "rankingSourceId": acfg.get("ranking_source_id", 2),
        "correctionMethod": acfg.get("correction_method", 0),
        "studentId": student_id,
    }


def _student_simulation_grades(overview: dict[str, Any]) -> dict[str, str]:
    chart_points = overview.get("chartPoints") or []
    student_grades = _student_simulation_grades_list(overview)
    grades_by_name: dict[str, str] = {}

    for index, name in enumerate(chart_points):
        if index < len(student_grades):
            grades_by_name[name] = student_grades[index]

    return grades_by_name


def _student_simulation_grades_list(overview: dict[str, Any]) -> list[str]:
    for series in overview.get("chartData") or []:
        if series.get("label") == "Sua Nota":
            return [str(value) for value in series.get("values") or []]
    return []


def _school_averages_by_name(overview: dict[str, Any]) -> dict[str, str]:
    chart_points = overview.get("chartPoints") or []
    school_values: list[str] = []
    for series in overview.get("chartData") or []:
        if series.get("label") == "Média da sua escola":
            school_values = [str(value) for value in series.get("values") or []]
            break

    if not chart_points or not school_values:
        return {}

    if len(school_values) == len(chart_points):
        return dict(zip(chart_points, school_values))

    return {chart_points[-1]: school_values[-1]}


def _sorted_assessments_from_all(all_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(all_items, key=lambda item: (item.get("dates") or [""])[0])


def _format_simulation_performance(raw: dict[str, Any]) -> dict[str, Any]:
    subjects: list[dict[str, Any]] = []
    for step in raw.get("steps") or []:
        for subject in step.get("subjects") or []:
            row = (subject.get("fronts") or {}).get("rows") or []
            subjects.append({
                "name": subject.get("name"),
                "grade": subject.get("testGrade"),
                "grade_detail": row[0].get("grade") if row else None,
                "hits": row[0].get("hits") if row else None,
            })

    general = raw.get("general") or {}
    student = raw.get("student") or {}
    return {
        "assessment_id": raw.get("id"),
        "name": raw.get("name"),
        "overall_grade": general.get("testGrade"),
        "student_name": student.get("name"),
        "subjects": subjects,
    }


class PoliedroService:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        access_token: str | None = None,
    ) -> None:
        self.client = PoliedroClient(config, access_token=access_token)
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

    def get_simulation_grades(self, school_year: int | None = None) -> Any:
        """Consulta notas do simulado / prova trimestral (evolution graph)."""
        params = _assessment_params(self.cfg, school_year=school_year)
        return self.client.get(
            "/pmais/results/bff/results/assessment/evolution-graph",
            params=params,
        )

    def get_all_simulation_assessments(self, school_year: int | None = None) -> Any:
        """Lista simulados com UUIDs via endpoint /assessment/all."""
        params = _all_assessments_params(self.cfg, school_year=school_year)
        return self.client.get(
            "/pmais/results/bff/results/assessment/all",
            params=params,
        )

    def list_simulation_assessments(self, school_year: int | None = None) -> dict[str, Any]:
        """Lista simulados com UUID, status, datas e nota geral quando disponível."""
        all_items = self.get_all_simulation_assessments(school_year=school_year)

        grades_by_name: dict[str, str] = {}
        school_averages_by_name: dict[str, str] = {}
        try:
            overview = self.get_simulation_grades(school_year=school_year)
            grades_by_name = _student_simulation_grades(overview)
            school_averages_by_name = _school_averages_by_name(overview)
        except RuntimeError:
            logger.warning(
                "Não foi possível carregar notas do evolution-graph; "
                "retornando listagem de simulados sem nota geral."
            )

        sorted_items = _sorted_assessments_from_all(all_items)

        assessments = []
        for index, item in enumerate(sorted_items):
            title = item.get("title", "")
            status = item.get("status") or {}
            assessment_id = item.get("id")
            assessments.append({
                "index": index,
                "name": title,
                "assessment_id": assessment_id,
                "grade": grades_by_name.get(title),
                "school_average": school_averages_by_name.get(title),
                "status": status.get("name"),
                "dates": item.get("dates"),
            })

        return {
            "school_year": school_year or self.cfg["student"]["school_year"],
            "assessments": assessments,
            "usage": (
                "Para detalhe por matéria, chame "
                "GET /api/v1/assessments/simulation/{assessment_id}/performance "
                "usando o assessment_id de cada item abaixo."
            ),
        }

    def get_simulation_performance(
        self,
        assessment_id: str,
        *,
        compare_with: int | None = None,
    ) -> Any:
        """Consulta detalhe do simulado por matéria (performance)."""
        if not assessment_id or not assessment_id.strip():
            raise RuntimeError(
                "assessment_id é obrigatório. "
                "Obtenha-o em GET /api/v1/assessments/simulation/list."
            )

        params = _performance_params(
            self.cfg,
            assessment_id.strip(),
            compare_with=compare_with,
        )
        raw = self.client.get(
            "/pmais/results/bff/results/assessment/performance",
            params=params,
        )
        result = _format_simulation_performance(raw)

        for item in self.get_all_simulation_assessments():
            if item.get("id") != assessment_id.strip():
                continue
            status_name = (item.get("status") or {}).get("name")
            if status_name:
                result["status"] = status_name
                if "parcial" in status_name.lower():
                    result["note"] = (
                        "Resultado parcial: algumas matérias podem ainda estar em correção."
                    )
            break

        return result

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

        raw = self.client.get("/pmais/api/v1/notifications", params=params)
        messages = [_format_message_list_item(item) for item in raw.get("data") or []]

        return {
            "messages": messages,
            "meta": raw.get("meta"),
            "usage": (
                "Para o texto completo do comunicado, chame "
                "GET /api/v1/messages/{announcement_id} usando announcement_id de cada item."
            ),
        }

    def get_message_detail(self, announcement_id: int | str) -> dict[str, Any]:
        """Consulta conteúdo completo de um comunicado/mensagem."""
        if announcement_id is None or str(announcement_id).strip() == "":
            raise RuntimeError(
                "announcement_id é obrigatório. "
                "Obtenha-o em GET /api/v1/messages (campo announcement_id)."
            )

        params = {
            "schoolId": self.cfg["student"]["school_id"],
            "roleId": self.cfg["student"]["role_id"],
            "dependentId": self.cfg["calendar"]["owner_id"],
        }
        raw = self.client.get_external(
            _announcements_base_url(self.cfg),
            f"/v1/announcement/{int(announcement_id)}",
            params=params,
            timeout=30,
        )
        return _format_announcement_detail(raw)

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
