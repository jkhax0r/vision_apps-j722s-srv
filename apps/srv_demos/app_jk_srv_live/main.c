/*
 * Live V4L2 smoke test for TI's SRV GPU OpenVX node on J722S.
 *
 * This is an intentionally simple bring-up app. It captures four UYVY V4L2
 * devices, fits each complete camera frame into a 640x480 OpenVX image, runs
 * tivxGlSrvNode(), presents the result, and optionally writes the final RGBX
 * output frame to disk. The fit preserves the GMSL camera aspect ratio; the
 * analog 720x480 samples are normalized to their intended 4:3 display shape.
 */

#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

#include <VX/vx.h>
#include <TI/hwa_kernels.h>
#include <TI/tivx_srv.h>
#include <TI/video_io_display.h>
#include <TI/video_io_kernels.h>
#include <render.h>
#include <utils/app_init/include/app_init.h>
#include "lens_distortion_correction.h"
#include "srv_common.h"
#include "core_generate_3dbowl.h"
#include "core_generate_gpulut.h"

#define IN_WIDTH      (640u)
#define IN_HEIGHT     (480u)
#define OUT_WIDTH     (1280u)
#define OUT_HEIGHT    (800u)
#define NUM_CAMERAS   (4u)
#define NUM_VIEWS     (1u)
#define CAP_BUFFERS   (4u)
#define SV_LUT_WIDTH  (1080u)
#define SV_LUT_HEIGHT (1080u)
#define SV_SUBSAMPLE  (4u)
#define SV_XYZLUT3D_SIZE \
    ((SV_LUT_HEIGHT / SV_SUBSAMPLE) * \
     (SV_LUT_WIDTH / SV_SUBSAMPLE) * 3u)
#define SV_GPULUT_SIZE \
    (((2u + (SV_LUT_WIDTH / SV_SUBSAMPLE)) * \
      (2u + (SV_LUT_HEIGHT / SV_SUBSAMPLE))) * 7u)

extern void tivxPlatformResetObjDescTableInfo(void);

static volatile sig_atomic_t stop_requested = 0;

static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

typedef struct {
    void *start;
    size_t length;
} CaptureBuffer;

typedef struct {
    const char *path;
    int fd;
    uint32_t width;
    uint32_t height;
    uint32_t stride;
    uint32_t sizeimage;
    CaptureBuffer buffers[CAP_BUFFERS];
    uint32_t num_buffers;
    uint32_t output_x;
    uint32_t output_y;
    uint32_t output_width;
    uint32_t output_height;
    uint32_t source_x_for_pair[IN_WIDTH / 2u];
    uint32_t source_y_for_line[IN_HEIGHT];
    int stacked_fields;
    int mirror_x;
    int flip_y;
} Camera;

static const char *default_devices[NUM_CAMERAS] = {
    "/usr/local/Ahsoka/devices/video/gmsl1",
    "/usr/local/Ahsoka/devices/video/analog0",
    "/usr/local/Ahsoka/devices/video/analog1",
    "/usr/local/Ahsoka/devices/video/gmsl0",
};

static const char *calibration_camera_names[NUM_CAMERAS] = {
    "camera0_front_gmsl1_640x480_nv12.yuv",
    "camera1_right_analog0_640x480_nv12.yuv",
    "camera2_back_analog1_640x480_nv12.yuv",
    "camera3_left_gmsl0_640x480_nv12.yuv",
};

static void release_image(vx_image *image)
{
    if ((image != NULL) && (*image != NULL))
    {
        vxReleaseImage(image);
    }
}

static void release_object_array(vx_object_array *array)
{
    if ((array != NULL) && (*array != NULL))
    {
        vxReleaseObjectArray(array);
    }
}

static void release_user_data_object(vx_user_data_object *object)
{
    if ((object != NULL) && (*object != NULL))
    {
        vxReleaseUserDataObject(object);
    }
}

static vx_status object_status(vx_reference ref)
{
    if (ref == NULL)
    {
        return VX_FAILURE;
    }

    return vxGetStatus(ref);
}

static int xioctl(int fd, unsigned long request, void *arg)
{
    int ret;

    do
    {
        ret = ioctl(fd, request, arg);
    } while ((ret == -1) && (errno == EINTR));

    return ret;
}

static double now_seconds(void)
{
    struct timespec ts;

    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + ((double)ts.tv_nsec / 1000000000.0);
}

