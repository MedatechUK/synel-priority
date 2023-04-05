pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --noconsole update_all_clockings.py
pyinstaller --onefile --noconsole app.py
