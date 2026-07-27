@echo off
setlocal
title Novel Assistant - Frontend App
echo Starting React/Vite Frontend Server...
pushd "%~dp0frontend"
npm run dev
popd
pause
endlocal
