from __future__ import annotations

from datetime import datetime
from email.utils import format_datetime
from typing import Any
from zoneinfo import ZoneInfo

from .client import PoliedroClient
from .logger import logger


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
        try:
            overview = self.get_simulation_grades(school_year=school_year)
            grades_by_name = _student_simulation_grades(overview)
        except RuntimeError:
            logger.warning(
                "Não foi possível carregar notas do evolution-graph; "
                "retornando listagem de simulados sem nota geral."
            )

        sorted_items = sorted(
            all_items,
            key=lambda item: (item.get("dates") or [""])[0],
        )

        assessments = []
        for index, item in enumerate(sorted_items):
            title = item.get("title", "")
            status = item.get("status") or {}
            assessments.append({
                "index": index,
                "name": title,
                "assessment_id": item.get("id"),
                "grade": grades_by_name.get(title),
                "status": status.get("name"),
                "dates": item.get("dates"),
            })

        return {
            "school_year": school_year or self.cfg["student"]["school_year"],
            "assessments": assessments,
        }

    def _resolve_assessment_id(
        self,
        *,
        assessment_id: str | None = None,
        assessment_index: int | None = None,
        assessment_name: str | None = None,
        school_year: int | None = None,
    ) -> str:
        if assessment_id:
            return assessment_id

        listing = self.list_simulation_assessments(school_year=school_year)
        assessments = listing["assessments"]

        if assessment_index is not None:
            for item in assessments:
                if item["index"] == assessment_index:
                    if not item["assessment_id"]:
                        raise RuntimeError(
                            f"assessment_id não encontrado para o simulado "
                            f"índice {assessment_index} ({item['name']})."
                        )
                    return item["assessment_id"]
            raise RuntimeError(f"Índice de simulado inválido: {assessment_index}")

        if assessment_name:
            query = assessment_name.strip().lower()
            matches = [
                item for item in assessments
                if query in item["name"].lower() and item["assessment_id"]
            ]
            if len(matches) == 1:
                return matches[0]["assessment_id"]
            if len(matches) > 1:
                names = ", ".join(item["name"] for item in matches)
                raise RuntimeError(f"Nome ambíguo '{assessment_name}'. Simulados: {names}")

        raise RuntimeError(
            "Informe assessment_id, assessment_index ou assessment_name "
            "para consultar o detalhe do simulado."
        )

    def get_simulation_performance(
        self,
        *,
        assessment_id: str | None = None,
        assessment_index: int | None = None,
        assessment_name: str | None = None,
        school_year: int | None = None,
        compare_with: int | None = None,
    ) -> Any:
        """Consulta detalhe do simulado por matéria (performance)."""
        resolved_id = self._resolve_assessment_id(
            assessment_id=assessment_id,
            assessment_index=assessment_index,
            assessment_name=assessment_name,
            school_year=school_year,
        )
        params = _performance_params(
            self.cfg,
            resolved_id,
            compare_with=compare_with,
        )
        return self.client.get(
            "/pmais/results/bff/results/assessment/performance",
            params=params,
        )

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
