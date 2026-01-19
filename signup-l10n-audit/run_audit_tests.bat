@echo off
REM Automated Sign-Up Localization Audit Test Suite
REM Tests 4 sites with Spanish locale and saves results to file

SETLOCAL EnableDelayedExpansion

REM Set output file with timestamp
set OUTPUT_FILE=audit_results_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%.txt
set OUTPUT_FILE=%OUTPUT_FILE: =0%

echo ========================================== > %OUTPUT_FILE%
echo SIGN-UP LOCALIZATION AUDIT TEST SUITE >> %OUTPUT_FILE%
echo ========================================== >> %OUTPUT_FILE%
echo Test Date: %date% %time% >> %OUTPUT_FILE%
echo Target Locale: Spanish (es) >> %OUTPUT_FILE%
echo ========================================== >> %OUTPUT_FILE%
echo. >> %OUTPUT_FILE%

REM Test sites
set SITES=www.shopify.com www.stripe.com www.amazon.com www.bbc.com www.netflix.com www.walmart.com www.cnn.com www.openai.com www.microsoft.com www.anthropic.com

echo Starting automated test suite...
echo Results will be saved to: %OUTPUT_FILE%
echo.
echo Testing 10 major websites for signup localization...
echo.

set COUNT=0
for %%S in (%SITES%) do (
    set /a COUNT+=1
    echo.
    echo [!COUNT!/10] Testing %%S...
    echo ========================================== >> %OUTPUT_FILE%
    echo TEST !COUNT!: %%S >> %OUTPUT_FILE%
    echo ========================================== >> %OUTPUT_FILE%
    
    REM Run the audit script with site and locale
    (echo %%S && echo es) | python signup_localization_audit_v2_integrated.py >> %OUTPUT_FILE% 2>&1
    
    echo. >> %OUTPUT_FILE%
    echo ------------------------------------------ >> %OUTPUT_FILE%
    echo. >> %OUTPUT_FILE%
)

echo.
echo ========================================== >> %OUTPUT_FILE%
echo TEST SUITE COMPLETED >> %OUTPUT_FILE%
echo ========================================== >> %OUTPUT_FILE%

echo.
echo Test suite completed!
echo Results saved to: %OUTPUT_FILE%
echo.
echo Opening results file...
notepad %OUTPUT_FILE%

ENDLOCAL
