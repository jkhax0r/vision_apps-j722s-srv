/* Host adapter around the unmodified TI bowl generator. */
#include <stdlib.h>
#include "C6xSimulator.h"
#include "../../../kernels/srv/c66/core_generate_3dbowl.c"

int jk_generate_bowl(const float *centers, int base_half_cells, float *xyz)
{
    svGpuLutGen_t config = {0};
    svGeometric_t offsets = {0};
    float calmat[48] = {0};
    const int source[4] = {0, 1, 1, 0};
    int i, axis;

    if (base_half_cells < 4 || base_half_cells > 400 || centers == NULL || xyz == NULL)
        return -1;
    config.SVOutDisplayWidth = 1080;
    config.SVOutDisplayHeight = 1080;
    config.numCameras = 4;
    config.subsampleratio = 4;
    offsets.offsetXleft = offsets.offsetYfront = -base_half_cells;
    offsets.offsetXright = offsets.offsetYback = base_half_cells;

    /* TI derives only the center and scale from these slots. Duplicate the
     * pair symmetrically; slots 0/2 supply its physical separation. These
     * are NOT the camera poses used for image projection. */
    for (i = 0; i < 4; i++)
        for (axis = 0; axis < 3; axis++)
        {
            calmat[12 * i + axis * 4] = 1.0f;
            calmat[12 * i + 9 + axis] = -centers[3 * source[i] + axis];
        }
    svGenerate_3D_Bowl(&config, &offsets, calmat, xyz);
    return 0;
}
