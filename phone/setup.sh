#!/usr/bin/env bash
# Builds the ADB Link phone app project (needs Flutter).
#   bash setup.sh [target-folder] [--build]
# --build also compiles the release APK and prints where it is.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="$HOME/adblink-app"
build=0
for a in "$@"; do
  case "$a" in
    --build) build=1 ;;
    *) dest="$a" ;;
  esac
done

command -v flutter >/dev/null || { echo "Flutter is not installed. See README.md ('Build the phone app yourself')."; exit 1; }

flutter create --org com.alienshtain --project-name adblink --platforms android "$dest"

rm -rf "$dest/lib" "$dest/test"
cp -r "$here/lib" "$dest/lib"
cp "$here/pubspec.yaml" "$dest/pubspec.yaml"

main_dir="$(dirname "$(find "$dest/android/app/src/main" -name 'MainActivity.*' | head -n1)")"
rm -f "$main_dir"/MainActivity.*
mkdir -p "$dest/android/app/src/main/kotlin/com/alienshtain/adblink"
cp "$here"/android_src/kotlin/*.kt "$dest/android/app/src/main/kotlin/com/alienshtain/adblink/"

cp "$here/android_src/AndroidManifest.xml" "$dest/android/app/src/main/AndroidManifest.xml"
# icons, launcher colours, quick-settings tile icon ... (merged over what Flutter generated)
cp -r "$here"/android_src/res/. "$dest/android/app/src/main/res/"

cd "$dest"
flutter pub get
echo
echo "Project ready in $dest"
if [ "$build" = 1 ]; then
  flutter build apk --release
  apk="$dest/build/app/outputs/flutter-apk/app-release.apk"
  echo
  echo "APK: $apk"
  echo "Install on the connected phone:  adb install -r $apk"
else
  echo "Build:    cd $dest && flutter build apk --release"
  echo "Install:  adb install -r build/app/outputs/flutter-apk/app-release.apk"
fi
