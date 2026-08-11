Orin App Folder
===============

This folder contains the scripts validated on the Jetson Orin Nano Super for
INA226 measurement, PCA9685 actuation, fallback camera tracking, and the final
four-LDR tracker/BESS gateway.

Current scripts
---------------

```text
ina226_reader.py
ina226_udp_gateway.py
pca9685_servo_test.py
pan_tilt_servo_test.py
tracker_softloop_udp_gateway.py
camera_light_tracker_udp_gateway.py
ldr_servo_tracker.py
```

INA226 first check
------------------

Run on Orin:

```text
sudo apt install -y i2c-tools python3-smbus
i2cdetect -y 7
python3 proje3/code/orin_app/ina226_reader.py --bus 7 --addr 0x40 --id-only
```

If the I2C device appears on a different bus, change `--bus`.
The current tested module appeared at address `0x44`, so use `--addr 0x44`
for the hardware currently on the bench.

Continuous read:

```text
python3 proje3/code/orin_app/ina226_reader.py --bus 7 --addr 0x44 --shunt-ohms 0.1
```

INA226 UDP dashboard gateway
----------------------------

Run on the Orin after the dashboard is running on the PC or Orin:

```text
python3 proje3/code/orin_app/ina226_udp_gateway.py --bus 7 --addr 0x44 --shunt-ohms 0.1 --udp-host 127.0.0.1 --udp-port 5011
```

Real BESS mode for the calibrated R100 module currently measuring the 2500 mAh
1S battery:

```text
python3 proje3/code/orin_app/ina226_udp_gateway.py \
  --mode bess \
  --bus 7 --addr 0x44 --shunt-ohms 0.1 \
  --bus-voltage-scale 0.9501 \
  --battery-capacity-ah 2.5 --battery-nominal-voltage 3.7 \
  --udp-host PC_IP_ADDRESS --udp-port 5013
```

BESS mode reports real signed battery power. Positive current means charging;
negative current means discharging. The 2026-08-11 direct-fan validation measured
approximately 2.954 V, -231 mA, and -0.683 W for 40/40 stable samples.

Unified four-LDR tracker and real BESS
--------------------------------------

Use MCP3208 CH0 plus the fixed 1 kOhm load for panel power while the INA226
reports signed battery telemetry in the same packet:

```text
python3 proje3/code/orin_app/ldr_servo_tracker.py \
  --port /dev/ttyUSB0 \
  --calibration-in proje3/data/ldr_ab_calibration.json \
  --sensor-mount fixed --control-mode sequential \
  --max-packets 400 \
  --drive-servos --bus 7 --addr 0x40 \
  --ina-enable --ina-role bess --ina-addr 0x44 \
  --shunt-ohms 0.1 --ina-bus-voltage-scale 0.9501 \
  --battery-capacity-ah 2.5 --battery-nominal-voltage 3.7 \
  --pan-channel 15 --tilt-channel 12 \
  --pan-start 90 --tilt-start 90 \
  --pan-min 10 --pan-max 170 --tilt-min 10 --tilt-max 170 \
  --fixed-tilt-gain 120 \
  --fixed-center-deadband 0.015 \
  --fixed-hemisphere-deadband 0.05 \
  --target-deadband-deg 1.0 \
  --min-step 0.5 --max-step 3.0 \
  --stable-samples 2 --invert-tilt \
  --panel-load-ohms 1000 \
  --udp-host PC_IP_ADDRESS --udp-port 5013 \
  --source-label "Orin unified tracker bidirectional BESS demo" \
  --log proje3/data/unified_tracker_bess_bidirectional_demo.csv \
  --overwrite-log
```

The resulting rich JSON variant is `orin.ldr_tracker.bess.v1`. Proje1 converts
it into a signed `mix` compact frame while proje2 shows panel/tracker and battery
values simultaneously.

Final continuous result: 368 valid packets, zero sequence gaps, both servo axes
active, 213 locked samples, and measured idle/charging/discharging states.

Notes:

```text
R100 on the INA226 module means shunt-ohms is 0.1.
R010 means shunt-ohms is 0.01.
```

PCA9685 servo bring-up
----------------------

Logic wiring:

```text
Orin pin 1  3.3V -> PCA9685 VCC
Orin pin 6  GND  -> PCA9685 GND
Orin pin 3  SDA  -> PCA9685 SDA
Orin pin 5  SCL  -> PCA9685 SCL
```

Servo power wiring:

```text
5V adapter + -> PCA9685 V+
5V adapter - -> PCA9685 GND
```

Important:

```text
PCA9685 VCC is 3.3V logic from Orin.
PCA9685 V+ is separate 5V servo power.
The 5V adapter ground and Orin/PCA9685 ground must be common.
Do not power the servo motor from the Orin 3.3V pin.
```

First test:

```text
sudo i2cdetect -y -r 7
python3 proje3/code/orin_app/pca9685_servo_test.py --bus 7 --addr 0x40 --channel 15 --angle 90
```

Small safe sweep:

```text
python3 proje3/code/orin_app/pca9685_servo_test.py --bus 7 --addr 0x40 --channel 15 --sweep --min-angle 70 --max-angle 110 --step 10 --cycles 1
python3 proje3/code/orin_app/pca9685_servo_test.py --bus 7 --addr 0x40 --channel 12 --sweep --min-angle 80 --max-angle 100 --step 5 --cycles 1
```

Two-servo pan/tilt test:

