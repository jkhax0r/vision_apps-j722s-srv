ifeq ($(TARGET_CPU),$(filter $(TARGET_CPU), x86_64 A72 A53))
ifeq ($(TARGET_OS),$(filter $(TARGET_OS), LINUX QNX))

include $(PRELUDE)

TARGET      := vx_app_jk_srv_live
TARGETTYPE  := exe
CSOURCES    := $(call all-c-files)

ifeq ($(TARGET_CPU),$(filter $(TARGET_CPU), A72 A53))

include $(VISION_APPS_PATH)/apps/concerto_mpu_inc.mak

ifeq ($(TARGET_OS), $(filter $(TARGET_OS), LINUX))
CFLAGS      += -DEGL_NO_X11
SYS_SHARED_LIBS += gbm
endif

ifeq ($(TARGET_OS),QNX)
SYS_SHARED_LIBS += screen
endif

endif

ifeq ($(TARGET_CPU),x86_64)
include $(VISION_APPS_PATH)/apps/concerto_x86_64_inc.mak
SKIPBUILD=1
endif

IDIRS += $(VISION_APPS_APPLIBS_IDIRS)
IDIRS += $(VISION_APPS_SRV_IDIRS)
IDIRS += $(VISION_APPS_PATH)/kernels/srv/host
IDIRS += $(VISION_APPS_PATH)
IDIRS += $(VXLIB_PATH)/packages
IDIRS += $(VXLIB_PATH)/packages/ti/vxlib/src/common/c6xsim

DEFS += HOST_EMULATION _HOST_BUILD _TMS320C6600 TMS320C66X LITTLE_ENDIAN_HOST
CFLAGS += -Wno-strict-aliasing -Wno-unused-variable
# TI's C6x host simulator predates current GCC diagnostics. Keep warnings as
# errors for the application while downgrading only diagnostics in that code.
CFLAGS += -Wno-error=uninitialized -Wno-error=parentheses
CFLAGS += -Wno-error=int-in-bool-context -Wno-error=unknown-pragmas

STATIC_LIBS += $(VISION_APPS_OPENGL_UTILS_LIBS)
STATIC_LIBS += $(VISION_APPS_SRV_LIBS)

SYS_SHARED_LIBS += EGL
SYS_SHARED_LIBS += GLESv2

ifeq ($(SOC),j722s)
SKIPBUILD=0
endif

include $(FINALE)

endif
endif
