System Integration Documentation
================================

This folder contains the shared architecture, evidence, reports, and tools used
to integrate three independently scoped projects into one bench demonstration.
It is not a fourth project and does not replace the individual project records.

Current implementation folders:

```text
bringup/        Nexys Video LED/switch and UART bring-up evidence
tools/          Shared analysis and final-report builder scripts
reports/        Generated tracker/communication metrics and plots
demo_evidence/  Final videos, report, presentation, architecture, and indexes
```

Cross-project architecture:

```text
integrated_three_project_architecture.txt
system_theory_and_build_doctrine.txt
expanded_final_system_concept.txt
shared_tracker_packet_contract.txt
```

Use these files to connect Solar Tracker and BESS, FPGA Digital Communications,
and Network Telemetry Dashboard through one shared renewable telemetry contract,
with clear Nexys Video, Jetson Orin, and PC roles.

Current hardware roles:

1. Nexys Video samples the MCP3208 sensor channels and provides validated FPGA
   communication-pipeline evidence.
2. Jetson Orin reads live UART data, controls both PCA9685 servo axes, reads
   signed INA226 BESS telemetry, and publishes unified UDP JSON.
3. The PC runs the FPGA Digital Communications CRC/QPSK/OFDM bridge and the
   Network Telemetry Dashboard application and logger.
4. The protected 1S cell is tested only under supervised TP4056 charging or
   fan-load discharge; it does not power the Orin or Nexys.

Shared project pattern:

```text
External world
  -> Sensors / Ethernet / ADC-DAC / power stage
  -> FPGA real-time logic
  -> Orin tracking + BESS measurement + unified UDP telemetry
  -> PC CRC/QPSK/OFDM bridge + dashboard + CSV evidence
  -> final report, presentation, demo video, and portfolio README
```

Common folder pattern:

```text
README.md                                      GitHub-facing project overview
current_system_status_2026_08_11.txt           Latest validated status
demo_evidence/README.txt                       Evidence index
demo_evidence/final_report/                    Final DOCX and PDF
demo_evidence/final_presentation/              Seven-slide presentation
demo_evidence/video/                           Accepted evidence recordings
reports/                                       Derived metrics and figures
```

Headline final result: 368/368 valid continuous tracker+BESS packets, zero
sequence gaps, both servo axes active, and real idle/charge/discharge states.

Post-graduation direction:

```text
post_graduation_australia_application_direction.txt
target_schools_and_programs.txt
```

These files connect the summer portfolio to Australia master's applications and career directions, with computer engineering + renewable energy systems as the current primary path.
