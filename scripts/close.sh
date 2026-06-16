PORT=$1
export ADB=D:/ProgramData/Sdk/platform-tools/adb.exe
${ADB} -s emulator-${PORT} emu kill