static int camera_open(Camera *camera, const char *path)
{
    struct v4l2_capability cap;
    struct v4l2_format fmt;
    struct v4l2_requestbuffers req;
    uint32_t i;
    uint32_t x;
    uint32_t y;

    memset(camera, 0, sizeof(*camera));
    camera->path = path;
    camera->fd = open(path, O_RDWR | O_NONBLOCK);
    if (camera->fd < 0)
    {
        fprintf(stderr, "%s: open failed: %s\n", path, strerror(errno));
        return -1;
    }

    memset(&cap, 0, sizeof(cap));
    if (xioctl(camera->fd, VIDIOC_QUERYCAP, &cap) < 0)
    {
        fprintf(stderr, "%s: VIDIOC_QUERYCAP failed: %s\n", path, strerror(errno));
        return -1;
    }
    if ((cap.capabilities & V4L2_CAP_VIDEO_CAPTURE) == 0)
    {
        fprintf(stderr, "%s: not a V4L2 capture device\n", path);
        return -1;
    }
    if ((cap.capabilities & V4L2_CAP_STREAMING) == 0)
    {
        fprintf(stderr, "%s: device does not support streaming I/O\n", path);
        return -1;
    }

    memset(&fmt, 0, sizeof(fmt));
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (xioctl(camera->fd, VIDIOC_G_FMT, &fmt) < 0)
    {
        fprintf(stderr, "%s: VIDIOC_G_FMT failed: %s\n", path, strerror(errno));
        return -1;
    }
    if (fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_UYVY)
    {
        fprintf(stderr, "%s: expected UYVY, got fourcc 0x%08x\n",
                path, fmt.fmt.pix.pixelformat);
        return -1;
    }

    camera->width = fmt.fmt.pix.width;
    camera->height = fmt.fmt.pix.height;
    camera->stride = fmt.fmt.pix.bytesperline;
    camera->sizeimage = fmt.fmt.pix.sizeimage;
    printf("%s: %ux%u UYVY stride=%u size=%u\n",
           path, camera->width, camera->height, camera->stride, camera->sizeimage);

    camera->stacked_fields = strstr(path, "analog") != NULL;
    camera->mirror_x = 1;
    camera->flip_y = camera->stacked_fields == 0;
    if (camera->stacked_fields != 0)
    {
        /* 720x480 NTSC samples describe a 4:3 image with non-square pixels. */
        camera->output_width = IN_WIDTH;
        camera->output_height = IN_HEIGHT;
    }
    else if (((uint64_t)camera->width * IN_HEIGHT) >
             ((uint64_t)camera->height * IN_WIDTH))
    {
        camera->output_width = IN_WIDTH;
        camera->output_height =
            (uint32_t)(((uint64_t)camera->height * IN_WIDTH) / camera->width);
        camera->output_height &= ~1u;
    }
    else
    {
        camera->output_height = IN_HEIGHT;
        camera->output_width =
            (uint32_t)(((uint64_t)camera->width * IN_HEIGHT) / camera->height);
        camera->output_width &= ~1u;
    }
    camera->output_x = ((IN_WIDTH - camera->output_width) / 2u) & ~1u;
    camera->output_y = (IN_HEIGHT - camera->output_height) / 2u;
    printf("%s: full-frame fit=%ux%u offset=%u,%u mirror-x=%s flip-y=%s\n", path,
           camera->output_width, camera->output_height,
           camera->output_x, camera->output_y,
           camera->mirror_x != 0 ? "yes" : "no",
           camera->flip_y != 0 ? "yes" : "no");

    for (x = 0; x < camera->output_width; x += 2u)
    {
        uint32_t source_x =
            (uint32_t)(((uint64_t)x * camera->width) /
                       camera->output_width) & ~1u;

        if (source_x > (camera->width - 2u))
        {
            source_x = camera->width - 2u;
        }
        if (camera->mirror_x != 0)
        {
            source_x = camera->width - 2u - source_x;
        }
        camera->source_x_for_pair[x / 2u] = source_x;
    }
    for (y = 0; y < camera->output_height; y++)
    {
        uint32_t source_y =
            (uint32_t)(((uint64_t)y * camera->height) / camera->output_height);

        if (camera->stacked_fields != 0)
        {
            uint32_t line = source_y;

            source_y = line / 2u;
            if ((line & 1u) != 0u)
            {
                source_y += camera->height / 2u;
            }
        }
        if (camera->flip_y != 0)
        {
            source_y = camera->height - 1u - source_y;
        }
        if (source_y >= camera->height)
        {
            source_y = camera->height - 1u;
        }
        camera->source_y_for_line[y] = source_y;
    }

    memset(&req, 0, sizeof(req));
    req.count = CAP_BUFFERS;
    req.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    req.memory = V4L2_MEMORY_MMAP;
    if (xioctl(camera->fd, VIDIOC_REQBUFS, &req) < 0)
    {
        fprintf(stderr, "%s: VIDIOC_REQBUFS failed: %s\n", path, strerror(errno));
        return -1;
    }
    if (req.count < 2)
    {
        fprintf(stderr, "%s: insufficient mmap buffers\n", path);
        return -1;
    }

    camera->num_buffers = req.count;
    if (camera->num_buffers > CAP_BUFFERS)
    {
        camera->num_buffers = CAP_BUFFERS;
    }

    for (i = 0; i < camera->num_buffers; i++)
    {
        struct v4l2_buffer buf;

        memset(&buf, 0, sizeof(buf));
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        if (xioctl(camera->fd, VIDIOC_QUERYBUF, &buf) < 0)
        {
            fprintf(stderr, "%s: VIDIOC_QUERYBUF failed: %s\n", path, strerror(errno));
            return -1;
        }

        camera->buffers[i].length = buf.length;
        camera->buffers[i].start = mmap(NULL, buf.length, PROT_READ | PROT_WRITE,
                                        MAP_SHARED, camera->fd, buf.m.offset);
        if (camera->buffers[i].start == MAP_FAILED)
        {
            fprintf(stderr, "%s: mmap failed: %s\n", path, strerror(errno));
            return -1;
        }
    }

    for (i = 0; i < camera->num_buffers; i++)
    {
        struct v4l2_buffer buf;

        memset(&buf, 0, sizeof(buf));
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        if (xioctl(camera->fd, VIDIOC_QBUF, &buf) < 0)
        {
            fprintf(stderr, "%s: VIDIOC_QBUF failed: %s\n", path, strerror(errno));
            return -1;
        }
    }

    {
        enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (xioctl(camera->fd, VIDIOC_STREAMON, &type) < 0)
        {
            fprintf(stderr, "%s: VIDIOC_STREAMON failed: %s\n", path, strerror(errno));
            return -1;
        }
    }

    return 0;
}

static void camera_close(Camera *camera)
{
    uint32_t i;

    if (camera->fd >= 0)
    {
        enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        xioctl(camera->fd, VIDIOC_STREAMOFF, &type);
    }

    for (i = 0; i < camera->num_buffers; i++)
    {
        if ((camera->buffers[i].start != NULL) &&
            (camera->buffers[i].start != MAP_FAILED))
        {
            munmap(camera->buffers[i].start, camera->buffers[i].length);
        }
    }

    if (camera->fd >= 0)
    {
        close(camera->fd);
    }
    camera->fd = -1;
}

static int camera_dequeue(Camera *camera, struct v4l2_buffer *buf, int timeout_ms)
{
    fd_set fds;
    struct timeval tv;
    int ret;

    FD_ZERO(&fds);
    FD_SET(camera->fd, &fds);
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;

    ret = select(camera->fd + 1, &fds, NULL, NULL, &tv);
    if (ret <= 0)
    {
        fprintf(stderr, "%s: capture timeout\n", camera->path);
        return -1;
    }

    memset(buf, 0, sizeof(*buf));
    buf->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf->memory = V4L2_MEMORY_MMAP;
    if (xioctl(camera->fd, VIDIOC_DQBUF, buf) < 0)
    {
        fprintf(stderr, "%s: VIDIOC_DQBUF failed: %s\n", camera->path, strerror(errno));
        return -1;
    }

    return 0;
}

static int camera_requeue(Camera *camera, struct v4l2_buffer *buf)
{
    if (xioctl(camera->fd, VIDIOC_QBUF, buf) < 0)
    {
        fprintf(stderr, "%s: VIDIOC_QBUF failed: %s\n", camera->path, strerror(errno));
        return -1;
    }

    return 0;
}

