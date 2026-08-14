@echo off
setlocal
cd /d "%~dp0.."

echo.
echo ========================================
echo Tony AI - SDD Architecture Audit
echo ========================================
echo.

bun run tools/validate-sdd-flow.ts
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo AUDIT PASSED
) else (
  echo AUDIT FAILED - review the output above
)

exit /b %EXIT_CODE%
