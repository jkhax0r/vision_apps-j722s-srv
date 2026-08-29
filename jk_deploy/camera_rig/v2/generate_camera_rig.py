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
PIVOT_INDEX_ANGLES = (0.0, 15.0, 30.0, 45.0, 60.0)
DETENT_RADIUS = 7.0
DETENT_SPHERE_RADIUS = 1.6
DETENT_BUMP_HEIGHT = 0.6
DETENT_POCKET_DEPTH = 0.7

# A standard 1/4-20 hex nut is nominally 7/16 inch across flats.
TRIPOD_CLEARANCE_DIAMETER = 6.8
TRIPOD_NUT_ACROSS_FLATS = 11.5
TRIPOD_NUT_DEPTH = 6.0
TRIPOD_NUT_REFERENCE_ACROSS_FLATS = 11.1
TRIPOD_NUT_REFERENCE_HEIGHT = 5.6
TRIPOD_THREAD_PITCH = 25.4 / 20.0
TRIPOD_PRINTED_THREAD_MINOR_DIAMETER = 5.3
TRIPOD_PRINTED_THREAD_MAJOR_DIAMETER = 6.76
TRIPOD_PRINTED_THREAD_HALF_WIDTH = 0.40
TRIPOD_PRINTED_THREAD_ENTRY_CHAMFER = 0.60
TRIPOD_PRINTED_THREAD_CUTTER_OVERLAP = 0.20
TRIPOD_STABILIZER_OFFSET = 14.0
TRIPOD_STABILIZER_HOLE_DIAMETER = 5.2
TRIPOD_STABILIZER_HOLE_DEPTH = 5.2
TRIPOD_STABILIZER_PIN_DIAMETER = 4.55
TRIPOD_STABILIZER_PIN_HEIGHT = 3.75

# Camera interfaces from the manufacturer drawings.
TECH_M3_CLEARANCE = 3.4
TECH_M3_SPACING = 15.0
TECH_M3_FROM_FRONT = 3.8
TECH_BODY_DEPTH = 28.0
TECH_BODY_WIDTH = 29.5
TECH_BODY_HEIGHT = 29.5
TECH_CAMERA_CENTER_X = 31.0
TECH_SHELF_CENTER_X = 30.0
TECH_SHELF_LENGTH = 36.0
TECH_SUPPORT_SPINE_START_X = 5.0
TECH_SUPPORT_SPINE_END_X = 38.0
TECH_SUPPORT_SPINE_BOTTOM_Z = 2.0
TECH_CRADLE_CLEARANCE = 0.5
TECH_WALL_THICKNESS = 2.5
TECH_FRONT_APERTURE = 25.0
ANALOG_PANEL_HOLE = 18.8  # 18.5 nominal plus FDM fit allowance.
ANALOG_PANEL_X = 34.0

TONGUE_THICKNESS = 7.6
DEFAULT_TILT_DEGREES = 45.0

# Dimensionally representative M4 x 30 pivot hardware; threads are omitted.
M4_BOLT_DIAMETER = 4.0
M4_BOLT_LENGTH = 30.0
M4_HEAD_ACROSS_FLATS = 7.0
M4_HEAD_HEIGHT = 3.0
M4_NUT_ACROSS_FLATS = 7.0
M4_NUT_HEIGHT = 3.2
M4_WASHER_OUTER_DIAMETER = 9.0
M4_WASHER_INNER_DIAMETER = 4.4
M4_WASHER_THICKNESS = 0.8


def hex_circumdiameter(across_flats: float) -> float:
    return across_flats / math.cos(math.radians(30.0))