static vx_status fit_uyvy_from_uyvy(vx_image image,
                                    const Camera *camera,
                                    const uint8_t *src)
{
    vx_status status;
    vx_rectangle_t rect;
    vx_imagepatch_addressing_t addr;
    vx_map_id map_id;
    uint8_t *base = NULL;
    uint32_t output_row[IN_WIDTH / 2u];
    uint32_t y;

    rect.start_x = 0;
    rect.start_y = 0;
    rect.end_x = IN_WIDTH;
    rect.end_y = IN_HEIGHT;

    status = vxMapImagePatch(image, &rect, 0, &map_id, &addr, (void **)&base,
                             VX_WRITE_ONLY, VX_MEMORY_TYPE_HOST, VX_NOGAP_X);
    if (status != VX_SUCCESS)
    {
        return status;
    }

    if (addr.stride_x != 2)
    {
        vxUnmapImagePatch(image, map_id);
        return VX_ERROR_NOT_SUPPORTED;
    }

    for (y = 0; y < IN_HEIGHT; y++)
    {
        uint8_t *dst_row = base + (y * addr.stride_y);
        uint32_t output_y;
        uint32_t source_y;
        uint32_t x;

        if (y < camera->output_y)
        {
            output_y = 0;
        }
        else if (y >= (camera->output_y + camera->output_height))
        {
            output_y = camera->output_height - 1u;
        }
        else
        {
            output_y = y - camera->output_y;
        }
        source_y = camera->source_y_for_line[output_y];

        for (x = 0; x < camera->output_width; x += 2u)
        {
            uint32_t source_x = camera->source_x_for_pair[x / 2u];
            const uint8_t *src_pair = src + (source_y * camera->stride) +
                                      (source_x * 2u);
            uint32_t pair;

            memcpy(&pair, src_pair, sizeof(pair));

            if (camera->mirror_x != 0)
            {
                pair = (pair & 0x00ff00ffu) |
                       ((pair & 0x0000ff00u) << 16u) |
                       ((pair & 0xff000000u) >> 16u);
            }
            output_row[(camera->output_x + x) / 2u] = pair;
        }

        /* Extend edge pixels into aspect-ratio padding. This retains the
         * complete camera field of view without exposing black source rows
         * when the calibrated projection reaches just beyond that view. */
        for (x = 0; x < camera->output_x; x += 2u)
        {
            output_row[x / 2u] = output_row[camera->output_x / 2u];
        }
        for (x = camera->output_x + camera->output_width;
             x < IN_WIDTH; x += 2u)
        {
            output_row[x / 2u] =
                output_row[(camera->output_x + camera->output_width - 2u) / 2u];
        }

        memcpy(dst_row, output_row, IN_WIDTH * 2u);
    }

    return vxUnmapImagePatch(image, map_id);
}

typedef struct {
    Camera *camera;
    vx_image image;
    vx_status status;
    double capture_seconds;
    double convert_seconds;
} CaptureWorker;

static void *capture_worker(void *argument)
{
    CaptureWorker *worker = (CaptureWorker *)argument;
    struct v4l2_buffer buf;
    double stage_start = now_seconds();

    worker->status = VX_FAILURE;
    if (camera_dequeue(worker->camera, &buf, 1000) != 0)
    {
        return NULL;
    }
    worker->capture_seconds = now_seconds() - stage_start;

    stage_start = now_seconds();
    worker->status = fit_uyvy_from_uyvy(
        worker->image, worker->camera,
        (const uint8_t *)worker->camera->buffers[buf.index].start);
    worker->convert_seconds = now_seconds() - stage_start;

    if (camera_requeue(worker->camera, &buf) != 0)
    {
        worker->status = VX_FAILURE;
    }
    return NULL;
}

static int make_calibration_path(char *path, size_t path_size,
                                 const char *filename)
{
    const char *data_root = getenv("VX_TEST_DATA_PATH");
    int length;

    if ((data_root == NULL) || (data_root[0] == '\0'))
    {
        data_root = ".";
    }
    length = snprintf(path, path_size, "%s/psdkra/srv/srv_app/%s",
                      data_root, filename);
    return ((length >= 0) && ((size_t)length < path_size)) ? 0 : -1;
}

static int read_calmat(svCalmat_t *calmat)
{
    char path[512];
    FILE *fp;
    uint32_t camera;

    memset(calmat, 0, sizeof(*calmat));
    if (make_calibration_path(path, sizeof(path), "CALMAT.BIN") != 0)
    {
        return -1;
    }
    fp = fopen(path, "rb");
    if (fp == NULL)
    {
        fprintf(stderr, "jk_srv_live: cannot open %s: %s\n",
                path, strerror(errno));
        return -1;
    }

    if ((fread(&calmat->numCameras, 1, sizeof(calmat->numCameras), fp) !=
         sizeof(calmat->numCameras)) ||
        (calmat->numCameras != (int32_t)NUM_CAMERAS))
    {
        fprintf(stderr, "jk_srv_live: invalid camera count in %s\n", path);
        fclose(fp);
        return -1;
    }
    for (camera = 0; camera < NUM_CAMERAS; camera++)
    {
        if ((fread(&calmat->calMatSize[camera], 1,
                   sizeof(calmat->calMatSize[camera]), fp) !=
             sizeof(calmat->calMatSize[camera])) ||
            (calmat->calMatSize[camera] != 48))
        {
            fprintf(stderr, "jk_srv_live: invalid camera %u matrix in %s\n",
                    camera, path);
            fclose(fp);
            return -1;
        }
    }
    if (fseek(fp, 128, SEEK_SET) != 0)
    {
        fclose(fp);
        return -1;
    }
    for (camera = 0; camera < NUM_CAMERAS; camera++)
    {
        uint8_t *destination =
            ((uint8_t *)calmat->calMatBuf) + (camera * 48u);
        if (fread(destination, 1, 48u, fp) != 48u)
        {
            fprintf(stderr, "jk_srv_live: truncated matrix data in %s\n", path);
            fclose(fp);
            return -1;
        }
    }
    fclose(fp);
    printf("jk_srv_live: loaded %s\n", path);
    return 0;
}

static int read_lens(ldc_lensParameters *lens)
{
    char path[512];
    FILE *fp;

    memset(lens, 0, sizeof(*lens));
    if (make_calibration_path(path, sizeof(path), "LENS.BIN") != 0)
    {
        return -1;
    }
    fp = fopen(path, "rb");
    if (fp == NULL)
    {
        fprintf(stderr, "jk_srv_live: cannot open %s: %s\n",
                path, strerror(errno));
        return -1;
    }
    if (fread(lens, 1, sizeof(*lens), fp) != sizeof(*lens))
    {
        fprintf(stderr, "jk_srv_live: invalid lens data in %s\n", path);
        fclose(fp);
        return -1;
    }
    fclose(fp);
    if ((lens->ldcLUT_numCams < (int32_t)NUM_CAMERAS) ||
        (lens->ldcLUT_D2U_length <= 0) ||
        (lens->ldcLUT_D2U_length > LDC_D2U_TABLE_MAX_LENGTH) ||
        (lens->ldcLUT_U2D_length <= 0) ||
        (lens->ldcLUT_U2D_length > LDC_U2D_TABLE_MAX_LENGTH) ||
        (lens->ldcLUT_focalLength <= 0.0f))
    {
        fprintf(stderr, "jk_srv_live: unsupported lens parameters in %s\n",
                path);
        return -1;
    }
    printf("jk_srv_live: loaded %s\n", path);
    return 0;
}

