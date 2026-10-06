"""Landscaping must sit around the building, not inside it."""

from collections.abc import Iterator

from app.geometry.rect import Rect
from app.scene.landscape import CLEARANCE, MIN_RADIUS, distance_to_rect, plant_radius
from app.validation.context import ValidationContext, fmt
from app.validation.report import ValidationIssue, warning


def check_site(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    env = ctx.spec.environment
    areas = [a for a in (env.driveway, env.patio, *env.paths) if a is not None]
    for area in areas:
        overlap = Rect(area.x, area.y, area.width, area.depth).intersection_area(ctx.footprint)
        if overlap > 0.01:
            yield warning("site_area_inside_building", f"Site area {area.id} overlaps the building by {fmt(overlap)} m².", area.id)
    for plant in env.vegetation:
        if ctx.footprint.contains_point(plant.x, plant.y, tol=-0.01):
            yield warning("vegetation_inside_building", f"Planting {plant.id} is placed inside the building.", plant.id)


def check_planting_clearance(ctx: ValidationContext) -> Iterator[ValidationIssue]:
    """Plants whose canopy would touch the building are drawn smaller, or left out if tiny."""
    b, roof = ctx.spec.building, ctx.spec.roof
    reach = b.wall_thickness / 2 + roof.overhang
    building = Rect(-reach, -reach, b.width + 2 * reach, b.depth + 2 * reach)
    for plant in ctx.spec.environment.vegetation:
        if ctx.footprint.contains_point(plant.x, plant.y, tol=-0.01):
            continue  # already reported as inside the building
        room = distance_to_rect(plant.x, plant.y, building) - CLEARANCE
        radius = plant_radius(plant)
        if room < MIN_RADIUS:
            yield warning("planting_too_close", f"Planting {plant.id} is too close to the building and will be left out of the 3D model.", plant.id)
        elif room < radius:
            yield warning("planting_too_close", f"Planting {plant.id} would touch the building, so it will be drawn {room / radius:.0%} of its size.", plant.id)
