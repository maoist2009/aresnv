@echo off
title ares-nv guided repair
rem Single entry point: paths are configured inside the wizard (first run).
cd /d %~dp0
python tools\guided_repair.py
pause
