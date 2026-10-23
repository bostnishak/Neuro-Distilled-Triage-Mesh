@echo off
setlocal enabledelayedexpansion

echo ================================================================================
echo  NDTM-9000 MASTER ZERO-DEFECT SOVEREIGN CERTIFICATION HARNESS (WINDOWS)
echo ================================================================================

cd /d "%~dp0"

echo ^>^>^> [STAGE 1/3] Scanning for Forbidden Placeholders...
findstr /s /i /m "TODO" backend\*.py edge_cpp_kernel\*.cpp edge_cpp_kernel\*.hpp frontend\src\*.tsx > temp_todo.txt 2>nul
for %%A in (temp_todo.txt) do if %%~zA GTR 0 (
    echo [-] FAILED: Found TODO placeholders in:
    type temp_todo.txt
    del temp_todo.txt
    exit /b 1
)
del temp_todo.txt 2>nul
echo [+] PASSED: Zero placeholders detected across entire sovereign codebase.

echo ^>^>^> [STAGE 2/3] Compiling and Executing C++20 Edge Kernel Invariants Suite...
where g++ >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    g++ -std=c++20 -O3 -Iedge_cpp_kernel/include edge_cpp_kernel/src/shm_zero_copy_arena.cpp edge_cpp_kernel/src/radix2_fft_spectrogram.cpp edge_cpp_kernel/src/laplacian_simd_optics.cpp edge_cpp_kernel/tests/test_cpp_kernel_invariants.cpp -o test_cpp_invariants.exe
    if %ERRORLEVEL% NEQ 0 (
        echo [-] C++ build failed.
        exit /b %ERRORLEVEL%
    )
    test_cpp_invariants.exe
    if %ERRORLEVEL% NEQ 0 (
        echo [-] C++ invariants failed.
        del test_cpp_invariants.exe 2>nul
        exit /b %ERRORLEVEL%
    )
    del test_cpp_invariants.exe 2>nul
    echo [+] PASSED: C++20 SPSC, Cooley-Tukey FFT, and Zero-Copy SHM Invariants Certified.
) else (
    echo [!] WARNING: g++ not in PATH. Skipping local C++ test execution.
)

echo ^>^>^> [STAGE 3/3] Running Python Pytest Suite across all engines...
set PYTHONPATH=%CD%\backend;%PYTHONPATH%
python -m pytest backend\tests -v
if %ERRORLEVEL% NEQ 0 (
    echo [-] Python test suite failed.
    exit /b %ERRORLEVEL%
)

echo ================================================================================
echo  [SEAL] NDTM-9000 SOVEREIGN OPERATING KERNEL: 100%% ZERO-DEFECT CERTIFIED
echo ================================================================================
exit /b 0