static void initialize_ldc(LensDistortionCorrection *ldc,
                           const ldc_lensParameters *lens, uint32_t camera)
{
    memset(ldc, 0, sizeof(*ldc));
    ldc->distCenterX = lens->ldcLUT_distortionCenters[camera * 2u];
    ldc->distCenterY = lens->ldcLUT_distortionCenters[camera * 2u + 1u];
    ldc->distFocalLength = lens->ldcLUT_focalLength;
    ldc->distFocalLengthInv = 1.0f / ldc->distFocalLength;
    ldc->lut_d2u_indMax = lens->ldcLUT_D2U_length - 1;
    ldc->lut_d2u_step = lens->ldcLUT_D2U_step;
    ldc->lut_d2u_stepInv = 1.0f / ldc->lut_d2u_step;
    ldc->lut_u2d_indMax = lens->ldcLUT_U2D_length - 1;
    ldc->lut_u2d_step = lens->ldcLUT_U2D_step;
    ldc->lut_u2d_stepInv = 1.0f / ldc->lut_u2d_step;
    memcpy(ldc->lut_d2u, lens->ldcLUT_D2U_table, sizeof(ldc->lut_d2u));
    memcpy(ldc->lut_u2d, lens->ldcLUT_U2D_table, sizeof(ldc->lut_u2d));
}

static float positive_env_float(const char *name)
{
    const char *text = getenv(name);
    char *end = NULL;
    float value;

    if ((text == NULL) || (text[0] == '\0'))
    {
        return 0.0f;
    }
    errno = 0;
    value = strtof(text, &end);
    if ((errno != 0) || (end == text) || (*end != '\0') ||
        !isfinite(value) || (value <= 0.0f))
    {
        fprintf(stderr, "jk_srv_live: ignoring invalid %s=%s\n", name, text);
        return 0.0f;
    }
    return value;
}

static void set_equisolid_focal(LensDistortionCorrection *ldc, float focal)
{
    int32_t index;

    ldc->distFocalLength = focal;
    ldc->distFocalLengthInv = 1.0f / focal;
    for (index = 0; index <= ldc->lut_u2d_indMax; index++)
    {
        float theta = (float)index * ldc->lut_u2d_step;
        ldc->lut_u2d[index] = 2.0f * focal * sinf(theta * 0.5f);
    }
}

static void rescale_bowl(float *bowl_xyz,
                         const svACCalmatStruct_t *calmat,
                         float requested_step,
                         float requested_origin_x,
                         float requested_origin_y)
{
    float camera_x[NUM_CAMERAS];
    float camera_y[NUM_CAMERAS];
    float origin_x = 0.0f;
    float origin_y = 0.0f;
    float generated_step;
    float scale;
    uint32_t camera;
    uint32_t entry;

    if (requested_step <= 0.0f)
    {
        return;
    }
    for (camera = 0; camera < NUM_CAMERAS; camera++)
    {
        const float *matrix = &calmat->scaled_outcalmat[camera * 12u];
        camera_x[camera] = -(matrix[0] * matrix[9] +
                             matrix[1] * matrix[10] +
                             matrix[2] * matrix[11]);
        camera_y[camera] = -(matrix[3] * matrix[9] +
                             matrix[4] * matrix[10] +
                             matrix[5] * matrix[11]);
        origin_x += camera_x[camera] / (float)NUM_CAMERAS;
        origin_y += camera_y[camera] / (float)NUM_CAMERAS;
    }
    generated_step = hypotf(camera_x[0] - camera_x[2],
                            camera_y[0] - camera_y[2]) / 100.0f;
    if (generated_step <= 0.0f)
    {
        return;
    }
    if (requested_origin_x <= 0.0f)
    {
        requested_origin_x = origin_x;
    }
    if (requested_origin_y <= 0.0f)
    {
        requested_origin_y = origin_y;
    }
    scale = requested_step / generated_step;
    for (entry = 0; entry < (SV_XYZLUT3D_SIZE / 3u); entry++)
    {
        float *xyz = &bowl_xyz[entry * 3u];
        xyz[0] = requested_origin_x + ((xyz[0] - origin_x) * scale);
        xyz[1] = requested_origin_y + ((xyz[1] - origin_y) * scale);
        xyz[2] *= scale;
    }
    printf("jk_srv_live: bowl scale %.3f -> %.3f mm/pixel (x%.3f), "
           "origin %.1f,%.1f -> %.1f,%.1f\n",
           generated_step, requested_step, scale, origin_x, origin_y,
           requested_origin_x, requested_origin_y);
}

