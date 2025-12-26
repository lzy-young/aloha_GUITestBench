PORT=$1
export ADB=/your/local/path/to/adb
${ADB} -s emulator-${PORT} emu kill