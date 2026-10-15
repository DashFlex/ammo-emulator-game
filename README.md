# Ammo Emulator Game

I made this with AI lol

A macOS shooting gallery game built around the Force Touch haptic trackpad.  
Hold the trackpad click — feel every round fire.

DISCLAMER: I am a student and therefore do not have time to accept pull requests and others. Thanks for understanding.

## Concept

The original Ammo Emulator was one trick: hold the trackpad click and the Mac fires a haptic tick every 150 ms. This game keeps that as the core mechanic and wraps a full shooting gallery around it.

## Controls

| Input | Action |
|-------|--------|
| **Hold Click** | Fire (one haptic tick per round, 150 ms apart) |
| **R** | Reload *(Classic mode only)* |
| **P** / **Esc** | Pause |
| **M** | Back to menu *(from pause or game over)* |

## How to install
There is a .app.zip file. Download it and open it. Drag the app to the Applications folder. Do not rename it.
Before you open it, install Python if you dont have it already (I recommend you install Homebrew cuz its the fastest)
```bash
# Install Homebrew (skip if you already have it)
/bin/bash -c "$(curl -fsSL https://githubusercontent.com)"

# Install Python
brew install python
```
Now once you have done all these (especially dragging it to the Applications folder) go ahead and run this
```bash
pip3 install pyobjc-framework-Cocoa
chmod +x "/Applications/ammo-emulator-game.app/Contents/MacOS/ammo-emulator-game"
xattr -cr "/Applications/ammo-emulator-game.app"
```

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
  pip3 install pyobjc-framework-Cocoa
  ```

> Haptics require a finger resting on the trackpad while you hold the click.

## Technical Details

| Property | Value |
|----------|-------|
| Language | Python 3 |
| Packaging | PyInstaller |
| Runtime | Embedded Python (no install needed) |
| Architecture | ARM64 (Apple Silicon) |
| Linked libs | `libSystem.B.dylib`, `libz.1.dylib` |
| Binary size | ~11 MB |
| Device | All MacBooks sold after 2018 (discluding MacBook Neo cuz it doesnt have any capacitive trackpad)|