static vx_array create_calibrated_lut(vx_context context)
{
    vx_array lut = NULL;
    svGpuLutGen_t config;
    svACCalmatStruct_t scaled_calmat;
    svGeometric_t offset;
    svLdcLut_t lens_luts;
    svCalmat_t calmat_file;
    ldc_lensParameters lens_file;
    tivxGenerateGpulutParams generate_params;
    float *bowl_xyz = NULL;
    uint16_t *gpu_lut = NULL;
    vx_status status = VX_SUCCESS;
    uint32_t camera;
    uint32_t element;
    int32_t lut_items = 0;
    double start_seconds;
    float gmsl_focal;
    float analog_focal;
    float requested_step;
    float requested_origin_x;
    float requested_origin_y;

    if ((read_calmat(&calmat_file) != 0) || (read_lens(&lens_file) != 0))
    {
        return NULL;
    }

    memset(&config, 0, sizeof(config));
    config.SVInCamFrmHeight = IN_HEIGHT;
    config.SVInCamFrmWidth = IN_WIDTH;
    config.SVOutDisplayHeight = SV_LUT_HEIGHT;
    config.SVOutDisplayWidth = SV_LUT_WIDTH;
    config.numCameras = NUM_CAMERAS;
    config.subsampleratio = SV_SUBSAMPLE;
    config.useWideBowl = 1;

    memset(&scaled_calmat, 0, sizeof(scaled_calmat));
    for (camera = 0; camera < NUM_CAMERAS; camera++)
    {
        for (element = 0; element < 9u; element++)
        {
            scaled_calmat.scaled_outcalmat[camera * 12u + element] =
                (float)calmat_file.calMatBuf[camera * 12u + element] /
                1073741824.0f;
        }
        for (; element < 12u; element++)
        {
            scaled_calmat.scaled_outcalmat[camera * 12u + element] =
                (float)calmat_file.calMatBuf[camera * 12u + element] /
                1024.0f;
        }
    }

    memset(&offset, 0, sizeof(offset));
    offset.offsetXleft = -400;
    offset.offsetXright = 400;
    offset.offsetYfront = -450;
    offset.offsetYback = 450;

    memset(&lens_luts, 0, sizeof(lens_luts));
    for (camera = 0; camera < NUM_CAMERAS; camera++)
    {
        initialize_ldc(&lens_luts.ldc[camera], &lens_file, camera);
    }
    gmsl_focal = positive_env_float("APP_SRV_GMSL_FOCAL");
    analog_focal = positive_env_float("APP_SRV_ANALOG_FOCAL");
    if (gmsl_focal > 0.0f)
    {
        set_equisolid_focal(&lens_luts.ldc[0], gmsl_focal);
        set_equisolid_focal(&lens_luts.ldc[3], gmsl_focal);
    }
    if (analog_focal > 0.0f)
    {
        set_equisolid_focal(&lens_luts.ldc[1], analog_focal);
        set_equisolid_focal(&lens_luts.ldc[2], analog_focal);
    }
    if ((gmsl_focal > 0.0f) || (analog_focal > 0.0f))
    {
        printf("jk_srv_live: mixed equisolid focal lengths GMSL=%.1f analog=%.1f\n",
               lens_luts.ldc[0].distFocalLength,
               lens_luts.ldc[1].distFocalLength);
    }

    bowl_xyz = (float *)calloc(SV_XYZLUT3D_SIZE, sizeof(*bowl_xyz));
    gpu_lut = (uint16_t *)calloc(SV_GPULUT_SIZE, sizeof(*gpu_lut));
    memset(&generate_params, 0, sizeof(generate_params));
    generate_params.buf_GLUT3d_undist_size =
        (1u + (SV_LUT_WIDTH / (2u * SV_SUBSAMPLE))) *
        4u * 2u * sizeof(int16_t);
    generate_params.buf_GLUT3d_undist_ptr =
        (float *)calloc(1, generate_params.buf_GLUT3d_undist_size);
    if ((bowl_xyz == NULL) || (gpu_lut == NULL) ||
        (generate_params.buf_GLUT3d_undist_ptr == NULL))
    {
        fprintf(stderr, "jk_srv_live: calibrated LUT allocation failed\n");
        status = VX_ERROR_NO_MEMORY;
        goto cleanup;
    }

    start_seconds = now_seconds();
    printf("jk_srv_live: generating TI calibrated bowl LUT on A53\n");
    svGenerate_3D_Bowl(&config, &offset,
                       scaled_calmat.scaled_outcalmat, bowl_xyz);
    requested_step = positive_env_float("APP_SRV_MM_PER_LUT_PIXEL");
    requested_origin_x = positive_env_float("APP_SRV_ORIGIN_X");
    requested_origin_y = positive_env_float("APP_SRV_ORIGIN_Y");
    rescale_bowl(bowl_xyz, &scaled_calmat, requested_step,
                 requested_origin_x, requested_origin_y);
    svGenerate_3D_GPULUT(&config, &lens_luts, &generate_params,
                        &scaled_calmat, bowl_xyz, gpu_lut, &lut_items);
    if ((lut_items <= 0) || ((uint32_t)lut_items > SV_GPULUT_SIZE))
    {
        fprintf(stderr, "jk_srv_live: TI LUT generator returned %d items\n",
                lut_items);
        status = VX_FAILURE;
        goto cleanup;
    }

    lut = vxCreateArray(context, VX_TYPE_UINT16, SV_GPULUT_SIZE);
    if (object_status((vx_reference)lut) != VX_SUCCESS)
    {
        status = VX_FAILURE;
        goto cleanup;
    }
    status = vxAddArrayItems(lut, (vx_size)lut_items, gpu_lut,
                             sizeof(*gpu_lut));
    if (status == VX_SUCCESS)
        printf("jk_srv_live: calibrated GPU LUT ready (%d uint16 items, %.3f s)\n",
               lut_items, now_seconds() - start_seconds);

cleanup:
    free(generate_params.buf_GLUT3d_undist_ptr);
    free(gpu_lut);
    free(bowl_xyz);
    if ((status != VX_SUCCESS) && (lut != NULL))
    {
        fprintf(stderr, "jk_srv_live: calibrated LUT generation failed: %d\n",
                status);
        vxReleaseArray(&lut);
    }
    return lut;
}

static vx_array create_uncalibrated_lut(vx_context context)
{
    const uint32_t entries = QUADRANTS * QUADRANT_SIZE;
    const vx_size uint16_items = (entries * sizeof(srv_lut_t)) / sizeof(vx_uint16);
    srv_lut_t *lut;
    vx_array array;
    vx_status status;
    uint32_t quadrant;

    if ((sizeof(srv_lut_t) % sizeof(vx_uint16)) != 0u)
    {
        return NULL;
    }

    lut = (srv_lut_t *)calloc(entries, sizeof(*lut));
    if (lut == NULL)
    {
        return NULL;
    }

    for (quadrant = 0; quadrant < QUADRANTS; quadrant++)
    {
        const int is_left = ((quadrant == 0u) || (quadrant == 3u));
        const int is_top = (quadrant < 2u);
        uint32_t row;

        for (row = 0; row < QUADRANT_HEIGHT; row++)
        {
            uint32_t column;
            for (column = 0; column < QUADRANT_WIDTH; column++)
            {
                srv_lut_t *entry = &lut[(quadrant * QUADRANT_SIZE) +
                                        (row * QUADRANT_WIDTH) + column];
                uint32_t source_x1 = (column * (IN_WIDTH - 1u)) /
                                     (QUADRANT_WIDTH - 1u);
                uint32_t source_y1 = (row * (IN_HEIGHT - 1u)) /
                                     (QUADRANT_HEIGHT - 1u);
                uint32_t source_x2 = (column * (IN_WIDTH - 1u)) /
                                     (QUADRANT_WIDTH - 1u);
                uint32_t source_y2 = (row * (IN_HEIGHT - 1u)) /
                                     (QUADRANT_HEIGHT - 1u);

                entry->x = (GL_VERTEX_DATATYPE)(is_left
                    ? ((int32_t)(column * POINTS_SUBX) - (POINTS_WIDTH / 2))
                    : ((int32_t)(column * POINTS_SUBX) - POINTS_SUBX));
                entry->y = (GL_VERTEX_DATATYPE)(is_top
                    ? ((POINTS_HEIGHT / 2) - (int32_t)(row * POINTS_SUBY))
                    : (POINTS_SUBY - (int32_t)(row * POINTS_SUBY)));
                entry->z = 0;
                entry->u1 = (GL_TEXCOORD_DATATYPE)(source_y1 * 16u);
                entry->v1 = (GL_TEXCOORD_DATATYPE)(source_x1 * 16u);
                entry->u2 = (GL_TEXCOORD_DATATYPE)(source_y2 * 16u);
                entry->v2 = (GL_TEXCOORD_DATATYPE)(source_x2 * 16u);
            }
        }
    }

    array = vxCreateArray(context, VX_TYPE_UINT16, uint16_items);
    if (object_status((vx_reference)array) == VX_SUCCESS)
    {
        status = vxAddArrayItems(array, uint16_items, lut, sizeof(vx_uint16));
    }
    else
    {
        status = VX_FAILURE;
    }
    free(lut);

    if (status != VX_SUCCESS)
    {
        vxReleaseArray(&array);
        return NULL;
    }

    return array;
}

