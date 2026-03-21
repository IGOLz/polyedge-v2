@echo off
setlocal

set "REPO_ROOT=%~dp0"
pushd "%REPO_ROOT%"

python scripts\btc_5m_dual_bet_redeem_debug.py %*
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
