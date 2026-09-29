#!/usr/bin/env python3
"""Convert native Flex UYVY snapshots without changing their orientation."""
import argparse
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    previews = []
    for slot in range(4):
        raw = np.fromfile(args.directory / f"input{slot}.uyvy", dtype=np.uint8)
        if raw.size != 1920 * 1200 * 2:
            raise ValueError(f"Unexpected frame length for input{slot}")
        frame = cv2.cvtColor(raw.reshape(1200, 1920, 2), cv2.COLOR_YUV2BGR_UYVY)
        cv2.imwrite(str(args.directory / f"input{slot}.png"), frame)
        thumb = cv2.resize(frame, (960, 600), interpolation=cv2.INTER_AREA)
        cv2.putText(thumb, f"INPUT {slot} / video{slot+2}", (20, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        previews.append(thumb)
    cv2.imwrite(str(args.directory / "contact.png"),
                np.vstack((np.hstack(previews[:2]), np.hstack(previews[2:]))))


if __name__ == "__main__":
    main()
