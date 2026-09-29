#!/usr/bin/env python3
"""Build printable corner locators and true-size, uniquely identified labels."""
import json
from pathlib import Path
import sys

import cadquery as cq
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import numpy as np
import pymupdf as pdf

HERE = Path(__file__).resolve().parent
OUT = HERE / "generated"
sys.path.insert(0, str(HERE.parents[2] / "camera_rig/v2"))
from render_preview import camera_basis, project, read_binary_stl, shaded_colors

MM = 72 / 25.4
SIDE = 130.0
PLATE = 2.0
LIP = 3.0
DROP = 16.0
RELIEF = 40.0
LABEL_START = 22.0
LABEL_SIZE = 100.0
TAG_SIZE = 80.0
QUIET = (LABEL_SIZE - TAG_SIZE) / 2
IDS = (1, 2, 3, 4)
DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def box(x, y, z, dx, dy, dz):
    return cq.Workplane("XY").box(dx, dy, dz, centered=False).translate((x, y, z))


def build_cap(lips=True):
    outline = [(0, RELIEF), (RELIEF, 0), (SIDE, 0), (SIDE, SIDE), (0, SIDE)]
    part = cq.Workplane("XY").polyline(outline).close().extrude(PLATE)
    if lips:
        # Fences begin past the rounded corner, with a 1 mm overlap into the plate.
        part = part.union(box(RELIEF, -LIP, -DROP, SIDE-RELIEF-6, LIP+1, DROP+PLATE))
        part = part.union(box(-LIP, RELIEF, -DROP, LIP+1, SIDE-RELIEF-6, DROP+PLATE))
    # Shallow L guides sit outside the 100 mm label, leaving its white border intact.
    for x in (LABEL_START-1, LABEL_START+LABEL_SIZE+1):
        for y in (LABEL_START-1, LABEL_START+LABEL_SIZE+1):
            dx = 1 if x < SIDE/2 else -1
            dy = 1 if y < SIDE/2 else -1
            part = part.cut(box(min(x, x+dx*5), y-.3, PLATE-.4, 5, .6, .5))
            part = part.cut(box(x-.3, min(y, y+dy*5), PLATE-.4, .6, 5, .5))
    return part.clean()


def print_orientation(part):
    # Label face on the bed; two lips grow upward, with no large bridges/supports.
    return part.rotate((0, 0, 0), (1, 0, 0), 180).translate((LIP, SIDE, PLATE))


def marker_cells(marker_id):
    return cv2.aruco.generateImageMarker(DICTIONARY, marker_id, 6, borderBits=1)


def draw_text(page, rect_mm, text, size=10):
    rect = pdf.Rect(*(v*MM for v in rect_mm))
    font = pdf.Font("helv")
    lines = text.splitlines()
    height = (font.ascender-font.descender)*size
    if height*len(lines) > rect.height:
        raise ValueError(f"Text does not fit: {text}")
    for i, line in enumerate(lines):
        width = font.text_length(line, fontsize=size)
        if width > rect.width:
            raise ValueError(f"Text is too wide: {line}")
        page.insert_text((rect.x0+(rect.width-width)/2, rect.y0+font.ascender*size+i*height),
                         line, fontsize=size, fontname="helv")


def draw_label(page, marker_id, x, y):
    # PDF coordinates are top-down. The clipped lower-left corner points outward.
    path = [(x, y), (x+100, y), (x+100, y+100), (x+5, y+100),
            (x, y+95), (x, y)]
    page.draw_polyline([pdf.Point(a*MM, b*MM) for a, b in path],
                       color=(.55, .55, .55), width=.25)
    cells = marker_cells(marker_id)
    cell = TAG_SIZE / 6
    shape = page.new_shape()
    for row in range(6):
        for col in range(6):
            if cells[row, col] == 0:
                shape.draw_rect(pdf.Rect((x+QUIET+col*cell)*MM,
                                         (y+QUIET+row*cell)*MM,
                                         (x+QUIET+(col+1)*cell)*MM,
                                         (y+QUIET+(row+1)*cell)*MM))
    shape.finish(color=None, fill=(0, 0, 0))
    shape.commit()


