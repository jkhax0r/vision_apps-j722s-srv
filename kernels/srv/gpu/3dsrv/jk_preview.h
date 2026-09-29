#ifndef JK_PREVIEW_H
#define JK_PREVIEW_H

#include <stdio.h>

struct jk_preview_rect { int x, y, width, height; };

static inline int jk_preview_selection(const char *path)
{
    FILE *file = fopen(path, "r");
    if (!file)
        return -1;
    int selected = -1;
    char extra;
    int fields = fscanf(file, "%d %c", &selected, &extra);
    fclose(file);
    return fields == 1 && selected >= 0 && selected < 4 ? selected : -1;
}

static inline jk_preview_rect jk_preview_viewport(int camera, bool expanded,
    int screen_width, int screen_height, int camera_width, int camera_height)
{
    int cell_width = screen_width / (expanded ? 2 : 4);
    int cell_height = screen_height / (expanded ? 1 : 2);
    int width = cell_width;
    int height = width * camera_height / camera_width;
    if (height > cell_height)
    {
        height = cell_height;
        width = height * camera_width / camera_height;
    }
    jk_preview_rect rect = {
        (expanded ? 0 : (camera % 2) * cell_width) + (cell_width - width) / 2,
        (expanded ? 0 : (1 - camera / 2) * cell_height) + (cell_height - height) / 2,
        width, height
    };
    return rect;
}

#endif
