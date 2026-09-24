@echo off
:: Trackmind launcher (run from source)
:: Camera IP, login and every other setting live in the app:
:: first launch walks you through setup, then use Settings (gear, top-right).
::
:: Add --browser to open the interface in your web browser instead of an
:: app window, e.g.   python autotrack.py --browser

echo Starting Trackmind...
python autotrack.py %*
if errorlevel 1 pause
