# APKs Source Directory

This directory is used to store all Android APK files required by the GUITestBench project.

Download the defective APKs via the following link: [APKs](https://huggingface.co/datasets/yifeigao/GUITestBench)

## Required APKs

Based on the project configuration, the following APK files should be placed in this directory:

### Single-Version Applications
| Application Name | APK Filename |
|-----------------|-------------|
| NewPipe | `NewPipe_0.27.0.apk` |
| FakeTraveler | `FakeTraveler-debug-02.apk` |
| VibeYou | `VibeYou-debug-03.apk` |
| Broccoli | `broccoli-release-01.apk` |
| Tasks | `org.tasks_130907-release-02.apk` |
| Catima | `catima-v2_32_1.apk` |
| AndrOBD | `com.fr3ts0n.ecu.gui.androbd_20007.apk` |
| Markor | `markor-v1.0.2.apk` |
| OwnTracks | `owntracks-v2_5_0.apk` |

### Multi-Version Applications

#### Amaze File Manager
- `amaze.file.manager.3.4.3.play.apk` (version 3.4.3)
- `AmazeFileManager-v3.5.3.apk` (version 3.5.3)

#### OpenTracks
- `OpenTracks-release-03.apk` (version 03)
- `opentracks-v3_7_3.apk` (version 3.7.3)
- `opentracks-v4_12_4.apk` (version 4.12.4)

#### AnkiDroid
- `AnkiDroid-2.8.2.apk` (version 2.8.2)
- `AnkiDroid-2.13.5-arm64-v8a.apk` (version 2.13.5)
- `AnkiDroid-2.14.0-arm64-v8a.apk` (version 2.14.0)
- `AnkiDroid-2.15alpha34-arm64-v8a.apk` (version 2.15)

## Application Categories

These applications cover various categories:
- **Internet/Multimedia**: NewPipe, VibeYou
- **File Manager**: Amaze File Manager
- **Education**: AnkiDroid
- **Recipe Management**: Broccoli
- **Task Management**: Tasks
- **Loyalty Cards**: Catima
- **GPS Tracking**: OpenTracks, OwnTracks
- **Note Taking**: Markor
- **Location Spoofing**: FakeTraveler
- **Automotive**: AndrOBD

## Usage

1. Place all APK files in this directory
2. The project references these files through the `APK2PATH` mapping in `constant.py`
3. Ensure filenames exactly match the configuration

## Related Resources

- **Defects-Oriented Tasks**: `../defects_oriented/` - Test instructions for known defects
- **Exploration-Oriented Tasks**: `../exploration_oriented/` - Exploratory testing scenarios
- **Reproduction Screenshots**: `../reproduce/` - Screenshot evidence of defect reproduction
- **Test Database**: `../database/` - Database files required for testing
