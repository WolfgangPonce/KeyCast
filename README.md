<img width="441" height="516" alt="Screenshot_2" src="https://github.com/user-attachments/assets/29c9add1-a531-4ff3-971d-f037aa7d0c29" />
<img width="393" height="90" alt="Screenshot_3" src="https://github.com/user-attachments/assets/7bd32f3d-1e2e-41fa-b1b8-34c4e07e6e04" />

# KeyCast

A lightweight keyboard overlay for screen recording and live streaming on Windows. KeyCast displays your keypresses as floating, fade-out chips on top of any application, so viewers can see exactly what you are typing or which shortcuts you are using.

Built with Python and PyQt6.

## Features

- **Floating overlay** that stays on top of every window and ignores mouse clicks (you can keep working underneath it).
- **Smart modifier grouping**, so `Ctrl + Shift + S` shows up as a single chip instead of three separate ones.
- **System tray icon** with quick access to settings and a clean exit.
- **Fully configurable**:
  - Font family and size
  - Position (four corners or custom X/Y offset)
  - Fade-out time
  - Maximum number of key chips visible at once
  - Background opacity
  - Text and background colours
- **Persistent settings** saved to `keycast_config.json` next to the executable.
- **Self-contained .exe** when built. No Python install required for end users.

## Requirements

- Windows 10 or 11
- Python 3.9 or newer (only if you are running from source or building the executable yourself)

## Usage

Run `KeyCast.exe`. A keyboard icon appears in the system tray. Right-click it for settings, or middle-click to close.

The overlay starts in the bottom-right corner of your primary monitor. Open Settings from the tray to move it, restyle it, or change behaviour.

## Running from source

```bash
git clone https://github.com/WolfgangPonce/KeyCast.git
cd KeyCast
pip install -r requirements.txt
python main.py
```

## Building the executable

A `build.bat` script is included for convenience:

```bash
build.bat
```

This installs dependencies and runs PyInstaller. The finished `KeyCast.exe` will be placed in the `dist/` folder. The build is fully self-contained, so you can move the .exe anywhere.

## Configuration file

Settings are saved to `keycast_config.json` in the same folder as the executable (or next to `main.py` when running from source). You can edit it manually if you prefer, but the Settings dialog is easier.

## Tech stack

- [PyQt6](https://pypi.org/project/PyQt6/) for the overlay window and settings UI
- [pynput](https://pypi.org/project/pynput/) for global keyboard hooks
- [PyInstaller](https://pyinstaller.org/) for packaging into a single .exe
- Win32 DWM API calls to remove the window border and shadow on Windows 11

## License

MIT. See [LICENSE](LICENSE) for details.

## Author

Built by Wolfgang ([GOAT Media Group](https://github.com/WolfgangPonce)).
