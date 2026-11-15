# PlanWise AI - Android App

A lightweight Android app (WebView) for the deployed PlanWise AI website:
https://planwise-ai-bqcm.onrender.com

## Features

- Full-screen app with its own icon and splash screen
- Explains the wait while the free server wakes up (first open can take up to a minute)
- Offline screen with a **Try again** button
- Location permission for **📍 Use my current location**
- Back button returns from the planner to Explore before leaving the app
- Map and website links open in the right external app (Maps, browser)
- Works on Android 8.0 (API 26) and newer; tested on Android 17 (Pixel 6 emulator)

## Build

Requires Android Studio (or JDK 17 + Android SDK 36).

```bash
cd android-app
./gradlew assembleRelease     # signed release APK (needs keystore.properties)
./gradlew assembleDebug       # debug APK, no keystore needed
```

Output:

- `app/build/outputs/apk/release/PlanWise-AI-release.apk`
- `app/build/outputs/apk/debug/PlanWise-AI-debug.apk`

Or open the `android-app` folder in Android Studio and use **Build → Build APK(s)**.

## Release signing

`keystore.properties` and `planwise-release.jks` are kept out of git. Back them up:
the same key is required to publish updates of the app.

```properties
storeFile=planwise-release.jks
storePassword=...
keyAlias=planwise
keyPassword=...
```

## Changing the website address

Edit `SITE_URL` in `app/build.gradle` and rebuild.
