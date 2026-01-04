# Planetary Neuron - CMake Build (Zephyr or Telink SDK)
cmake_minimum_required(VERSION 3.20)

# Option: Build with Zephyr RTOS or bare-metal Telink SDK
option(USE_ZEPHYR "Build with Zephyr RTOS" OFF)

if(USE_ZEPHYR)
    # Zephyr build
    find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
    project(planetary-neuron LANGUAGES C CXX)
else()
    # Bare-metal Telink SDK build
    project(planetary-neuron LANGUAGES C CXX ASM)

    set(CMAKE_C_STANDARD 11)
    set(CMAKE_CXX_STANDARD 17)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)

    # TLSR8258 toolchain (Telink's modified GCC)
    set(TELINK_SDK_PATH "$ENV{TELINK_SDK}" CACHE PATH "Path to Telink SDK")
    set(CMAKE_C_COMPILER "${TELINK_SDK_PATH}/tools/tc32/bin/tc32-elf-gcc")
    set(CMAKE_CXX_COMPILER "${TELINK_SDK_PATH}/tools/tc32/bin/tc32-elf-g++")

    # Chip-specific flags
    add_compile_options(
        -mcpu=tc32
        -mfpu=none
        -Os
        -fno-exceptions
        -fno-rtti
        -ffunction-sections
        -fdata-sections
        -Wall
        -Wextra
        -DMCU_CORE_TYPE=TLSR8258
    )

    add_link_options(
        -mcpu=tc32
        -Wl,--gc-sections
        -T ${TELINK_SDK_PATH}/boot/link/8258_ble.ld
    )
endif()

# Source files
set(SOURCES
    src/core/main.cpp
    src/flash/persistence.cpp
)

# Headers
include_directories(
    include
    ${TELINK_SDK_PATH}/common
    ${TELINK_SDK_PATH}/drivers/8258
    ${TELINK_SDK_PATH}/stack/ble
    ${TELINK_SDK_PATH}/vendor/common
)

if(USE_ZEPHYR)
    target_sources(app PRIVATE ${SOURCES})
    target_include_directories(app PRIVATE include)
else()
    add_executable(planetary-neuron ${SOURCES})

    # Link Telink libraries
    target_link_libraries(planetary-neuron
        ${TELINK_SDK_PATH}/lib/liblt_8258.a
        ${TELINK_SDK_PATH}/lib/libmesh.a
    )

    # Generate binary for flashing
    add_custom_command(TARGET planetary-neuron POST_BUILD
        COMMAND ${CMAKE_OBJCOPY} -O binary
            $<TARGET_FILE:planetary-neuron>
            ${CMAKE_BINARY_DIR}/planetary-neuron.bin
        COMMENT "Generating flashable binary"
    )
endif()

# Memory usage report
add_custom_target(size
    COMMAND ${CMAKE_SIZE} $<TARGET_FILE:planetary-neuron>
    DEPENDS planetary-neuron
    COMMENT "Memory usage report"
)