static vx_status write_image_raw(const char *path, vx_image image)
{
    vx_status status;
    vx_uint32 width = 0;
    vx_uint32 height = 0;
    vx_size planes = 0;
    vx_uint32 plane;
    FILE *fp;

    status = vxQueryImage(image, VX_IMAGE_WIDTH, &width, sizeof(width));
    if (status == VX_SUCCESS)
    {
        status = vxQueryImage(image, VX_IMAGE_HEIGHT, &height, sizeof(height));
    }
    if (status == VX_SUCCESS)
    {
        status = vxQueryImage(image, VX_IMAGE_PLANES, &planes, sizeof(planes));
    }
    if (status != VX_SUCCESS)
    {
        return status;
    }

    fp = fopen(path, "wb");
    if (fp == NULL)
    {
        perror(path);
        return VX_FAILURE;
    }

    for (plane = 0; plane < planes; plane++)
    {
        vx_rectangle_t rect;
        vx_imagepatch_addressing_t addr;
        vx_map_id map_id;
        void *data_ptr = NULL;

        rect.start_x = 0;
        rect.start_y = 0;
        rect.end_x = width;
        rect.end_y = height;

        status = vxMapImagePatch(image, &rect, plane, &map_id, &addr, &data_ptr,
                                 VX_READ_ONLY, VX_MEMORY_TYPE_HOST, VX_NOGAP_X);
        if (status != VX_SUCCESS)
        {
            break;
        }
        else
        {
            uint32_t y;
            uint8_t *base = (uint8_t *)data_ptr;
            uint32_t rows = addr.dim_y / addr.step_y;
            uint32_t bytes_per_row = (addr.dim_x * addr.stride_x) / addr.step_x;

            for (y = 0; y < rows; y++)
            {
                if (fwrite(base + (y * addr.stride_y), 1, bytes_per_row, fp) != bytes_per_row)
                {
                    status = VX_FAILURE;
                    break;
                }
            }

            vxUnmapImagePatch(image, map_id);
        }

        if (status != VX_SUCCESS)
        {
            break;
        }
    }

    fclose(fp);
    return status;
}

static vx_status write_image_nv12(const char *path, vx_image image)
{
    vx_status status;
    vx_uint32 width = 0;
    vx_uint32 height = 0;
    vx_df_image format = 0;
    vx_rectangle_t rect;
    vx_imagepatch_addressing_t addr;
    vx_map_id map_id;
    uint8_t *base = NULL;
    uint8_t *nv12 = NULL;
    size_t y_plane_size;
    size_t output_size;
    FILE *fp = NULL;
    uint32_t x;
    uint32_t y;

    status = vxQueryImage(image, VX_IMAGE_WIDTH, &width, sizeof(width));
    if (status == VX_SUCCESS)
    {
        status = vxQueryImage(image, VX_IMAGE_HEIGHT, &height, sizeof(height));
    }
    if (status == VX_SUCCESS)
    {
        status = vxQueryImage(image, VX_IMAGE_FORMAT, &format, sizeof(format));
    }
    if ((status != VX_SUCCESS) || (format != VX_DF_IMAGE_UYVY) ||
        ((width & 1u) != 0u) || ((height & 1u) != 0u))
    {
        return VX_ERROR_INVALID_FORMAT;
    }

    y_plane_size = (size_t)width * height;
    output_size = y_plane_size + (y_plane_size / 2u);
    nv12 = (uint8_t *)malloc(output_size);
    if (nv12 == NULL)
    {
        return VX_ERROR_NO_MEMORY;
    }

    rect.start_x = 0;
    rect.start_y = 0;
    rect.end_x = width;
    rect.end_y = height;
    status = vxMapImagePatch(image, &rect, 0, &map_id, &addr, (void **)&base,
                             VX_READ_ONLY, VX_MEMORY_TYPE_HOST, VX_NOGAP_X);
    if (status != VX_SUCCESS)
    {
        free(nv12);
        return status;
    }

    if (addr.stride_x != 2)
    {
        status = VX_ERROR_NOT_SUPPORTED;
    }
    else
    {
        for (y = 0; y < height; y++)
        {
            const uint8_t *src_row = base + (y * addr.stride_y);
            uint8_t *dst_y = nv12 + ((size_t)y * width);

            for (x = 0; x < width; x += 2u)
            {
                const uint8_t *src = src_row + (x * 2u);
                dst_y[x] = src[1];
                dst_y[x + 1u] = src[3];
            }
        }

        for (y = 0; y < height; y += 2u)
        {
            const uint8_t *src_row0 = base + (y * addr.stride_y);
            const uint8_t *src_row1 = base + ((y + 1u) * addr.stride_y);
            uint8_t *dst_uv = nv12 + y_plane_size +
                              (((size_t)y / 2u) * width);

            for (x = 0; x < width; x += 2u)
            {
                const uint8_t *src0 = src_row0 + (x * 2u);
                const uint8_t *src1 = src_row1 + (x * 2u);
                dst_uv[x] = (uint8_t)(((uint32_t)src0[0] + src1[0] + 1u) / 2u);
                dst_uv[x + 1u] =
                    (uint8_t)(((uint32_t)src0[2] + src1[2] + 1u) / 2u);
            }
        }
    }

    vxUnmapImagePatch(image, map_id);

    if (status == VX_SUCCESS)
    {
        fp = fopen(path, "wb");
        if (fp == NULL)
        {
            perror(path);
            status = VX_FAILURE;
        }
        else if (fwrite(nv12, 1, output_size, fp) != output_size)
        {
            fprintf(stderr, "%s: incomplete write\n", path);
            status = VX_FAILURE;
        }
    }

    if (fp != NULL)
    {
        fclose(fp);
    }
    free(nv12);
    return status;
}

