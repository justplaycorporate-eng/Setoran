[app]
title = Aplikasi Setoran
package.name = aplikasisetoran
package.domain = org.setoran
source.dir = .
source.include_exts = py,png,jpg,xlsx
source.exclude_patterns = smoke.py,shot.py,app_desktop_lama.py,*.png,out.txt
version = 1.0
requirements = python3,kivy==2.3.0,sqlite3,openpyxl,et_xmlfile
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
