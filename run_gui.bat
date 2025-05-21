@echo off
REM Set the name of your conda environment
set ENV_NAME=myenvname

REM Set the path to your Anaconda/Miniconda installation
REM Modify this if your installation is not in the default location
set CONDA_PATH=%USERPROFILE%\miniconda3

REM Initialize conda (this sets up the conda command in the script)
call "%CONDA_PATH%\Scripts\activate.bat"

REM Activate the environment
conda activate %ENV_NAME%

REM Run your GUI script
python "C:\path\to\your\gui.py"

REM Optional: pause so the window stays open if there's an error
pause
