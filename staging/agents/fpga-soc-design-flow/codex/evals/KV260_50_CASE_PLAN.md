<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 50-Design Generalization Campaign

Status: execution plan

The original R01–R20 ladder remains unchanged. R21–R50 extend coverage from
generic PL/video building blocks into the attached Pmod I2S2 audio path,
AR1335/AP1302 camera path, PS/DDR control, Linux-facing integration, and
combined multimedia systems. Every case keeps a deterministic public RTL
kernel and cocotb oracle even when its platform work package uses live
peripherals.

| Rank | Case | Primary generalization target |
|---:|---|---|
| 21 | `kv260_i2s_transmitter` | I2S serialization and framing |
| 22 | `kv260_i2s_receiver` | I2S capture and channel alignment |
| 23 | `kv260_audio_gain` | Saturating signed audio arithmetic |
| 24 | `kv260_stereo_mixer` | Multi-source audio mixing |
| 25 | `kv260_audio_tone_generator` | Deterministic audio stimulus |
| 26 | `kv260_audio_fir_equalizer` | Pipelined audio filtering |
| 27 | `kv260_audio_peak_meter` | Windowed level measurement |
| 28 | `kv260_audio_mute_ramp` | Click-free gain ramping |
| 29 | `kv260_audio_channel_router` | Stereo routing and swap |
| 30 | `kv260_audio_dc_blocker` | Stateful high-pass filtering |
| 31 | `kv260_raw10_unpacker` | Packed sensor-pixel conversion |
| 32 | `kv260_bayer_demosaic` | Bayer neighborhood processing |
| 33 | `kv260_color_correction` | Fixed-point color matrix |
| 34 | `kv260_gamma_lut` | Programmable lookup transformation |
| 35 | `kv260_image_histogram` | Frame statistics and memory updates |
| 36 | `kv260_adaptive_threshold` | Runtime-controlled segmentation |
| 37 | `kv260_morphology_3x3` | Neighborhood morphology |
| 38 | `kv260_object_bounding_box` | Frame-level spatial reduction |
| 39 | `kv260_alpha_overlay` | Dual-stream video composition |
| 40 | `kv260_video_cropper` | Raster coordinate transformation |
| 41 | `kv260_motion_detector` | Temporal frame differencing |
| 42 | `kv260_frame_statistics` | Frame min/max/mean accumulation |
| 43 | `kv260_av_timestamp` | Cross-stream timestamp correlation |
| 44 | `kv260_axi_traffic_monitor` | AXI performance instrumentation |
| 45 | `kv260_interrupt_aggregator` | PS-visible event prioritization |
| 46 | `kv260_dma_descriptor_queue` | Descriptor control and completion |
| 47 | `kv260_ddr_bandwidth_exerciser` | Bounded memory-traffic generation |
| 48 | `kv260_linux_gpio_mailbox` | Linux/PS-to-PL command protocol |
| 49 | `kv260_camera_audio_synchronizer` | Camera/audio epoch alignment |
| 50 | `kv260_multimedia_appliance` | Camera, audio, DDR, PS, and debug integration |

Hardware qualification remains serialized per target/JTAG cable. Cases with
no matching LTX/debug map are design-complete only until rebuilt through the
hardware-qualified instrumentation path.
