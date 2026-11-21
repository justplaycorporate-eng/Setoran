# Aplikasi Setoran - Android

Isi folder: `main.py` (tampilan), `logic.py` (hitungan), `buildozer.spec` (pengaturan APK).

## PENTING sebelum build
Taruh file **template_setoran.xlsx** (template Excel asli Anda) di folder yang sama dengan
`main.py`. Tanpa file itu, tombol *Ekspor Excel* akan gagal (fitur lain tetap jalan).

## Cara 1 - Tanpa Linux: pakai GitHub (paling mudah)
1. Buat akun & repository baru di github.com, upload SEMUA isi folder ini
   (termasuk folder `.github`).
2. Buka tab **Actions** > **Build APK** > **Run workflow**.
3. Tunggu 15-30 menit, lalu unduh **AplikasiSetoran-apk** di bagian Artifacts.
4. Ekstrak zip-nya, kirim file `.apk` ke HP, buka, izinkan "install dari sumber tidak dikenal".

## Cara 2 - Linux / WSL Ubuntu
    sudo apt update && sudo apt install -y git zip unzip openjdk-17-jdk python3-pip \
         autoconf libtool pkg-config zlib1g-dev libncurses5-dev libffi-dev libssl-dev
    pip install --user buildozer cython==0.29.36
    cd folder_ini
    buildozer android debug
Hasil: `bin/aplikasisetoran-1.0-arm64-v8a_armeabi-v7a-debug.apk`

## Uji di komputer dulu (opsional)
    pip install kivy openpyxl
    python main.py

## Letak file di HP
Database: penyimpanan internal aplikasi (aman, tidak hilang saat app ditutup).
Ekspor Excel & Backup: `Documents/AplikasiSetoran` (bila ditolak Android, otomatis ke folder app).