def make_hub() -> cq.Workplane:
    hub = cq.Workplane("XY").circle(CORE_DIAMETER / 2.0).extrude(BASE_THICKNESS)
    hub = hub.union(
        cq.Workplane("XY").box(
            ARM_RADIUS * 2.0, ARM_WIDTH, BASE_THICKNESS, centered=(True, True, False)
        )
    )
    hub = hub.union(
        cq.Workplane("XY").box(
            ARM_WIDTH, ARM_RADIUS * 2.0, BASE_THICKNESS, centered=(True, True, False)
        )
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

        # Five shallow pockets on one inner ear engage the carrier's spherical
        # bump. Loosening the M4 bolt lets the ear flex enough to move between
        # the 15-degree index positions.
        inner_ear_y = EAR_GAP / 2.0
        pocket_center_y = inner_ear_y - (DETENT_SPHERE_RADIUS - DETENT_POCKET_DEPTH)
        for tilt_degrees in PIVOT_INDEX_ANGLES:
            tilt_radians = math.radians(tilt_degrees)
            pocket = (
                cq.Workplane("XY")
                .sphere(DETENT_SPHERE_RADIUS)
                .translate(
                    (
                        PIVOT_RADIUS - DETENT_RADIUS * math.sin(tilt_radians),
                        pocket_center_y,
                        PIVOT_Z - DETENT_RADIUS * math.cos(tilt_radians),
                    )
                )
            )
            clevis = clevis.cut(pocket)
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
    stabilizer_hole = (
        cq.Workplane("XY")
        .center(0.0, TRIPOD_STABILIZER_OFFSET)
        .circle(TRIPOD_STABILIZER_HOLE_DIAMETER / 2.0)
        .extrude(TRIPOD_STABILIZER_HOLE_DEPTH)
    )
    return hub.cut(through_hole).cut(nut_pocket).cut(stabilizer_hole)


def cut_pivot_hole(part: cq.Workplane) -> cq.Workplane:
    pivot_cut = (
        cq.Workplane("XZ").circle(PIVOT_HOLE_DIAMETER / 2.0).extrude(12.0, both=True)
    )
    return part.cut(pivot_cut)


def make_pivot_tongue() -> cq.Workplane:
    tongue = cq.Workplane("XY").box(
        20.0, TONGUE_THICKNESS, 20.0, centered=(True, True, True)
    )
    bump_center_y = (TONGUE_THICKNESS / 2.0) - (
        DETENT_SPHERE_RADIUS - DETENT_BUMP_HEIGHT
    )
    detent_bump = (
        cq.Workplane("XY")
        .sphere(DETENT_SPHERE_RADIUS)
        .translate((0.0, bump_center_y, -DETENT_RADIUS))
    )
    return cut_pivot_hole(tongue).union(detent_bump)


def make_technexion_carrier() -> cq.Workplane:
    # Keep the wide shelf outside the hub ears through the useful tilt range.
    # A deep, narrow spine passes through the clevis gap, overlaps the tongue,
    # and continues under the camera to carry its bending load into the pivot.
    shelf_z = 8.0
    shelf_top = 12.0
    shelf = (
        cq.Workplane("XY")
        .box(TECH_SHELF_LENGTH, 36.0, 4.0, centered=(True, True, False))
        .translate((TECH_SHELF_CENTER_X, 0.0, shelf_z))
    )
    support_spine = (
        cq.Workplane("XY")
        .box(
            TECH_SUPPORT_SPINE_END_X - TECH_SUPPORT_SPINE_START_X,
            TONGUE_THICKNESS,
            shelf_top - TECH_SUPPORT_SPINE_BOTTOM_Z,
            centered=(True, True, True),
        )
        .translate(
            (
                (TECH_SUPPORT_SPINE_START_X + TECH_SUPPORT_SPINE_END_X) / 2.0,
                0.0,
                (TECH_SUPPORT_SPINE_BOTTOM_Z + shelf_top) / 2.0,
            )
        )
    )
    carrier = make_pivot_tongue().union(support_spine).union(shelf)

    # The camera drops in from above. Side walls control roll and lateral
    # motion, while the perforated front frame catches the lens-plane corners
    # when gravity pulls the downward-aimed camera toward the front.
    inside_half_width = (TECH_BODY_WIDTH / 2.0) + TECH_CRADLE_CLEARANCE
    wall_center_y = inside_half_width + (TECH_WALL_THICKNESS / 2.0)
    front_inner_x = (
        TECH_CAMERA_CENTER_X + (TECH_BODY_DEPTH / 2.0) + TECH_CRADLE_CLEARANCE
    )
    front_center_x = front_inner_x + (TECH_WALL_THICKNESS / 2.0)
    side_wall_x_min = 16.0
    side_wall_x_max = front_inner_x + TECH_WALL_THICKNESS
    for y in (-wall_center_y, wall_center_y):
        side_wall = (
            cq.Workplane("XY")
            .box(
                side_wall_x_max - side_wall_x_min,
                TECH_WALL_THICKNESS,
                18.0,
                centered=(True, True, True),
            )
            .translate(
                (
                    (side_wall_x_min + side_wall_x_max) / 2.0,
                    y,
                    19.0,
                )
            )
        )
        carrier = carrier.union(side_wall)

    front_frame_width = 2.0 * (inside_half_width + TECH_WALL_THICKNESS)
    front_frame = (
        cq.Workplane("XY")
        .box(
            TECH_WALL_THICKNESS,
            front_frame_width,
            33.0,
            centered=(True, True, True),
        )
        .translate((front_center_x, 0.0, 26.5))
    )
    front_aperture = (
        cq.Workplane("YZ", origin=(front_center_x, 0.0, 0.0))
        .center(0.0, shelf_top + (TECH_BODY_HEIGHT / 2.0))
        .circle(TECH_FRONT_APERTURE / 2.0)
        .extrude(4.0, both=True)
    )
    carrier = carrier.union(front_frame.cut(front_aperture))

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
    return cut_pivot_hole(carrier.cut(mounting_holes))


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
    return cut_pivot_hole(carrier)


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
    coupon = cq.Workplane("XY").box(
        34.0, 42.0, BASE_THICKNESS, centered=(True, True, False)
    )
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
    stabilizer_hole = (
        cq.Workplane("XY")
        .center(0.0, TRIPOD_STABILIZER_OFFSET)
        .circle(TRIPOD_STABILIZER_HOLE_DIAMETER / 2.0)
        .extrude(TRIPOD_STABILIZER_HOLE_DEPTH)
    )
    return coupon.cut(through_hole).cut(nut_pocket).cut(stabilizer_hole)


def make_detent_clevis_coupon() -> cq.Workplane:
    cutter = (
        cq.Workplane("XY")
        .box(24.0, ARM_WIDTH, 40.0, centered=(True, True, False))
        .translate((PIVOT_RADIUS, 0.0, 0.0))
    )
    return make_hub().intersect(cutter).translate((-PIVOT_RADIUS, 0.0, 0.0))


def make_detent_tongue_coupon() -> cq.Workplane:
    return make_pivot_tongue()


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


def intersection_volume(left: cq.Workplane, right: cq.Workplane) -> float:
    intersection = left.intersect(right)
    return sum(solid.Volume() for solid in intersection.solids().vals())


def validate_hub_clearance(
    hub: cq.Workplane,
    components: tuple[tuple[str, cq.Workplane], ...],
) -> None:
    # Rotational symmetry means checking one clevis covers all four stations.
    for tilt_degrees in PIVOT_INDEX_ANGLES:
        for name, component in components:
            volume = intersection_volume(
                hub, placed_carrier(component, 0.0, tilt_degrees)
            )
            if volume > 0.001:
                raise RuntimeError(
                    f"{name} intersects hub by {volume:.3f} mm^3 "
                    f"at {tilt_degrees:.0f} degrees"
                )


def validate_assembly_interfaces(
    hub: cq.Workplane,
    technexion: cq.Workplane,
    analog: cq.Workplane,
    technexion_camera: cq.Workplane,
    analog_camera: cq.Workplane,
    tripod_hardware: cq.Workplane,
    pivot_hardware: cq.Workplane,
) -> None:
    stationary_pairs = (
        ("technexion camera/cradle", technexion, technexion_camera),
        ("analog camera/carrier", analog, analog_camera),
        ("tripod hardware/hub", tripod_hardware, hub),
    )
    for name, left, right in stationary_pairs:
        volume = intersection_volume(left, right)
        if volume > 0.001:
            raise RuntimeError(f"{name} interference is {volume:.3f} mm^3")

    placed_hardware = placed_pivot_hardware(pivot_hardware, 0.0)
    for tilt_degrees in PIVOT_INDEX_ANGLES:
        for name, carrier in (
            ("technexion_carrier", technexion),
            ("analog_flush_carrier", analog),
        ):
            placed = placed_carrier(carrier, 0.0, tilt_degrees)
            volume = intersection_volume(placed_hardware, placed)
            if volume > 0.001:
                raise RuntimeError(
                    f"{name}/M4 hardware interference is {volume:.3f} mm^3 "
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
        .translate((TECH_CAMERA_CENTER_X, 0.0, shelf_top + TECH_BODY_HEIGHT / 2.0))
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


def make_compound(parts: tuple[cq.Workplane, ...]) -> cq.Workplane:
    shapes = []
    for part in parts:
        shapes.extend(part.solids().vals())
    return cq.Workplane(obj=cq.Compound.makeCompound(shapes))


def make_tripod_nut_reference() -> cq.Workplane:
    pocket_floor_z = BASE_THICKNESS - TRIPOD_NUT_DEPTH
    nut = (
        cq.Workplane("XY")
        .polygon(6, hex_circumdiameter(TRIPOD_NUT_REFERENCE_ACROSS_FLATS))
        .extrude(TRIPOD_NUT_REFERENCE_HEIGHT)
        .translate((0.0, 0.0, pocket_floor_z))
    )
    thread_bore = (
        cq.Workplane("XY")
        .circle(4.98 / 2.0)
        .extrude(TRIPOD_NUT_REFERENCE_HEIGHT + 2.0)
        .translate((0.0, 0.0, pocket_floor_z - 1.0))
    )
    return nut.cut(thread_bore)


def make_printable_tripod_nut() -> cq.Workplane:
    """Make a loose-fit 1/4-20 nut sized for the hub's captured-nut pocket."""
    nut = (
        cq.Workplane("XY")
        .polygon(6, hex_circumdiameter(TRIPOD_NUT_REFERENCE_ACROSS_FLATS))
        .extrude(TRIPOD_NUT_REFERENCE_HEIGHT)
    )

    minor_radius = TRIPOD_PRINTED_THREAD_MINOR_DIAMETER / 2.0
    major_radius = TRIPOD_PRINTED_THREAD_MAJOR_DIAMETER / 2.0
    profile_inner_radius = minor_radius - TRIPOD_PRINTED_THREAD_CUTTER_OVERLAP
    helix_start = -TRIPOD_THREAD_PITCH
    thread_path = cq.Wire.makeHelix(
        TRIPOD_THREAD_PITCH,
        TRIPOD_NUT_REFERENCE_HEIGHT + (2.0 * TRIPOD_THREAD_PITCH),
        major_radius,
        center=(0.0, 0.0, helix_start),
    )
    thread_profile = (
        cq.Workplane("XZ")
        .moveTo(
            profile_inner_radius,
            helix_start - TRIPOD_PRINTED_THREAD_HALF_WIDTH,
        )
        .lineTo(major_radius, helix_start)
        .lineTo(
            profile_inner_radius,
            helix_start + TRIPOD_PRINTED_THREAD_HALF_WIDTH,
        )
        .close()
        .wire()
        .val()
    )
    thread_cutter = cq.Workplane(
        obj=cq.Solid.sweep(
            thread_profile,
            [],
            thread_path,
            makeSolid=True,
            isFrenet=True,
        )
    )
    bore = (
        cq.Workplane("XY")
        .circle(minor_radius)
        .extrude(TRIPOD_NUT_REFERENCE_HEIGHT + 2.0)
        .translate((0.0, 0.0, -1.0))
    )

    entry_radius = major_radius + TRIPOD_PRINTED_THREAD_ENTRY_CHAMFER
    entry_inner_radius = minor_radius + (TRIPOD_PRINTED_THREAD_CUTTER_OVERLAP / 2.0)
    bottom_entry = cq.Workplane(
        obj=cq.Solid.makeCone(
            entry_radius,
            entry_inner_radius,
            TRIPOD_PRINTED_THREAD_ENTRY_CHAMFER,
        )
    )
    top_entry = cq.Workplane(
        obj=cq.Solid.makeCone(
            entry_inner_radius,
            entry_radius,
            TRIPOD_PRINTED_THREAD_ENTRY_CHAMFER,
            pnt=cq.Vector(
                0.0,
                0.0,
                TRIPOD_NUT_REFERENCE_HEIGHT - TRIPOD_PRINTED_THREAD_ENTRY_CHAMFER,
            ),
        )
    )
    return nut.cut(bore).cut(thread_cutter).cut(bottom_entry).cut(top_entry)


def make_tripod_screw_reference() -> cq.Workplane:
    shaft = (
        cq.Workplane("XY").circle(6.2 / 2.0).extrude(4.7).translate((0.0, 0.0, -0.2))
    )
    head = cq.Workplane("XY").circle(7.0).extrude(3.0).translate((0.0, 0.0, -3.0))
    return shaft.union(head)


def make_tripod_stabilizer_pin_reference() -> cq.Workplane:
    pin = (
        cq.Workplane("XY")
        .center(0.0, TRIPOD_STABILIZER_OFFSET)
        .circle(TRIPOD_STABILIZER_PIN_DIAMETER / 2.0)
        .extrude(TRIPOD_STABILIZER_PIN_HEIGHT)
    )
    return pin.edges(">Z").fillet(0.5)


def make_tripod_hardware_reference() -> cq.Workplane:
    return make_compound(
        (
            make_tripod_nut_reference(),
            make_tripod_screw_reference(),
            make_tripod_stabilizer_pin_reference(),
        )
    )


def orient_z_hardware_along_y(part: cq.Workplane) -> cq.Workplane:
    return part.rotate((0, 0, 0), (1, 0, 0), 90.0)


def make_m4_bolt_reference() -> cq.Workplane:
    shaft = cq.Workplane("XY").circle(M4_BOLT_DIAMETER / 2.0).extrude(M4_BOLT_LENGTH)
    head = (
        cq.Workplane("XY")
        .polygon(6, hex_circumdiameter(M4_HEAD_ACROSS_FLATS))
        .extrude(M4_HEAD_HEIGHT)
        .translate((0.0, 0.0, -M4_HEAD_HEIGHT))
    )
    head_bearing_y = (EAR_GAP / 2.0) + EAR_THICKNESS + M4_WASHER_THICKNESS
    return orient_z_hardware_along_y(shaft.union(head)).translate(
        (0.0, head_bearing_y, 0.0)
    )


def make_m4_washer_reference(y_position: float) -> cq.Workplane:
    washer = (
        cq.Workplane("XY")
        .circle(M4_WASHER_OUTER_DIAMETER / 2.0)
        .circle(M4_WASHER_INNER_DIAMETER / 2.0)
        .extrude(M4_WASHER_THICKNESS)
    )
    return orient_z_hardware_along_y(washer).translate((0.0, y_position, 0.0))


def make_m4_nut_reference() -> cq.Workplane:
    nut = (
        cq.Workplane("XY")
        .polygon(6, hex_circumdiameter(M4_NUT_ACROSS_FLATS))
        .extrude(M4_NUT_HEIGHT)
    )
    bore = (
        cq.Workplane("XY")
        .circle(3.3 / 2.0)
        .extrude(M4_NUT_HEIGHT + 2.0)
        .translate((0.0, 0.0, -1.0))
    )
    negative_ear_outer_y = -((EAR_GAP / 2.0) + EAR_THICKNESS)
    return orient_z_hardware_along_y(nut.cut(bore)).translate(
        (0.0, negative_ear_outer_y - M4_WASHER_THICKNESS, 0.0)
    )


def make_pivot_hardware_reference() -> cq.Workplane:
    positive_ear_outer_y = (EAR_GAP / 2.0) + EAR_THICKNESS
    negative_ear_outer_y = -positive_ear_outer_y
    return make_compound(
        (
            make_m4_bolt_reference(),
            make_m4_washer_reference(positive_ear_outer_y + M4_WASHER_THICKNESS),
            make_m4_washer_reference(negative_ear_outer_y),
            make_m4_nut_reference(),
        )
    )


def placed_pivot_hardware(
    hardware: cq.Workplane, azimuth_degrees: float
) -> cq.Workplane:
    angle = math.radians(azimuth_degrees)
    return hardware.rotate((0, 0, 0), (0, 0, 1), azimuth_degrees).translate(
        (
            PIVOT_RADIUS * math.cos(angle),
            PIVOT_RADIUS * math.sin(angle),
            PIVOT_Z,
        )
    )


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


def reference_stats(name: str, reference: cq.Workplane) -> str:
    shape = reference.val()
    box = shape.BoundingBox()
    solid_count = reference.solids().size()
    if not shape.isValid():
        raise RuntimeError(f"{name} is not a valid reference assembly")
    return (
        f"{name}: {box.xlen:.2f} x {box.ylen:.2f} x {box.zlen:.2f} mm, "
        f"solids={solid_count} (reference only)"
    )


def place_on_build_plate(part: cq.Workplane) -> cq.Workplane:
    box = part.val().BoundingBox()
    return part.translate((0.0, 0.0, -box.zmin))


def orient_technexion_for_printing(part: cq.Workplane) -> cq.Workplane:
    # Put the broad lens-plane frame on the bed and grow the cradle rearward.
    return place_on_build_plate(part.rotate((0, 0, 0), (0, 1, 0), 90.0))


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


def export_reference(output_dir: Path, name: str, reference: cq.Workplane) -> str:
    cq.exporters.export(
        reference,
        str(output_dir / f"{name}.stl"),
        tolerance=0.04,
        angularTolerance=0.08,
    )
    cq.exporters.export(reference, str(output_dir / f"{name}.step"))
    return reference_stats(name, reference)


def generate(output_dir: Path, tilt_degrees: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    hub = make_hub()
    technexion = make_technexion_carrier()
    analog = make_analog_carrier()
    analog_coupon = make_analog_fit_coupon()
    nut_coupon = make_tripod_nut_coupon()
    printable_tripod_nut = make_printable_tripod_nut()
    detent_clevis_coupon = make_detent_clevis_coupon()
    detent_tongue_coupon = make_detent_tongue_coupon()
    technexion_camera = make_technexion_mockup()
    analog_camera = make_analog_mockup()
    tripod_hardware = make_tripod_hardware_reference()
    pivot_hardware = make_pivot_hardware_reference()
    validate_hub_clearance(
        hub,
        (
            ("technexion_carrier", technexion),
            ("analog_flush_carrier", analog),
            ("technexion_camera_reference", technexion_camera),
            ("analog_camera_reference", analog_camera),
        ),
    )
    validate_assembly_interfaces(
        hub,
        technexion,
        analog,
        technexion_camera,
        analog_camera,
        tripod_hardware,
        pivot_hardware,
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
        export_part(output_dir, "tripod_nut_1_4_20", printable_tripod_nut),
        export_part(output_dir, "pivot_detent_clevis_coupon", detent_clevis_coupon),
        export_part(
            output_dir,
            "pivot_detent_tongue_coupon",
            detent_tongue_coupon,
            place_on_build_plate(
                detent_tongue_coupon.rotate((0, 0, 0), (1, 0, 0), 90.0)
            ),
        ),
        export_reference(
            output_dir, "tripod_mount_hardware_reference", tripod_hardware
        ),
        export_reference(output_dir, "pivot_hardware_reference", pivot_hardware),
    ]

    assembly = cq.Assembly(name="four_camera_tripod_rig")
    assembly.add(hub, name="tripod_hub", color=cq.Color(0.18, 0.22, 0.26))
    assembly.add(
        tripod_hardware,
        name="tripod_mount_hardware_reference",
        color=cq.Color(0.68, 0.70, 0.72),
    )
    printed_shapes = [hub.val()]
    camera_shapes = []
    hardware_shapes = tripod_hardware.solids().vals()

    placements = (
        ("front_technexion", technexion, technexion_camera, 0.0),
        ("right_analog", analog, analog_camera, 90.0),
        ("back_technexion", technexion, technexion_camera, 180.0),
        ("left_analog", analog, analog_camera, 270.0),
    )
    for name, carrier, camera, azimuth in placements:
        placed_printed_part = placed_carrier(carrier, azimuth, tilt_degrees)
        placed_camera = placed_carrier(camera, azimuth, tilt_degrees)
        placed_hardware = placed_pivot_hardware(pivot_hardware, azimuth)
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
        assembly.add(
            placed_hardware,
            name=f"{name}_pivot_hardware_reference",
            color=cq.Color(0.68, 0.70, 0.72),
        )
        printed_shapes.append(placed_printed_part.val())
        camera_shapes.append(placed_camera.val())
        hardware_shapes.extend(placed_hardware.solids().vals())

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
    cq.exporters.export(
        cq.Compound.makeCompound(hardware_shapes),
        str(output_dir / "camera_rig_hardware_references_preview.stl"),
        tolerance=0.04,
        angularTolerance=0.08,
    )
    (output_dir / "dimensions.txt").write_text(
        "\n".join(stats) + "\n", encoding="ascii"
    )


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
