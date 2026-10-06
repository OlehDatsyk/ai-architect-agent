"""Interpret a brief with the real Architect Agent and print the result.

Run from backend/ with ANTHROPIC_API_KEY set in the root .env:
    python -m scripts.interpret_brief "A modern three-bedroom bungalow with a flat roof"
    python -m scripts.interpret_brief --example luxury-house --bedrooms 5
    python -m scripts.interpret_brief --example modern-bungalow --plan output/plans
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.api.routes.designs import build_architect_agent
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.models.intent import DesignConstraints, DesignRequest
from app.planner import plan_building
from app.planner.preview import render_all
from app.services.example_repository import ExampleRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("brief", nargs="?", help="The building brief.")
    parser.add_argument("--example", help="Use the prompt of an example instead, e.g. modern-bungalow.")
    parser.add_argument("--bedrooms", type=int)
    parser.add_argument("--floors", type=int)
    parser.add_argument("--roof", choices=["automatic", "flat", "gable", "hip", "shed"], default="automatic")
    parser.add_argument("--detail", choices=["concept", "standard", "detailed"], default="standard")
    parser.add_argument("--json", action="store_true", help="Print the full result as JSON.")
    parser.add_argument("--plan", metavar="DIR", help="Also plan the design and write floor-plan SVGs and the specification to DIR.")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    brief = ExampleRepository(settings.examples_dir).get(args.example).prompt if args.example else args.brief
    if not brief:
        parser.error("give a brief or --example")

    request = DesignRequest(prompt=brief, constraints=DesignConstraints(
        bedrooms=args.bedrooms, floors=args.floors, roof=args.roof, detail_level=args.detail))
    try:
        result = asyncio.run(build_architect_agent(settings).interpret(request))
    except AppError as exc:
        print(f"\n{exc.code}: {exc.message}", file=sys.stderr)
        for issue in exc.details.get("issues", []):
            print(f"  - {issue['message']}", file=sys.stderr)
        return 1

    if args.json:
        print(result.model_dump_json(indent=2))
        return 0
    intent = result.intent
    print(f"\n{intent.project_name}  ({result.report.status.value}, {result.attempts} attempt(s), "
          f"{result.usage.input_tokens} in / {result.usage.output_tokens} out tokens)")
    print(intent.summary)
    print(f"Footprint {intent.footprint_width} x {intent.footprint_depth} m, {intent.floors} floor(s), "
          f"{intent.roof.type.value} roof at {intent.roof.pitch} degrees")
    for level in range(intent.floors):
        print(f"\nFloor {level}:")
        for room in intent.rooms_on_floor(level):
            print(f"  {room.name:<32} {room.target_area:6.1f} m2  {room.type.value}")
    for heading, items in (("Assumptions", intent.assumptions), ("Warnings", [i.message for i in result.report.issues]),
                           ("Options applied", result.constraints_applied)):
        if items:
            print(f"\n{heading}:")
            print("\n".join(f"  - {item}" for item in items))
    if args.plan:
        write_plan(result.intent, Path(args.plan))
    return 0


def write_plan(intent, out_dir: Path) -> None:
    try:
        planned = plan_building(intent)
    except AppError as exc:
        print(f"\nPlanning failed: {exc.message}", file=sys.stderr)
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "specification.json").write_text(planned.specification.model_dump_json(indent=2), encoding="utf-8")
    for level, _name, svg in render_all(planned.specification):
        (out_dir / f"floor_{level}.svg").write_text(svg, encoding="utf-8")
    print(f"\nPlan: {planned.report.status.value}, written to {out_dir}/")
    for note in planned.notes:
        print(f"  - {note}")


if __name__ == "__main__":
    raise SystemExit(main())
