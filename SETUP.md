# Reproducible Setup and Verification

The repository uses Python 3.9 or newer. Runtime tools are plain Python scripts; no package installation or cloud service is required for the communication simulations, dashboard, analyzers, or automated tests.

## Windows PC

From the repository root in PowerShell:

```powershell
py -3.9 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run_tests.py
```

Windows runs the FPGA Digital Communications CRC/QPSK/OFDM bridge, the Network
Telemetry Dashboard and reliability tools, evidence analyzers, and report
builder. The final bridge/dashboard terminal commands are preserved in
[board test 25](solar-tracker-bess/docs/board_test_25_unified_tracker_bess_bidirectional_demo.txt).

## Jetson Orin Nano

The demonstrated Orin environment was Ubuntu/JetPack with Python 3.10. Keep the JetPack OpenCV build because it provides the NVIDIA CSI/GStreamer path.

```bash
sudo apt update
sudo apt install -y python3-venv python3-opencv python3-smbus i2c-tools

cd /home/msi
python3 -m venv --system-site-packages .venv-solar
source .venv-solar/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install pyserial==3.5 smbus2==0.5.0
```

If serial or I2C access is denied, add the current account to the device groups, sign out, and sign back in:

```bash
sudo usermod -aG dialout,i2c "$USER"
```

Verify the validated bus-7 devices before a hardware run:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
sudo i2cdetect -y -r 7
```

Expected I2C addresses are PCA9685 `0x40` and external INA226 `0x44`; PCA9685 all-call `0x70` may also appear. The external wiring is defined in [the authoritative hardware document](system-integration/final_hardware_wiring_2026_08_11.md).

## FPGA Toolchain

- Board: Digilent Nexys Video
- FPGA part: `xc7a200tsbg484-1`
- Demonstrated tool installation: AMD Vivado 2025.2
- Constraints: `fpga-digital-communications/hardware/constraints/` and `solar-tracker-bess/hardware/constraints/`
- HDL sources: `fpga-digital-communications/code/hdl/` and `solar-tracker-bess/code/hdl/`

Vivado projects and generated runs are intentionally excluded from Git. Recreate a project with the listed FPGA part, add the required HDL source and matching XDC file, synthesize, implement, generate the bitstream, and program `xc7a200t_0` through Hardware Manager. Exact validated source/constraint combinations are recorded in the corresponding files under `fpga-digital-communications/docs/` and `solar-tracker-bess/docs/`.

## Automated Verification

Run every hardware-independent regression from the repository root:

```powershell
python run_tests.py
```

Or run a project suite directly:

```powershell
python -m unittest discover -s fpga-digital-communications/code/tests -p "test_*.py" -v
python -m unittest discover -s network-telemetry-dashboard/code/tests -p "test_*.py" -v
python -m unittest discover -s solar-tracker-bess/code/tests -p "test_*.py" -v
```

The root runner also executes the two legacy Solar Tracker and BESS unit-test modules and the FPGA Digital Communications bridge self-test. Hardware tests are separate because they require Nexys, Orin, serial, I2C, servos, and the supervised battery fixture.

## Evidence Reproduction Boundary

CSV logs, screenshots, reports, and videos are committed as measured evidence. Re-running software-only tests does not regenerate real hardware measurements. Reproducing those files requires the physical system and the step-by-step commands in the dated board-test records.