def make_labels():
    doc = pdf.open()
    for marker_id in IDS:
        page = doc.new_page(width=101.6*MM, height=152.4*MM)
        # Tangent to physical media edges, outside the 100 mm target cutout.
        page.draw_circle(pdf.Point(50.8*MM, 2.5*MM), 2.5*MM,
                         color=None, fill=(0, 0, 0))
        page.draw_circle(pdf.Point(50.8*MM, 149.9*MM), 2.5*MM,
                         color=None, fill=(0, 0, 0))
        draw_text(page, (4, 8, 97.6, 15), f"CORNER {marker_id} / ArUco ID {marker_id}", 12)
        draw_text(page, (3, 16, 98.6, 23), "Print at 100% / actual size. No fit-to-page.", 8)
        draw_label(page, marker_id, .8, 26.2)
        draw_text(page, (3, 129, 98.6, 135), "Clip lower-left corner; point it toward table corner.", 8)
        page.draw_line(pdf.Point(25.8*MM, 140*MM), pdf.Point(75.8*MM, 140*MM), width=.7)
        for x in (25.8, 75.8):
            page.draw_line(pdf.Point(x*MM, 139*MM), pdf.Point(x*MM, 141*MM), width=.7)
        draw_text(page, (25, 142, 77, 147), "50 mm scale check", 8)
        single = pdf.open()
        single.insert_pdf(doc, from_page=marker_id-1, to_page=marker_id-1)
        single.save(OUT / f"corner_{marker_id}_4x6.pdf")
        single.close()
        # Full label raster is for inspection/detection tests, not paper scaling.
        tag = cv2.aruco.generateImageMarker(DICTIONARY, marker_id, 960)
        canvas = np.full((1200, 1200), 255, np.uint8)
        canvas[120:1080, 120:1080] = tag
        cv2.imwrite(str(OUT / f"corner_{marker_id}_label.png"), canvas)
    doc.set_metadata({"title": "Table corner calibration markers: 4 x 6 inch labels",
                      "subject": "DICT_4X4_50 IDs 1-4, 80 mm markers, 100 mm cutouts"})
    doc.save(OUT / "corner_markers_4x6.pdf", deflate=True)
    doc[0].get_pixmap(matrix=pdf.Matrix(2, 2)).save(OUT / "label_preview.png")
    doc.close()
    # One label per letter/A4 page avoids accidental shrinking in office printers.
    for name, width, height in (("letter", 215.9, 279.4), ("a4", 210., 297.)):
        doc = pdf.open()
        for marker_id in IDS:
            page = doc.new_page(width=width*MM, height=height*MM)
            draw_text(page, (10, 20, width-10, 30), f"CORNER {marker_id} / ArUco ID {marker_id}", 18)
            draw_text(page, (10, 35, width-10, 45), "Print at 100% / actual size. Cut on gray outline.", 11)
            draw_label(page, marker_id, (width-100)/2, 65)
            draw_text(page, (10, 175, width-10, 195),
                      "80 mm black marker / 100 mm white cutout\nClipped corner points toward the outside table corner.", 10)
        doc.save(OUT / f"corner_markers_{name}.pdf", deflate=True)
        doc.close()


def rectangles_to_mesh(rects):
    triangles = []
    for x0, y0, x1, y1, z in rects:
        a, b, c, d = (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)
        triangles.extend(((a, b, c), (a, c, d)))
    triangles = np.array(triangles, float)
    return triangles, np.tile([0., 0., 1.], (len(triangles), 1))


