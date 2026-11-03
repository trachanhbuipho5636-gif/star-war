@echo off
D:
powershell -Command "(Get-Content main.py) -replace '            pointer = self.win.getPointer\(0\)', '            pointer = self.win.getPointer(0)' | Set-Content main.py"
python main.py
pause