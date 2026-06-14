from __future__ import annotations

import argparse
import json
from typing import Any

from .services import PoliedroService


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI para testar o Poliedro MCP")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("grades")

    simulation = sub.add_parser("simulation")
    simulation_sub = simulation.add_subparsers(dest="simulation_mode", required=True)
    simulation_sub.add_parser("summary")
    simulation_sub.add_parser("list")
    sim_detail = simulation_sub.add_parser("detail")
    sim_detail.add_argument("--assessment-id", required=True)
    sim_detail.add_argument("--school-year", type=int)

    msg = sub.add_parser("messages")
    msg.add_argument("--status", default="UNREAD")
    msg.add_argument("--limit", type=int, default=50)
    msg.add_argument("--page", type=int, default=1)

    cal = sub.add_parser("calendar")
    cal.add_argument("mode", choices=["next", "week", "month", "year"])
    cal.add_argument("--date", default=None)

    args = parser.parse_args()
    service = PoliedroService()

    if args.command == "health":
        print_json(service.health_check())
    elif args.command == "grades":
        print_json(service.get_grades())
    elif args.command == "simulation":
        if args.simulation_mode == "summary":
            print_json(service.get_simulation_grades())
        elif args.simulation_mode == "list":
            print_json(service.list_simulation_assessments())
        elif args.simulation_mode == "detail":
            print_json(service.get_simulation_performance(args.assessment_id))
    elif args.command == "messages":
        print_json(service.get_messages(status=args.status, limit=args.limit, page=args.page))
    elif args.command == "calendar":
        if args.mode == "next":
            print_json(service.get_next_events())
        elif args.mode == "week":
            print_json(service.get_week_events(args.date))
        elif args.mode == "month":
            print_json(service.get_month_events(args.date))
        elif args.mode == "year":
            print_json(service.get_year_events(args.date))


if __name__ == "__main__":
    main()