def render_preview():
    plt.rcParams.update({"font.size": 11})
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), dpi=150)
    fig.patch.set_facecolor("#f4f6f8")
    tris, normals = read_binary_stl(OUT / "corner_cap_reference.stl")
    yellow = ((tris, normals), (.95, .77, .09))
    white = (rectangles_to_mesh([(22, 22, 122, 122, 2.02)]), (1., 1., 1.))
    rects = []
    cells = marker_cells(1)
    for row, col in np.argwhere(cells == 0):
        x0, y0 = 32+col*80/6, 112-(row+1)*80/6
        rects.append((x0, y0, x0+80/6, y0+80/6, 2.04))
    black = (rectangles_to_mesh(rects), (.035, .04, .045))
    for axis, position, meshes, title in (
        (axes[0], (-185, -210, 285), (yellow, white, black), "Top: 80 mm ID marker on a yellow locator"),
        (axes[1], (-190, -215, -245), (yellow,), "Underside: two edge stops; open outer corner"),
    ):
        position = np.array(position, float)
        right, up, forward = camera_basis(position, np.array([62., 62., 0.]), np.array([0., 0., 1.]))
        for layer, ((triangles, ns), color) in enumerate(meshes):
            facing = np.einsum("ij,ij->i", ns, position-triangles.mean(axis=1)) > 0
            triangles, ns = triangles[facing], ns[facing]
            p, d = project(triangles, position, right, up, forward)
            order = np.argsort(d)[::-1]
            # Decals sit on the unobstructed top surface; draw after the solid.
            axis.add_collection(PolyCollection(p[order], facecolors=shaded_colors(ns, color)[order],
                                              edgecolors="none", antialiased=False, zorder=layer+1))
        axis.autoscale_view()
        axis.set_aspect("equal")
        axis.margins(.1)
        axis.set_title(title, fontsize=12, pad=12)
        axis.axis("off")
    fig.suptitle("Table Corner Calibration Locator / v1", fontsize=19, y=.98)
    fig.text(.5, .04, "130 mm plate / 2 mm thick / 16 mm edge stops / print four identical bases",
             ha="center", fontsize=12)
    fig.subplots_adjust(top=.86, bottom=.14, left=.02, right=.98, wspace=.05)
    fig.savefig(OUT / "corner_marker_preview.png", facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    parts = {"table_corner_cap": build_cap(), "flat_marker_plate": build_cap(False)}
    volumes = {}
    for name, part in parts.items():
        shape = part.val()
        if not shape.isValid() or len(shape.Solids()) != 1:
            raise ValueError(f"Invalid CAD solid: {name}")
        cq.exporters.export(print_orientation(part), str(OUT / f"{name}.stl"), tolerance=.04)
        cq.exporters.export(part, str(OUT / f"{name}.step"))
        volumes[name] = shape.Volume()
    cq.exporters.export(parts["table_corner_cap"], str(OUT / "corner_cap_reference.stl"))
    make_labels()
    manifest = {
        "version": 1, "units": "mm", "dictionary": "DICT_4X4_50", "ids": list(IDS),
        "plate_side": SIDE, "plate_thickness": PLATE, "fence_depth": DROP,
        "fence_thickness": LIP, "corner_relief": RELIEF,
        "label_size": LABEL_SIZE, "marker_black_outer_size": TAG_SIZE,
        "quiet_margin": QUIET, "label_start_xy": [22, 22],
        "frame": "Virtual table corner is (0,0,0); x/y point inward, z points above table",
        "marker_corners_canonical_xy": [[32, 112], [112, 112], [112, 32], [32, 32]],
        "marker_center_xy": [72, 72], "marker_plane_z_without_paper": PLATE,
        "orientation": "Clipped lower-left label corner toward chamfered outside table corner",
        "table_registration": "Valid only when both fences contact straight vertical table edges",
        "flat_plate_registration": "No edge registration; locate crop corners separately",
        "volumes_mm3": volumes,
        "status": "CAD and synthetic detection checks only; physical print and live camera test pending"
    }
    (OUT / "marker_geometry.json").write_text(json.dumps(manifest, indent=2)+"\n")
    render_preview()
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
