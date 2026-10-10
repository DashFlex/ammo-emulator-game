# Ammo Emulator Game

A macOS shooting gallery game built around the Force Touch haptic trackpad.  
Hold the trackpad click — feel every round fire.

## Concept

The original Ammo Emulator was one trick: hold the trackpad click and the Mac fires a haptic tick every 150 ms. This game keeps that as the core mechanic and wraps a full shooting gallery around it.

## Controls

| Input | Action |
|-------|--------|
| **Hold Click** | Fire (one haptic tick per round, 150 ms apart) |
| **R** | Reload *(Classic mode only)* |
| **P** / **Esc** | Pause |
| **M** | Back to menu *(from pause or game over)* |

## Game Modes

### 🟡 Classic
- 30-round magazine + 120 rounds in reserve
- Shoot the **gold ammo crates** to get **6 seconds of infinite ammo** and a full mag reload

### ♾️ Infinite
- Unlimited ammo — the original Ammo Emulator behaviour
- Pure score attack

## Requirements

- **macOS** with a **Force Touch trackpad** (for haptics)
- **Python 3**
- Dependencies:
  ```bash
  pip install pyobjc-framework-Cocoa
  ```

> Haptics require a finger resting on the trackpad while you hold the click.

## Running from Source

```bash
python3 ammo_emulator_game.py
```

## Building the App

```bash
pip install pyinstaller pyobjc-framework-Cocoa
pyinstaller --windowed --name "Ammo Emulator" ammo_emulator_game.py
```

Or to wrap the compiled binary into an `.app` bundle manually:

```bash
APP="/Applications/ammo-emulator-game.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp ammo-emulator-game "$APP/Contents/MacOS/ammo-emulator-game"
chmod +x "$APP/Contents/MacOS/ammo-emulator-game"
codesign --force --deep --sign - "$APP"
```

## Technical Details

| Property | Value |
|----------|-------|
| Language | Python 3 |
| Packaging | PyInstaller |
| Runtime | Embedded Python (no install needed) |
| Architecture | ARM64 (Apple Silicon) |
| Linked libs | `libSystem.B.dylib`, `libz.1.dylib` |
| Binary size | ~11 MB |
