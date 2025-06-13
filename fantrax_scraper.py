import requests
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import re
from datetime import datetime

def find_players_being_added(text):
    """Find players being added using position-based logic"""
    lines = text.split('\n')
    POSITIONS = ['SP', 'RP', 'C', '1B', '2B', '3B', 'SS', 'OF', 'DH']
    players = []
    
    for line_num, line in enumerate(lines):
        line = line.strip()
        
        # Check if line is a position
        is_position = (line in POSITIONS or 
                      re.match(r'^(SP|RP|C|1B|2B|3B|SS|OF|DH)(,(SP|RP|C|1B|2B|3B|SS|OF|DH))+$', line))
        
        if is_position:
            # Look for player name before position
            player_name = None
            for i in range(max(0, line_num-3), line_num):
                if i < len(lines):
                    prev_line = lines[i].strip()
                    if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+$', prev_line):
                        if prev_line not in ['Free Agent', 'Agent Claims', 'Claim Budget']:
                            player_name = prev_line
                            break
            
            # Check for bid keywords near this player
            if player_name:
                context_lines = lines[max(0, line_num-3):line_num+6]
                has_bid = any(keyword in context_line for context_line in context_lines 
                             for keyword in ['BID', 'SUBMITTED', 'PTY'])
                
                if has_bid:
                    # Find team
                    team = None
                    for i in range(line_num+1, min(len(lines), line_num+5)):
                        if re.match(r'^-\s*[A-Z]{3}$', lines[i].strip()):
                            team = lines[i].strip().replace('-', '').strip()
                            break
                    
                    players.append({
                        'player_name': player_name,
                        'position': line,
                        'team': team
                    })
    
    return players

def get_auction_data():
    # Get credentials
    username = os.getenv('FANTRAX_USERNAME')
    password = os.getenv('FANTRAX_PASSWORD')
    
    if not username or not password:
        try:
            config_data = json.load(open('config.json'))
            username = config_data['username']
            password = config_data['password']
        except:
            print("Error: No credentials found")
            return []
    
    # Setup Chrome
    service = Service(ChromeDriverManager().install())
    chrome_options = webdriver.ChromeOptions()
    
    if os.getenv('GITHUB_ACTIONS'):
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        # Login
        driver.get("https://www.fantrax.com/home")
        time.sleep(3)
        
        login_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'mat-gradient')]")
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(2)
        
        wait = WebDriverWait(driver, 10)
        user_field = wait.until(EC.presence_of_element_located((By.NAME, "userOrEmail")))
        pass_field = driver.find_element(By.NAME, "password")
        
        user_field.send_keys(username)
        pass_field.send_keys(password)
        pass_field.send_keys(Keys.RETURN)
        time.sleep(3)
        
        # Get auction page
        driver.get("https://www.fantrax.com/fantasy/league/vqsvwdkem1uv2c8b/transactions/pending;teamId=ALL_TEAMS")
        time.sleep(5)
        
        # Find deadline
        page_text = driver.page_source
        deadline_match = re.search(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,?\s+\d+:\d+\s+(AM|PM)', page_text)
        auction_deadline = deadline_match.group(0) if deadline_match else None
        
        # Find players
        all_elements = driver.find_elements(By.CSS_SELECTOR, "*")
        all_players = []
        seen_players = set()
        
        for element in all_elements:
            try:
                text = element.text.strip()
                if len(text) > 20 and any(pos in text for pos in ['SP', 'RP', 'C', '1B', '2B', '3B', 'SS', 'OF', 'DH']):
                    players = find_players_being_added(text)
                    for player in players:
                        name = player['player_name'].lower()
                        if name not in seen_players:
                            seen_players.add(name)
                            all_players.append(player)
            except:
                continue
        
        print(f"Found {len(all_players)} players being added:")
        for i, player in enumerate(all_players, 1):
            print(f"  {i}. {player['player_name']} ({player['position']}) - {player.get('team', 'Unknown')}")
        
        # Save results
        with open('auction_players.json', 'w') as f:
            json.dump(all_players, f, indent=2)
        
        # Create email
        if all_players:
            deadline_text = f" - Deadline {deadline_match.group().split(',')[0]}" if deadline_match else ""
            email_text = f"Fantasy Baseball Auction Alert{deadline_text}\n\n"
            
            if auction_deadline:
                email_text += f"Auction Deadline: {auction_deadline}\n\n"
            
            email_text += f"Found {len(all_players)} player(s) being added:\n\n"
            
            for i, player in enumerate(all_players, 1):
                email_text += f"{i}. {player['player_name']}\n"
                email_text += f"   Position: {player['position']}\n"
                email_text += f"   Team: {player.get('team', 'Unknown')}\n\n"
            
            with open('email_summary.txt', 'w', encoding='utf-8') as f:
                f.write(email_text)
            
            print(f"\n✓ Saved {len(all_players)} players to files")
        
        return all_players
        
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        driver.quit()

if __name__ == "__main__":
    get_auction_data()
