@echo off
cd /d "C:\Users\willi\OneDrive\Documents\VS Code Projects\Python scripts\Web Scrapping\Fantrax"
echo Starting Fantrax Auction Monitor...

echo Running scraper...
"C:\Users\willi\anaconda3\python.exe" Fantrax_Scrape_Process.py

echo Running email sender...
"C:\Users\willi\anaconda3\python.exe" Email_Results.py

echo Auction monitor complete.
