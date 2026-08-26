#!/usr/bin/env python3
"""Generate the adjustable four-camera tripod rig parts."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import cadquery as cq


# Hub and tripod interface (millimeters).
BASE_THICKNESS = 7.5
CORE_DIAMETER = 72.0
ARM_RADIUS = 80.0
ARM_WIDTH = 32.0
PIVOT_RADIUS = 70.0
PIVOT_Z = 25.0
EAR_LENGTH = 20.0
EAR_THICKNESS = 4.2
EAR_GAP = 8.2
EAR_HEIGHT = 30.0
PIVOT_HOLE_DIAMETER = 4.4

# A standard 1/4-20 hex nut is nominally 7/16 inch across flats.
TRIPOD_CLEARANCE_DIAMETER = 6.8
TRIPOD_NUT_ACROSS_FLATS = 11.5
TRIPOD_NUT_DEPTH = 6.0

# Camera interfaces from the manufacturer drawings.
TECH_M3_CLEARANCE = 3.4
TECH_M3_SPACING = 15.0
TECH_M3_FROM_FRONT = 3.8
TECH_BODY_DEPTH = 28.0
TECH_BODY_WIDTH = 29.5
TECH_BODY_HEIGHT = 29.5
TECH_CAMERA_CENTER_X = 31.0
ANALOG_PANEL_HOLE = 18.8  # 18.5 nominal plus FDM fit allowance.
ANALOG_PANEL_X = 34.0

TONGUE_THICKNESS = 7.6
DEFAULT_TILT_DEGREES = 45.0


def hex_circumdiameter(across_flats: float) -> float:
    return across_flats / math.cos(math.radians(30.0))


def make_hub() -> cq.Workplane:
    hub = cq.Workplane("XY").circle(CORE_DIAMETER / 2.0).extrude(BASE_THICKNESS)
    hub = hub.union(
        cq.Workplane("XY")
        .box(ARM_RADIUS * 2.0, ARM_WIDTH, BASE_THICKNESS, centered=(True, True, False))
    )
    hub = hub.union(
        cq.Workplane("XY")
        .box(ARM_WIDTH, ARM_RADIUS * 2.0, BASE_THICKNESS, centered=(True, True, False))
    )

    ear_offset = (EAR_GAP + EAR_THICKNESS) / 2.0
    for angle in (0.0, 90.0, 180.0, 270.0):
        clevis = cq.Workplane("XY")
        for y in (-ear_offset, ear_offset):
            ear = (
                cq.Workplane("XY")
                .box(
                    EAR_LENGTH,
                    EAR_THICKNESS,
                    EAR_HEIGHT,
                    centered=(True, True, False),
                )
                .translate((PIVOT_RADIUS, y, BASE_THICKNESS))
            )
            clevis = clevis.union(ear)

        pivot_cut = (
            cq.Workplane("XZ")
            .center(PIVOT_RADIUS, PIVOT_Z)
            .circle(PIVOT_HOLE_DIAMETER / 2.0)
            .extrude(ARM_WIDTH, both=True)
        )
        clevis = clevis.cut(pivot_cut)
        hub = hub.union(clevis.rotate((0, 0, 0), (0, 0, 1), angle))

        cable_slot = (
            cq.Workplane("XY")
            .box(6.0, 14.0, BASE_THICKNESS + 2.0, centered=(True, True, False))
            .translate((44.0, 0.0, -1.0))
            .rotate((0, 0, 0), (0, 0, 1), angle)
        )
        hub = hub.cut(cable_slot)

    through_hole = (
        cq.Workplane("XY")
        .circle(TRIPOD_CLEARANCE_DIAMETER / 2.0)
        .extrude(BASE_THICKNESS + 2.0)
        .translate((0.0, 0.0, -1.0))
    )
    nut_pocket = (
        cq.Workplane("XY")
        .polygon(6, hex_circumdiameter(TRIPOD_NUT_ACROSS_FLATS))
        .extrude(TRIPOD_NUT_DEPTH + 0.1)
        .translate((0.0, 0.0, BASE_THICKNESS - TRIPOD_NUT_DEPTH))
    )
    return hub.cut(through_hole).cut(nut_pocket)


def make_pivot_tongue() -> cq.Workplane:
    tongue = cq.Workplane("XY").box(
        20.0, TONGUE_THICKNESS, 20.0, centered=(True, True, True)
    )
    pivot_cut = (
        cq.Workplane("XZ")
        .circle(PIVOT_HOLE_DIAMETER / 2.0)
        .extrude(12.0, both=True)
    )
    return tongue.cut(pivot_cut)


def make_technexion_carrier() -> cq.Workplane:
    # Keep the wide shelf outside the hub ears through the useful tilt range.
    # A narrow bridge passes through the clevis gap and joins it to the tongue.
    shelf_z = 8.0
    shelf = (
        cq.Workplane("XY")
        .box(38.0, 36.0, 4.0, centered=(True, True, False))
        .translate((TECH_CAMERA_CENTER_X, 0.0, shelf_z))
    )
    bridge = (
        cq.Workplane("XY")
        .box(8.0, TONGUE_THICKNESS, 4.0, centered=(True, True, True))
        .translate((11.0, 0.0, 9.0))
    )
    carrier = make_pivot_tongue().union(bridge).union(shelf)

    hole_x = TECH_CAMERA_CENTER_X + (TECH_BODY_DEPTH / 2.0) - TECH_M3_FROM_FRONT
    mounting_holes = (
        cq.Workplane("XY")
        .pushPoints(
            [
                (hole_x, -TECH_M3_SPACING / 2.0),
                (hole_x, TECH_M3_SPACING / 2.0),
            ]
        )
        .circle(TECH_M3_CLEARANCE / 2.0)
        .extrude(10.0)
        .translate((0.0, 0.0, 5.0))
    )
    return carrier.cut(mounting_holes)


def make_analog_carrier(panel_hole: float = ANALOG_PANEL_HOLE) -> cq.Workplane:
    panel_center_z = 20.0
    panel = (
        cq.Workplane("XY")
        .box(3.2, 40.0, 40.0, centered=(True, True, True))
        .translate((ANALOG_PANEL_X, 0.0, panel_center_z))
    )
    camera_hole = (
        cq.Workplane("YZ", origin=(ANALOG_PANEL_X, 0.0, 0.0))
        .center(0.0, panel_center_z)
        .circle(panel_hole / 2.0)
        .extrude(10.0, both=True)
    )
    center_beam = (
        cq.Workplane("XY")
        .box(38.0, TONGUE_THICKNESS, 8.0, centered=(True, True, True))
        .translate((15.0, 0.0, 4.0))
    )
    carrier = make_pivot_tongue().union(center_beam).union(panel.cut(camera_hole))

    # These braces begin outside the clevis ears and clear the spring clip.
    for y in (-14.0, 14.0):
        rail = (
            cq.Workplane("XY")
            .box(16.0, 3.5, 24.0, centered=(True, True, True))
            .translate((26.0, y, 12.0))
        )
        carrier = carrier.union(rail)
    lower_crossbar = (
        cq.Workplane("XY")
        .box(6.0, 31.5, 4.0, centered=(True, True, True))
        .translate((31.0, 0.0, 4.0))
    )
    carrier = carrier.union(lower_crossbar)
    return carrier


def make_analog_fit_coupon() -> cq.Workplane:
    coupon = cq.Workplane("XY").box(84.0, 32.0, 3.2, centered=(True, True, False))
    diameters = (18.5, 18.8, 19.1)
    centers = (-27.0, 0.0, 27.0)
    for center, diameter in zip(centers, diameters):
        hole = (
            cq.Workplane("XY")
            .center(center, 0.0)
            .circle(diameter / 2.0)
            .extrude(5.2)
            .translate((0.0, 0.0, -1.0))
        )
        coupon = coupon.cut(hole)
    return coupon


def make_tripod_nut_coupon() -> cq.Workplane:
    coupon = cq.Workplane("XY").box(30.0, 26.0, BASE_THICKNESS, centered=(True, True, False))
    through_hole = (
        cq.Workplane("XY")
        .circle(TRIPOD_CLEARANCE_DIAMETER / 2.0)
        .extrude(BASE_THICKNESS + 2.0)
        .translate((0.0, 0.0, -1.0))
    )
    nut_pocket = (
        cq.Workplane("XY")
        .polygon(6, hex_circumdiameter(TRIPOD_NUT_ACROSS_FLATS))
        .extrude(TRIPOD_NUT_DEPTH + 0.1)
        .translate((0.0, 0.0, BASE_THICKNESS - TRIPOD_NUT_DEPTH))
    )
    return coupon.cut(through_hole).cut(nut_pocket)


def placed_carrier(
    carrier: cq.Workplane, azimuth_degrees: float, tilt_degrees: float
) -> cq.Workplane:
    angle = math.radians(azimuth_degrees)
    return (
        carrier.rotate((0, 0, 0), (0, 1, 0), tilt_degrees)
        .rotate((0, 0, 0), (0, 0, 1), azimuth_degrees)
        .translate(
            (
                PIVOT_RADIUS * math.cos(angle),
                PIVOT_RADIUS * math.sin(angle),
                PIVOT_Z,
            )
        )
    )


def validate_hub_clearance(
    hub: cq.Workplane,
    components: tuple[tuple[str, cq.Workplane], ...],
) -> None:
    # Rotational symmetry means checking one clevis covers all four stations.
    for tilt_degrees in (0.0, 30.0, 45.0, 60.0):
        for name, component in components:
            intersection = hub.intersect(
                placed_carrier(component, 0.0, tilt_degrees)
            )
            volume = sum(solid.Volume() for solid in intersection.solids().vals())
            if volume > 0.001:
                raise RuntimeError(
                    f"{name} intersects hub by {volume:.3f} mm^3 "
                    f"at {tilt_degrees:.0f} degrees"
                )


def make_technexion_mockup() -> cq.Workplane:
    shelf_top = 12.0
    body = (
        cq.Workplane("XY")
        .box(
            TECH_BODY_DEPTH,
            TECH_BODY_WIDTH,
            TECH_BODY_HEIGHT,
            centered=(True, True, True),
        )
        .translate(
            (TECH_CAMERA_CENTER_X, 0.0, shelf_top + TECH_BODY_HEIGHT / 2.0)
        )
    )
    lens = (
        cq.Workplane(
            "YZ",
            origin=(TECH_CAMERA_CENTER_X + TECH_BODY_DEPTH / 2.0, 0.0, 0.0),
        )
        .center(0.0, shelf_top + TECH_BODY_HEIGHT / 2.0)
        .circle(7.0)
        .extrude(8.0)
    )
    return body.union(lens)


def make_analog_mockup() -> cq.Workplane:
    panel_front_x = ANALOG_PANEL_X + 1.6
    center_z = 20.0
    barrel = (
        cq.Workplane("YZ", origin=(panel_front_x, 0.0, 0.0))
        .center(0.0, center_z)
        .circle(18.5 / 2.0)
        .extrude(-23.0)
    )
    flange = (
        cq.Workplane("YZ", origin=(panel_front_x, 0.0, 0.0))
        .center(0.0, center_z)
        .circle(23.0 / 2.0)
        .extrude(3.0)
    )
    return barrel.union(flange)


def part_stats(name: str, part: cq.Workplane) -> str:
    shape = part.val()
    box = shape.BoundingBox()
    solid_count = part.solids().size()
    if not shape.isValid():
        raise RuntimeError(f"{name} is not a valid solid")
    if solid_count != 1:
        raise RuntimeError(f"{name} contains {solid_count} disconnected solids")
    return (
        f"{name}: {box.xlen:.2f} x {box.ylen:.2f} x {box.zlen:.2f} mm, "
        f"volume={shape.Volume():.1f} mm^3"
    )


def place_on_build_plate(part: cq.Workplane) -> cq.Workplane:
    box = part.val().BoundingBox()
    return part.translate((0.0, 0.0, -box.zmin))


def orient_technexion_for_printing(part: cq.Workplane) -> cq.Workplane:
    # Put the camera shelf face on the bed and grow the pivot tongue upward.
    return place_on_build_plate(part.rotate((0, 0, 0), (1, 0, 0), 180.0))


def orient_analog_for_printing(part: cq.Workplane) -> cq.Workplane:
    # Put the broad front panel on the bed and grow its braces upward.
    return place_on_build_plate(part.rotate((0, 0, 0), (0, 1, 0), 90.0))


def export_part(
    output_dir: Path,
    name: str,
    part: cq.Workplane,
    stl_part: cq.Workplane | None = None,
) -> str:
    if stl_part is None:
        stl_part = place_on_build_plate(part)
    cq.exporters.export(
        stl_part,
        str(output_dir / f"{name}.stl"),
        tolerance=0.05,
        angularTolerance=0.1,
    )
    cq.exporters.export(part, str(output_dir / f"{name}.step"))
    return part_stats(name, part)


def generate(output_dir: Path, tilt_degrees: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    hub = make_hub()
    technexion = make_technexion_carrier()
    analog = make_analog_carrier()
    analog_coupon = make_analog_fit_coupon()
    nut_coupon = make_tripod_nut_coupon()
    validate_hub_clearance(
        hub,
        (
            ("technexion_carrier", technexion),
            ("analog_flush_carrier", analog),
            ("technexion_camera_reference", make_technexion_mockup()),
            ("analog_camera_reference", make_analog_mockup()),
        ),
    )

    stats = [
        export_part(output_dir, "tripod_hub", hub),
        export_part(
            output_dir,
            "technexion_carrier",
            technexion,
            orient_technexion_for_printing(technexion),
        ),
        export_part(
            output_dir,
            "analog_flush_carrier",
            analog,
            orient_analog_for_printing(analog),
        ),
        export_part(output_dir, "analog_fit_coupon", analog_coupon),
        export_part(output_dir, "tripod_nut_fit_coupon", nut_coupon),
    ]

    assembly = cq.Assembly(name="four_camera_tripod_rig")
    assembly.add(hub, name="tripod_hub", color=cq.Color(0.18, 0.22, 0.26))
    printed_shapes = [hub.val()]
    camera_shapes = []

    placements = (
        ("front_technexion", technexion, make_technexion_mockup(), 0.0),
        ("right_analog", analog, make_analog_mockup(), 90.0),
        ("back_technexion", technexion, make_technexion_mockup(), 180.0),
        ("left_analog", analog, make_analog_mockup(), 270.0),
    )
    for name, carrier, camera, azimuth in placements:
        placed_printed_part = placed_carrier(carrier, azimuth, tilt_degrees)
        placed_camera = placed_carrier(camera, azimuth, tilt_degrees)
        assembly.add(
            placed_printed_part,
            name=f"{name}_carrier",
            color=cq.Color(0.18, 0.45, 0.72),
        )
        assembly.add(
            placed_camera,
            name=f"{name}_camera_reference",
            color=cq.Color(0.12, 0.12, 0.12, 0.55),
        )
        printed_shapes.append(placed_printed_part.val())
        camera_shapes.append(placed_camera.val())

    assembly.export(str(output_dir / "camera_rig_assembly.step"))
    cq.exporters.export(
        cq.Compound.makeCompound(printed_shapes),
        str(output_dir / "camera_rig_printed_assembly_preview.stl"),
        tolerance=0.08,
        angularTolerance=0.15,
    )
    cq.exporters.export(
        cq.Compound.makeCompound(camera_shapes),
        str(output_dir / "camera_rig_camera_references_preview.stl"),
        tolerance=0.08,
        angularTolerance=0.15,
    )
    (output_dir / "dimensions.txt").write_text("\n".join(stats) + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    parser.add_argument("--tilt", type=float, default=DEFAULT_TILT_DEGREES)
    args = parser.parse_args()
    generate(args.output_dir, args.tilt)


if __name__ == "__main__":
    main()
