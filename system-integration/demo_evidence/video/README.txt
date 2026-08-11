Integrated Real-LDR Tracker Subsystem Demo
==========================================

Status
------

```text
TRACKER SUBSYSTEM LIVE PASS
```

Recording
---------

```text
File: tracker_subsystem_integrated_demo_2026-08-10.mp4
Date: 2026-08-10
Duration: 93.4 seconds
Resolution: 1920x1080
Frame rate: 30 fps
File size: 229,875,082 bytes
Audio: muted / silent
SHA-256: 8678F51070E854CE6ED240E728A468F1E63E10D311C83BC740D314EAE1F57726
```

Visible Evidence
----------------

```text
Dashboard:
  Orin final real four-LDR solar tracker source
  healthy UDP link
  zero invalid packets and zero sequence gaps
  CRC/QPSK/OFDM communication layer
  physical servo actuator
  tracker state, panel target, power, and protection state

Orin / NoMachine:
  live real-LDR samples
  PCA9685 channel commands
  drive=on
  clean release of channels 15 and 12 at completion

Windows bridge:
  sequential p1br frames
  frame_b=133, qpsk=532, ofdm=12
  gap=0 and ok=1

Hardware camera:
  physical mounted panel movement
  panel-only covering during the shading test
```

Timeline
--------

```text
00:00  New run starts with the dashboard and physical panel visible.
00:05  Healthy link and visible panel convergence.
00:15  Tracker is locked and shading baseline learning is visible.
00:29  Protection reaches OK before the panel-cover test.
00:37  Protection displays red Shading while the panel is covered.
00:39  Shading remains asserted.
00:43  Protection has recovered to OK after uncovering.
01:31  Final seq=179: healthy, 0 gaps, 0 invalid, locked, 0.1-degree error.
01:31  Bridge reaches seq=179 with gap=0/ok=1; Orin releases both channels.
```

Editing Note
------------

This MP4 is the accepted trimmed tracker-subsystem evidence video. The
accidental captured audio is muted. The earlier untrimmed MKV was removed after
verification. This does not claim completion of the separate real BESS stage.


Unified Tracker and Real BESS Demo
==================================

Status
------

```text
UNIFIED TRACKER + REAL BESS LIVE PASS
```

Recording
---------

```text
Preferred edited proof: unified_tracker_bess_integrated_demo_2026-08-11_edited.mp4
Raw capture: unified_tracker_bess_integrated_demo_2026-08-11.mkv
Date: 2026-08-11
Edited duration: 33 seconds
Edited resolution: 1920x1080
Edited frame rate: 30 fps
Edited file size: 80,328,229 bytes
Edited SHA-256: 7E0E971ACE66E140DDD306CD3FADDAAA93B95FF30DB851A70F7E236E23A34812
Raw file size: 15,069,913 bytes
Raw SHA-256: 67875F24312B2F9B86D5A466550C7413ED856A69B96C476D7252D2D4068D81E9
```

Matching CSV Evidence
---------------------

```text
fpga-digital-communications/data/unified_tracker_bess_final_demo_bridge.csv
network-telemetry-dashboard/data/unified_tracker_bess_final_demo_dashboard.csv
```

Validated Result
----------------

```text
60/60 CRC-valid mixed frames
0 sequence gaps
161-byte frames, 644 QPSK symbols, 14 OFDM symbols
Both pan and tilt axes moved
Tracker reached locked state
Panel voltage: 84 to 321 mV
Real BESS voltage: 2975 to 2980 mV
Real BESS current: approximately -214 mA
Real BESS power: -636 to -638 mW
Dashboard state: discharging
```

The visibly changing panel-power trace is expected with a handheld LED and a
moving panel. Its auto-scaled graph represents a very small absolute power
range. The independently measured battery-discharge power remained stable.


Unified Tracker and Bidirectional BESS Final Demo
=================================================

Status
------

```text
FINAL CONTINUOUS TRACKER + BIDIRECTIONAL BESS LIVE PASS
```

Recording
---------

```text
File: unified_tracker_bess_bidirectional_final_demo_2026-08-11.mp4
Date: 2026-08-11
Duration: 196.53 seconds
Resolution: 2560x1440
Frame rate: 30 fps
Video: H.264
Audio: none
File size: 61,518,238 bytes
SHA-256: CA3890AF8DC1A0DA271EB855CCBC08B3D733BB98884584540634CD89113A4DE7
```

Visible Evidence
----------------

```text
Dashboard and Orin terminal show idle, positive charging, negative
discharging, and final idle recovery in one uninterrupted run.
The physical panel visibly moves on both axes and reaches locked state.
The bridge remains CRC valid with zero gaps.
The dashboard records 368 valid packets, 0 invalid packets, and 0 gaps.
```

Matching CSV Evidence
---------------------

```text
fpga-digital-communications/data/unified_tracker_bess_bidirectional_demo_bridge.csv
network-telemetry-dashboard/data/unified_tracker_bess_bidirectional_demo_dashboard.csv
```