```text
python3 proje3/code/orin_app/pan_tilt_servo_test.py --bus 7 --addr 0x40 --pan-channel 15 --tilt-channel 12 --pan-min 70 --pan-max 110 --tilt-min 80 --tilt-max 100 --mode center
python3 proje3/code/orin_app/pan_tilt_servo_test.py --bus 7 --addr 0x40 --pan-channel 15 --tilt-channel 12 --pan-min 70 --pan-max 110 --tilt-min 80 --tilt-max 100 --step 10 --mode pan
python3 proje3/code/orin_app/pan_tilt_servo_test.py --bus 7 --addr 0x40 --pan-channel 15 --tilt-channel 12 --pan-min 70 --pan-max 110 --tilt-min 80 --tilt-max 100 --step 5 --mode tilt
python3 proje3/code/orin_app/pan_tilt_servo_test.py --bus 7 --addr 0x40 --pan-channel 15 --tilt-channel 12 --pan-min 70 --pan-max 110 --tilt-min 80 --tilt-max 100 --step 10 --mode box
```

Software tracker fallback
-------------------------

This diagnostic fallback sends a simulated four-LDR tracking loop to the same
UDP dashboard without requiring the physical mount:

```text
python3 proje3/code/orin_app/tracker_softloop_udp_gateway.py --udp-host PC_IP_ADDRESS --udp-port 5011
```

Use real INA226 voltage/current/power with simulated tracker angles:

```text
python3 proje3/code/orin_app/tracker_softloop_udp_gateway.py --udp-host PC_IP_ADDRESS --udp-port 5011 --ina-enable --ina-bus 7 --ina-addr 0x44 --shunt-ohms 0.1
```

Optional simulated-input servo drive:

```text
python3 proje3/code/orin_app/tracker_softloop_udp_gateway.py --udp-host PC_IP_ADDRESS --udp-port 5011 --drive-servos --pca-bus 7 --pca-addr 0x40 --pan-channel 15 --tilt-channel 12 --pan-min 70 --pan-max 110 --tilt-min 80 --tilt-max 100
```

Camera light tracker
--------------------

Safe synthetic test:

```text
python3 proje3/code/orin_app/camera_light_tracker_udp_gateway.py --synthetic --udp-host PC_IP_ADDRESS --udp-port 5013 --max-packets 80 --interval 0.25
```

CSI camera detection test, no servo output:

```text
python3 proje3/code/orin_app/camera_light_tracker_udp_gateway.py --camera csi --camera-id 0 --width 640 --height 480 --udp-host PC_IP_ADDRESS --udp-port 5013 --max-packets 80 --interval 0.25
```

Pan-only USB-camera diagnostic mode:

```text
python3 proje3/code/orin_app/camera_light_tracker_udp_gateway.py --camera usb --camera-id 1 --camera-mount fixed --width 640 --height 480 --source-label "Orin USB fixed-camera pan tracker" --udp-host PC_IP_ADDRESS --udp-port 5013 --max-packets 80 --interval 0.25 --drive-servos --pan-only --pca-bus 7 --pca-addr 0x40 --pan-channel 15 --tilt-channel 12 --pan-min 70 --pan-max 110 --pan-start 90 --tilt-start 90 --max-pan-step 2
```

`--pan-only` holds tilt in software and explicitly releases the PCA9685 tilt
channel before tracking begins. It remains available as a fallback diagnostic;
the final accepted system uses the four real LDR sensors and both servo axes.

Four-KY-018 tracker
-------------------

Read the Nexys UART on the Orin and calculate startup-calibrated LDR directions
without moving the servos:

```text
python3 proje3/code/orin_app/ldr_servo_tracker.py --port /dev/ttyUSB0 --max-packets 40
```

The first 20 packets calibrate center. Add `--drive-servos` only after the
dry-run direction labels pass.

The current build uses a stationary four-LDR cross beside the independently
moving servo head. Use `--sensor-mount fixed`: centered light maps to absolute
pan/tilt targets of 90/90, and each new LDR direction continuously updates the
absolute targets. `--sensor-mount moving` retains the experimental feedback
controllers for a future build where the LDR cross is attached to the moving
panel.

Send the real LDR tracker through the shared proje1 bridge and proje2 dashboard
without servo output:

```text
python3 proje3/code/orin_app/ldr_servo_tracker.py --port /dev/ttyUSB0 --calibration-in proje3/data/ldr_ab_calibration.json --sensor-mount fixed --max-packets 20 --panel-load-ohms 1000 --udp-host 192.168.1.219 --udp-port 5013 --source-label "Orin real four-LDR solar tracker"
```

`--udp-host` is optional. Omitting it preserves local-only tracker behavior.
`--panel-load-ohms 1000` reports an MCP3208 voltage-based load-power estimate
for the current weak indoor light; omit it when direct INA226 power is useful.

The tracker also protects against LDR rail/low-light input faults and can learn
a locked-state panel response baseline for shading detection. Configure the
detector with `--shading-learn-samples`, `--shading-drop-ratio`,
`--shading-trigger-samples`, and `--shading-recovery-samples`. Fault labels and
reasons are included in UDP packets and local CSV logs.

Camera mount modes:

```text
--camera-mount fixed
  Camera stays on the base/stand. Pixel direction maps to an absolute servo
  target around pan-start/tilt-start.

--camera-mount moving
  Camera is attached to the moving panel. Pixel error is corrected relative to
  the current servo angle.
```
