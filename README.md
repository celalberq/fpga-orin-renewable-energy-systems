# FPGA + Jetson Orin Renewable-Energy Systems

A portfolio monorepo containing three distinct university engineering projects
that were also integrated into one working renewable-energy demonstrator. Each
project has its own design scope, implementation, tests, and evidence; the
integration shares hardware measurements and one telemetry contract.

## Three Projects

| Project | Independent scope | Main validated result |
|---|---|---|
| [Solar Tracker and BESS](solar-tracker-bess/) | LDR and panel sensing, two-axis control, and signed battery telemetry | Physical light tracking plus measured charge and discharge |
| [FPGA Digital Communications](fpga-digital-communications/) | CRC framing, QPSK mapping, and OFDM resource accounting | Live 161-byte frames and Nexys Video pipeline proof |
| [Network Telemetry Dashboard](network-telemetry-dashboard/) | UDP transport, validation, reliability monitoring, visualization, and logging | 368/368 valid continuous-demo packets with zero sequence gaps |

The projects can be reviewed separately through the links above. The
`system-integration/` directory contains only their shared architecture,
cross-project runbooks, final report, presentation, and demonstration media.

## System Overview

```mermaid
flowchart LR
    LDR["4x KY-018 LDR"] --> ADC["MCP3208 ADC"]
    PV["Panel + voltage divider"] --> ADC
    ADC --> FPGA["Nexys Video FPGA"]
    FPGA --> ORIN["Jetson Orin Nano"]
    ORIN --> PCA["PCA9685"]
    PCA --> SERVOS["Pan + tilt servos"]
    CELL["Protected 1S Li-ion"] --> INA["INA226"]
    INA --> ORIN
    CELL --> TP["TP4056"]
    TP --> FAN["Fan discharge load"]
    ORIN --> UDP["Unified UDP telemetry"]
    UDP --> COMM["CRC/QPSK/OFDM bridge"]
    COMM --> DASH["Dashboard + CSV evidence"]
```

The diagram shows the final integration path; it does not collapse the three
projects into a single claimed deliverable.

## Headline Results

| Measurement | Result |
|---|---:|
| Fixed-vs-tracking mean-power gain | `+24.141%` |
| Fixed-vs-tracking energy gain | `+24.229%` |
| Best observed tracking error | `0.012 deg` |
| Locked tracker samples in final run | `213` |
| Shading/recovery test | `120 valid, 0 gaps` |
| Real fan-load battery discharge | approximately `2.954 V`, `-231 mA`, `-0.683 W` |
| Real supervised battery charging | `+233 to +236 mA`, `+0.895 to +0.908 W` |
| Final continuous tracker+BESS run | `368/368 valid`, `0 gaps` |
| Continuous BESS state sequence | `idle -> charging -> idle -> discharging -> idle` |
| Unified communication profile | `161 B`, `644 QPSK`, `14 OFDM` |

## Hardware

- Digilent Nexys Video FPGA board
- Jetson Orin Nano Super
- MCP3208 ADC
- Four KY-018 light sensors
- PCA9685 servo controller
- Two 180-degree pan/tilt servos and replacement mechanism
- Small solar panel with a 1k-ohm measurement load
- INA226 current/power monitor with R100 shunt
- Protected 3.7 V, 2500 mAh 18650 cell
- TP4056 charger/protection module
- L9110 fan load

## Unified Data Path

```text
Nexys/MCP3208 sensor UART
  -> Orin LDR tracker + PCA9685 servo actuation + INA226 BESS measurement
  -> unified tracker/panel/BESS UDP JSON on port 5013
  -> FPGA digital-communications CRC/QPSK/OFDM bridge
  -> forwarded UDP JSON on port 5011
  -> network telemetry dashboard, validation, sequence-gap monitoring, and CSV logging
```

The final mixed communication frame contains tracker angles and target, tracking
error and state, panel voltage and estimated power, battery voltage, signed
current and power, BESS state, sequence metadata, and actuator state.

```text
Payload:       157 bytes
CRC frame:     161 bytes / 1288 bits
QPSK:          644 symbols
OFDM:          14 symbols
QPSK padding:  28 symbols
```

## Primary Evidence

- [Final bidirectional tracker+BESS demo](system-integration/demo_evidence/video/unified_tracker_bess_bidirectional_final_demo_2026-08-11.mp4)
- [Final edited unified demo](system-integration/demo_evidence/video/unified_tracker_bess_integrated_demo_2026-08-11_edited.mp4)
- [Final technical report](system-integration/demo_evidence/final_report/fpga_orin_renewable_energy_systems_final_report_2026_08_11.docx)
- [Final technical report PDF](system-integration/demo_evidence/final_report/fpga_orin_renewable_energy_systems_final_report_2026_08_11.pdf)
- [Final presentation](system-integration/demo_evidence/final_presentation/fpga_orin_renewable_energy_systems_final_presentation_2026_08_11.pptx)
- [Current system status](system-integration/current_system_status_2026_08_11.txt)
- [Authoritative hardware wiring, connectors, and BOM](system-integration/final_hardware_wiring_2026_08_11.md)
- [Reproducible setup and verification](SETUP.md)
- [Unified board-test record](solar-tracker-bess/docs/board_test_24_unified_tracker_bess_discharge.txt)
- [Bidirectional BESS board-test record](solar-tracker-bess/docs/board_test_25_unified_tracker_bess_bidirectional_demo.txt)
- [Charging board-test record](solar-tracker-bess/docs/board_test_23_real_bess_charge_udp_dashboard.txt)
- [Discharge board-test record](solar-tracker-bess/docs/board_test_22_real_bess_ina226_discharge.txt)
- [Final bidirectional bridge CSV](fpga-digital-communications/data/unified_tracker_bess_bidirectional_demo_bridge.csv)
- [Final bidirectional dashboard CSV](network-telemetry-dashboard/data/unified_tracker_bess_bidirectional_demo_dashboard.csv)
- [Architecture source](system-integration/demo_evidence/final_system_architecture_2026_08_11.md)
- [CV and report summary](system-integration/demo_evidence/cv_report_summary.txt)

## Repository Map

| Directory | Contents |
|---|---|
| `solar-tracker-bess/` | Renewable sensing, Orin tracking, PCA9685 control, BESS telemetry, HDL, and hardware tests |
| `fpga-digital-communications/` | Communication simulations, CRC/QPSK/OFDM HDL, PC bridge, constraints, and board tests |
| `network-telemetry-dashboard/` | UDP/dashboard software, reliability tests, and network evidence |
| `system-integration/` | Shared architecture, wiring, reports, presentation, evidence, and videos |

## Safety and Limitations

- The battery does not power the Orin or Nexys; both use their normal supplies.
- The TP4056 USB input is disconnected while the fan load is connected because
  simultaneous charge/load sharing has not been validated.
- Temporary battery terminals are used only for supervised bench testing.
- Indoor panel power is low because the available source is a handheld LED.
- The panel-power A/B result is estimated from voltage across a known resistor.
- The communication subsystem is CRC/QPSK/OFDM profiling and FPGA pipeline
  validation, not a complete over-the-air RF modem.

## Optional Extensions

- Outdoor sunlight measurements
- Mechanically secure battery terminals and enclosure
- Full FPGA IFFT/FFT modem or SDR/RF loopback
- Remote database or cloud deployment
