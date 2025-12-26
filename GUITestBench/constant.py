import json

with open('./GUITestBench/database/data.json', 'r') as f:
    CONDITION = json.load(f)

APK2PATH = {
    "newpipe": "./GUITestBench/apks_source/NewPipe_0.27.0.apk", 
    "faketraveler": "./GUITestBench/apks_source/FakeTraveler-debug-02.apk", 
    "vibeyou": "./GUITestBench/apks_source/VibeYou-debug-03.apk", 
    "opentracks-03": "./GUITestBench/apks_source/OpenTracks-release-03.apk", 
    "opentracks-3_7_3": "./GUITestBench/apks_source/opentracks-v3_7_3.apk", 
    "opentracks-4_12-4": "./GUITestBench/apks_source/opentracks-v4_12_4.apk", 
    "broccoli": "./GUITestBench/apks_source/broccoli-release-01.apk", 
    "tasks": "./GUITestBench/apks_source/org.tasks_130907-release-02.apk", 
    "ankidroid-2_8_2": "./GUITestBench/apks_source/AnkiDroid-2.8.2.apk", 
    "ankidroid-2_15": "./GUITestBench/apks_source/AnkiDroid-2.15alpha34-arm64-v8a.apk", 
    "ankidroid-2_14": "./GUITestBench/apks_source/AnkiDroid-2.14.0-arm64-v8a.apk", 
    "ankidroid-2_13_5": "./GUITestBench/apks_source/AnkiDroid-2.13.5-arm64-v8a.apk", 
    "amaze-3_4_3": "./GUITestBench/apks_source/amaze.file.manager.3.4.3.play.apk", 
    "amaze-3_5_3": "./GUITestBench/apks_source/AmazeFileManager-v3.5.3.apk", 
    "catima": "./GUITestBench/apks_source/catima-v2_32_1.apk", 
    "androbd": "./GUITestBench/apks_source/com.fr3ts0n.ecu.gui.androbd_20007.apk", 
    "markor": "./GUITestBench/apks_source/markor-v1.0.2.apk", 
    "owntracks": "./GUITestBench/apks_source/owntracks-v2_5_0.apk"
}

ACTIVITY_MAP = {
    "newpipe": "org.schabi.newpipe.debug/org.schabi.newpipe.MainActivity", 
    "faketraveler": "cl.coders.faketraveler/.MainActivity", 
    "vibeyou": "app.suhasdissa.vibeyou.debug/app.suhasdissa.vibeyou.MainActivity", 
    "opentracks-03": "de.dennisguse.opentracks/.introduction.IntroductionActivity", 
    "opentracks-3_7_3": "de.dennisguse.opentracks/.TrackListActivity", 
    "opentracks-4_12-4": "de.dennisguse.opentracks/.introduction.IntroductionActivity", 
    "broccoli": "com.flauschcode.broccoli/.MainActivity", 
    "tasks": "org.tasks/com.todoroo.astrid.activity.MainActivity", 
    "ankidroid-2_8_2": "com.ichi2.anki/.IntentHandler", 
    "ankidroid-2_15": "com.ichi2.anki/.IntentHandler", 
    "ankidroid-2_14": "com.ichi2.anki/.IntentHandler", 
    "ankidroid-2_13_5": "com.ichi2.anki/.IntentHandler", 
    "amaze-3_4_3": "com.amaze.filemanager/.activities.MainActivity", 
    'amaze-3_5_3': 'com.amaze.filemanager/.ui.activities.MainActivity', 
    "catima": "me.hackerchick.catima/protect.card_locker.MainActivity", 
    "androbd": "com.fr3ts0n.ecu.gui.androbd/.MainActivity", 
    "markor": "net.gsantner.markor/.activity.MainActivity", 
    "owntracks": "org.owntracks.android/.ui.map.MapActivity"
}

APP2PACKAGE = {
    'newpipe': 'org.schabi.newpipe.debug', 
    'faketraveler': 'cl.coders.faketraveler', 
    'vibeyou': 'app.suhasdissa.vibeyou.debug', 
    'opentracks-03': 'de.dennisguse.opentracks', 
    'opentracks-3_7_3': 'de.dennisguse.opentracks', 
    'opentracks-4_12-4': 'de.dennisguse.opentracks', 
    'broccoli': 'com.flauschcode.broccoli', 
    'tasks': 'org.tasks', 
    'ankidroid-2_8_2': 'com.ichi2.anki', 
    'ankidroid-2_15': 'com.ichi2.anki', 
    'ankidroid-2_14': 'com.ichi2.anki', 
    'ankidroid-2_13_5': 'com.ichi2.anki', 
    'amaze-3_4_3': 'com.amaze.filemanager', 
    'amaze-3_5_3': 'com.amaze.filemanager', 
    'catima': 'me.hackerchick.catima', 
    'androbd': 'com.fr3ts0n.ecu.gui.androbd', 
    'markor': 'net.gsantner.markor', 
    'owntracks': 'org.owntracks.android', 
}

DB_PATH = {
    'broccoli': '/data/data/com.flauschcode.broccoli/databases/broccoli', 
    'tasks': '/data/data/org.tasks/databases/database', 
    'owntracks': '/data/data/org.owntracks.android/databases/waypoints',
    'ankidroid-2_14': "/storage/emulated/0/AnkiDroid/collection.anki2"
}