int main(int argc, char *argv[])
{
    const char *output_path = "/tmp/jk_srv_live_rgbx_1280x800.raw";
    const char *calibration_dir = getenv("APP_CALIB_CAPTURE_DIR");
    const char *calibration_frame_text = getenv("APP_CALIB_CAPTURE_FRAME");
    const char *use_calibration_text = getenv("APP_SRV_USE_CALIBRATION");
    const char *devices[NUM_CAMERAS];
    uint32_t frame_count = 0u;
    uint32_t calibration_frame = 30u;
    int calibration_written = 0;
    Camera cameras[NUM_CAMERAS];
    vx_context context = NULL;
    vx_graph graph = NULL;
    vx_node srv_node = NULL;
    vx_node display_node = NULL;
    vx_image exemplar = NULL;
    vx_image output = NULL;
    vx_object_array inputs = NULL;
    vx_object_array views = NULL;
    vx_array srv_lut = NULL;
    vx_user_data_object params_obj = NULL;
    vx_user_data_object view_obj = NULL;
    vx_user_data_object display_params_obj = NULL;
    vx_status status = VX_SUCCESS;
    tivx_srv_params_t params;
    srv_coords_t view;
    int app_initialized = 0;
    uint32_t i;
    uint32_t frame;
    double start_time;
    double end_time;
    double capture_seconds = 0.0;
    double convert_seconds = 0.0;
    double graph_seconds = 0.0;
    int use_calibration =
        ((use_calibration_text == NULL) ||
         (strcmp(use_calibration_text, "0") != 0));

    setvbuf(stdout, NULL, _IOLBF, 0);
    setvbuf(stderr, NULL, _IOLBF, 0);
    signal(SIGINT, request_stop);
    signal(SIGTERM, request_stop);

    memset(cameras, 0, sizeof(cameras));
    for (i = 0; i < NUM_CAMERAS; i++)
    {
        devices[i] = default_devices[i];
        cameras[i].fd = -1;
    }

    if (argc > 1)
    {
        frame_count = (uint32_t)strtoul(argv[1], NULL, 0);
    }
    if (argc > 2)
    {
        output_path = argv[2];
    }
    if (argc >= 7)
    {
        for (i = 0; i < NUM_CAMERAS; i++)
        {
            devices[i] = argv[3 + i];
        }
    }

    if ((calibration_frame_text != NULL) && (calibration_frame_text[0] != '\0'))
    {
        calibration_frame = (uint32_t)strtoul(calibration_frame_text, NULL, 0);
        if (calibration_frame == 0u)
        {
            calibration_frame = 1u;
        }
    }

    if (frame_count == 0u)
        printf("jk_srv_live: continuous output=%s\n", output_path);
    else
        printf("jk_srv_live: frames=%u output=%s\n", frame_count, output_path);
    printf("jk_srv_live: %s GPU LUT, camera order front/right/back/left\n",
           use_calibration ? "TI calibrated" : "identity quadrant");
    if ((calibration_dir != NULL) && (calibration_dir[0] != '\0'))
    {
        printf("jk_srv_live: calibration capture frame=%u directory=%s\n",
               calibration_frame, calibration_dir);
    }

    for (i = 0; i < NUM_CAMERAS; i++)
    {
        if (camera_open(&cameras[i], devices[i]) != 0)
        {
            status = VX_FAILURE;
            goto cleanup;
        }
    }

    if (appInit() != 0)
    {
        fprintf(stderr, "jk_srv_live: appInit failed\n");
        status = VX_FAILURE;
        goto cleanup;
    }
    app_initialized = 1;

    tivxPlatformResetObjDescTableInfo();

    context = vxCreateContext();
    if (object_status((vx_reference)context) != VX_SUCCESS)
    {
        fprintf(stderr, "jk_srv_live: vxCreateContext failed\n");
        status = VX_FAILURE;
        goto cleanup;
    }

    tivxSrvLoadKernels(context);
    tivxHwaLoadKernels(context);
    tivxVideoIOLoadKernels(context);

    exemplar = vxCreateImage(context, IN_WIDTH, IN_HEIGHT, VX_DF_IMAGE_UYVY);
    inputs = vxCreateObjectArray(context, (vx_reference)exemplar, NUM_CAMERAS);
    release_image(&exemplar);

    if (use_calibration != 0)
        srv_lut = create_calibrated_lut(context);
    else
        srv_lut = create_uncalibrated_lut(context);

    memset(&params, 0, sizeof(params));
    params.cam_bpp = 12u;
    params_obj = vxCreateUserDataObject(context, "tivx_srv_params_t", sizeof(params), &params);

    memset(&view, 0, sizeof(view));
    view.camz = 240.0f;
    view_obj = vxCreateUserDataObject(context, "srv_coords_t", sizeof(view), &view);
    views = vxCreateObjectArray(context, (vx_reference)view_obj, NUM_VIEWS);
    release_user_data_object(&view_obj);

    output = vxCreateImage(context, OUT_WIDTH, OUT_HEIGHT, VX_DF_IMAGE_RGBX);
    graph = vxCreateGraph(context);

    if ((status != VX_SUCCESS) || (inputs == NULL) || (views == NULL) ||
        (srv_lut == NULL) ||
        (params_obj == NULL) ||
        (output == NULL) || (graph == NULL))
    {
        status = VX_FAILURE;
        goto cleanup;
    }

    srv_node = tivxGlSrvNode(graph, params_obj, inputs, views,
                            srv_lut, output);
    if (object_status((vx_reference)srv_node) != VX_SUCCESS)
    {
        status = VX_FAILURE;
        goto cleanup;
    }

    status = vxSetNodeTarget(srv_node, VX_TARGET_STRING, TIVX_TARGET_MPU_0);
    if ((status == VX_SUCCESS) &&
        (tivxIsTargetEnabled(TIVX_TARGET_DISPLAY1) == vx_true_e))
    {
        tivx_display_params_t display_params;

        memset(&display_params, 0, sizeof(display_params));
        display_params.opMode = TIVX_KERNEL_DISPLAY_ZERO_BUFFER_COPY_MODE;
        display_params.pipeId = 0u;
        display_params.outWidth = OUT_WIDTH;
        display_params.outHeight = OUT_HEIGHT;
        display_params.posX = 0u;
        display_params.posY = 0u;
        display_params_obj = vxCreateUserDataObject(
            context, "tivx_display_params_t", sizeof(display_params),
            &display_params);
        display_node = tivxDisplayNode(graph, display_params_obj, output);
        if ((object_status((vx_reference)display_params_obj) != VX_SUCCESS) ||
            (object_status((vx_reference)display_node) != VX_SUCCESS))
        {
            fprintf(stderr, "jk_srv_live: display node creation failed\n");
            status = VX_FAILURE;
        }
        else
        {
            status = vxSetNodeTarget(
                display_node, VX_TARGET_STRING, TIVX_TARGET_DISPLAY1);
            printf("jk_srv_live: TI DISPLAY1 enabled at %ux%u\n",
                   OUT_WIDTH, OUT_HEIGHT);
        }
    }
    else if (status == VX_SUCCESS)
    {
        printf("jk_srv_live: TI DISPLAY1 target is not enabled\n");
    }
    if (status == VX_SUCCESS)
    {
        status = vxVerifyGraph(graph);
    }
    if (status != VX_SUCCESS)
    {
        fprintf(stderr, "jk_srv_live: vxVerifyGraph failed: %d\n", status);
        goto cleanup;
    }

    start_time = now_seconds();
    for (frame = 0; ((frame_count == 0u) || (frame < frame_count)) &&
                    !stop_requested; frame++)
    {
        CaptureWorker workers[NUM_CAMERAS];
        pthread_t threads[NUM_CAMERAS];
        uint32_t threads_started = 0u;

        memset(workers, 0, sizeof(workers));
        for (i = 0; i < NUM_CAMERAS; i++)
        {
            workers[i].camera = &cameras[i];
            workers[i].image = (vx_image)vxGetObjectArrayItem(inputs, i);
            if (object_status((vx_reference)workers[i].image) != VX_SUCCESS)
            {
                status = VX_FAILURE;
                break;
            }
            if (pthread_create(&threads[i], NULL, capture_worker, &workers[i]) != 0)
            {
                fprintf(stderr, "jk_srv_live: pthread_create failed for camera %u\n", i);
                status = VX_FAILURE;
                break;
            }
            threads_started++;
        }

        for (i = 0; i < threads_started; i++)
        {
            pthread_join(threads[i], NULL);
        }
        for (i = 0; i < NUM_CAMERAS; i++)
        {
            if (i < threads_started)
            {
                capture_seconds += workers[i].capture_seconds;
                convert_seconds += workers[i].convert_seconds;
                if (workers[i].status != VX_SUCCESS)
                {
                    status = workers[i].status;
                }
            }
        }
        if ((threads_started != NUM_CAMERAS) || (status != VX_SUCCESS))
        {
            for (i = 0; i < NUM_CAMERAS; i++)
            {
                release_image(&workers[i].image);
            }
            goto cleanup;
        }

        if ((calibration_dir != NULL) && (calibration_dir[0] != '\0') &&
            (calibration_written == 0) && ((frame + 1u) >= calibration_frame))
        {
            char path[512];

            for (i = 0; i < NUM_CAMERAS; i++)
            {
                snprintf(path, sizeof(path), "%s/%s", calibration_dir,
                         calibration_camera_names[i]);
                status = write_image_nv12(path, workers[i].image);
                if (status != VX_SUCCESS)
                {
                    fprintf(stderr, "jk_srv_live: failed to write %s: %d\n",
                            path, status);
                    break;
                }
                printf("jk_srv_live: wrote %s (640x480 NV12/420sp)\n", path);
            }
            if (status == VX_SUCCESS)
            {
                calibration_written = 1;
            }
        }

        for (i = 0; i < NUM_CAMERAS; i++)
        {
            release_image(&workers[i].image);
        }
        if (status != VX_SUCCESS)
        {
            goto cleanup;
        }

        {
            double stage_start = now_seconds();
            status = vxProcessGraph(graph);
            graph_seconds += now_seconds() - stage_start;
        }
        if (status != VX_SUCCESS)
        {
            fprintf(stderr, "jk_srv_live: vxProcessGraph failed on frame %u: %d\n",
                    frame, status);
            goto cleanup;
        }

        if (((frame + 1u) % 30u) == 0u)
        {
            double elapsed = now_seconds() - start_time;
            printf("jk_srv_live: frame %u/%u %.2f fps\n",
                   frame + 1u, frame_count, (double)(frame + 1u) / elapsed);
        }
    }
    end_time = now_seconds();

    if ((calibration_dir != NULL) && (calibration_dir[0] != '\0') &&
        (calibration_written == 0))
    {
        fprintf(stderr,
                "jk_srv_live: stopped before calibration frame %u was captured\n",
                calibration_frame);
        status = VX_FAILURE;
        goto cleanup;
    }

    status = write_image_raw(output_path, output);
    if (status == VX_SUCCESS)
    {
        printf("jk_srv_live: wrote %s (%ux%u RGBX raw)\n",
               output_path, OUT_WIDTH, OUT_HEIGHT);
        printf("jk_srv_live: processed %u frames in %.3f s = %.2f fps\n",
               frame, end_time - start_time,
               (double)frame / (end_time - start_time));
        printf("jk_srv_live: capture %.3f s, convert %.3f s, SRV graph %.3f s\n",
               capture_seconds, convert_seconds, graph_seconds);
    }

cleanup:
    if (display_node != NULL)
    {
        vxReleaseNode(&display_node);
    }
    if (srv_node != NULL)
    {
        vxReleaseNode(&srv_node);
    }
    if (graph != NULL)
    {
        vxReleaseGraph(&graph);
    }
    release_image(&output);
    release_user_data_object(&display_params_obj);
    release_user_data_object(&params_obj);
    if (srv_lut != NULL)
    {
        vxReleaseArray(&srv_lut);
    }
    release_object_array(&views);
    release_object_array(&inputs);

    if (context != NULL)
    {
        tivxVideoIOUnLoadKernels(context);
        tivxHwaUnLoadKernels(context);
        tivxSrvUnLoadKernels(context);
        vxReleaseContext(&context);
    }

    if (app_initialized != 0)
    {
        appDeInit();
    }

    for (i = 0; i < NUM_CAMERAS; i++)
    {
        camera_close(&cameras[i]);
    }

    if (status == VX_SUCCESS)
    {
        return 0;
    }

    fprintf(stderr, "jk_srv_live: failed with vx_status=%d\n", status);
    return 1;
}
