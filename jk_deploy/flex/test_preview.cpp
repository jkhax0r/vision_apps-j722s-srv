#include "jk_preview.h"
#include <assert.h>

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *path = argv[1];
    assert(jk_preview_selection(path) == -1);
    const char *states[] = {"-1\n", "0\n", "1\n", "2\n", "3\n", "4\n", "bad", "2 garbage", ""};
    const int expected[] = {-1, 0, 1, 2, 3, -1, -1, -1, -1};
    for (int i = 0; i < 9; i++)
    {
        FILE *file = fopen(path, "w");
        assert(file);
        fputs(states[i], file);
        fclose(file);
        assert(jk_preview_selection(path) == expected[i]);
    }
    for (int camera = 0; camera < 4; camera++)
    {
        jk_preview_rect quad = jk_preview_viewport(camera, false, 1920, 720, 1920, 1200);
        assert(quad.width == 480 && quad.height == 300);
        assert(quad.x == (camera % 2) * 480);
        assert(quad.y == (camera < 2 ? 390 : 30));
        jk_preview_rect single = jk_preview_viewport(camera, true, 1920, 720, 1920, 1200);
        assert(single.x == 0 && single.y == 60 && single.width == 960 && single.height == 600);
        jk_preview_rect portrait = jk_preview_viewport(camera, true, 1920, 720, 1200, 1920);
        assert(portrait.x == 255 && portrait.y == 0 && portrait.width == 450 && portrait.height == 720);
    }
    remove(path);
    return 0;
}
