/*
 * Live V4L2 smoke test for TI's SRV GPU OpenVX node on J722S.
 *
 * This is an intentionally simple bring-up app. It captures four UYVY V4L2
 * devices, copies a centered 640x480 crop into OpenVX images, runs
 * tivxGlSrvNode(), and writes the final RGBX output frame to disk.
 */

#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
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

#define IN_WIDTH      (640u)
#define IN_HEIGHT     (480u)
#define OUT_WIDTH     (1280u)
#define OUT_HEIGHT    (800u)
#define NUM_CAMERAS   (4u)
#define NUM_VIEWS     (1u)
#define CAP_BUFFERS   (4u)

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
    uint32_t copy_width;
    uint32_t copy_height;
    uint32_t source_x;
    uint32_t source_y;
    int stacked_fields;
} Camera;

static const char *default_devices[NUM_CAMERAS] = {
    "/usr/local/Ahsoka/devices/video/gmsl0",
    "/usr/local/Ahsoka/devices/video/gmsl1",
    "/usr/local/Ahsoka/devices/video/analog0",
    "/usr/local/Ahsoka/devices/video/analog1",
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

    camera->copy_width = camera->width < IN_WIDTH ? camera->width : IN_WIDTH;
    camera->copy_width &= ~1u;
    camera->copy_height = camera->height < IN_HEIGHT ? camera->height : IN_HEIGHT;
    camera->source_x = ((camera->width - camera->copy_width) / 2u) & ~1u;
    camera->source_y = (camera->height - camera->copy_height) / 2u;
    camera->stacked_fields = strstr(path, "analog") != NULL;

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

static vx_status fill_uyvy_from_uyvy(vx_image image,
                                     const Camera *camera,
                                     const uint8_t *src)
{
    vx_status status;
    vx_rectangle_t rect;
    vx_imagepatch_addressing_t addr;
    vx_map_id map_id;
    uint8_t *base = NULL;
    uint32_t y;

    rect.start_x = 0;
    rect.start_y = 0;
    rect.end_x = camera->copy_width;
    rect.end_y = camera->copy_height;

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

    for (y = 0; y < camera->copy_height; y++)
    {
        uint32_t source_y = camera->source_y + y;

        if (camera->stacked_fields != 0)
        {
            source_y = camera->source_y + (y / 2u);
            if ((y & 1u) != 0u)
            {
                source_y += camera->copy_height / 2u;
            }
        }
        const uint8_t *src_row = src +
            (source_y * camera->stride) + (camera->source_x * 2u);
        uint8_t *dst_row = base + (y * addr.stride_y);
        memcpy(dst_row, src_row, camera->copy_width * 2u);
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
    worker->status = fill_uyvy_from_uyvy(
        worker->image, worker->camera,
        (const uint8_t *)worker->camera->buffers[buf.index].start);
    worker->convert_seconds = now_seconds() - stage_start;

    if (camera_requeue(worker->camera, &buf) != 0)
    {
        worker->status = VX_FAILURE;
    }
    return NULL;
}

static vx_array create_uncalibrated_lut(vx_context context,
                                        const Camera cameras[NUM_CAMERAS])
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
        const uint32_t texture1 = quadrant;
        const uint32_t texture2 = texture1;
        uint32_t row;

        for (row = 0; row < QUADRANT_HEIGHT; row++)
        {
            uint32_t column;
            for (column = 0; column < QUADRANT_WIDTH; column++)
            {
                srv_lut_t *entry = &lut[(quadrant * QUADRANT_SIZE) +
                                        (row * QUADRANT_WIDTH) + column];
                uint32_t source_x1 = (column * (cameras[texture1].copy_width - 1u)) /
                                     (QUADRANT_WIDTH - 1u);
                uint32_t source_y1 = (row * (cameras[texture1].copy_height - 1u)) /
                                     (QUADRANT_HEIGHT - 1u);
                uint32_t source_x2 = (column * (cameras[texture2].copy_width - 1u)) /
                                     (QUADRANT_WIDTH - 1u);
                uint32_t source_y2 = (row * (cameras[texture2].copy_height - 1u)) /
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

int main(int argc, char *argv[])
{
    const char *output_path = "/tmp/jk_srv_live_rgbx_1280x800.raw";
    const char *devices[NUM_CAMERAS];
    uint32_t frame_count = 0u;
    Camera cameras[NUM_CAMERAS];
    vx_context context = NULL;
    vx_graph graph = NULL;
    vx_node srv_node = NULL;
    vx_node display_node = NULL;
    vx_image exemplar = NULL;
    vx_image output = NULL;
    vx_object_array inputs = NULL;
    vx_object_array views = NULL;
    vx_array uncalibrated_lut = NULL;
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

    if (frame_count == 0u)
        printf("jk_srv_live: continuous output=%s\n", output_path);
    else
        printf("jk_srv_live: frames=%u output=%s\n", frame_count, output_path);

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

    uncalibrated_lut = create_uncalibrated_lut(context, cameras);

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
        (uncalibrated_lut == NULL) ||
        (params_obj == NULL) ||
        (output == NULL) || (graph == NULL))
    {
        status = VX_FAILURE;
        goto cleanup;
    }

    srv_node = tivxGlSrvNode(graph, params_obj, inputs, views,
                            uncalibrated_lut, output);
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
            release_image(&workers[i].image);
        }
        if ((threads_started != NUM_CAMERAS) || (status != VX_SUCCESS))
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
    if (uncalibrated_lut != NULL)
    {
        vxReleaseArray(&uncalibrated_lut);
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
