import requests
import json
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

def parse_auction_data(raw_text):
    """Parse auction text into structured data"""
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    data = {}
    
    # Find player name (first "First Last" pattern that isn't a position combo)
    for i, line in enumerate(lines):
        if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', line):
            # Skip position combinations like "SP,RP" or "1B,3B,OF"
            if not re.match(r'^(SP|RP|C|1B|2B|3B|SS|OF|DH|P)(,(SP|RP|C|1B|2B|3B|SS|OF|DH|P))*$', line):
                data['player_name'] = line.strip()
                # Only look at next 8 lines to avoid other players' data
                relevant_lines = lines[i:i+8]
                break
    else:
        return data  # No valid player name found
    
    # Extract position, team, and time from relevant lines only
    positions = []
    for line in relevant_lines:
        if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', line) and line != data['player_name']:
            break  # Stop at next player name
        
        # Find positions
        positions.extend(re.findall(r'\b(SP|RP|C|1B|2B|3B|SS|OF|DH)\b', line))
        
        # Find team (3-letter code, excluding common words)
        if 'team' not in data:
            teams = re.findall(r'\b([A-Z]{3})\b', line)
            for team in teams:
                if team not in {'BID', 'PTY', 'POS', 'STA', 'DEL', 'CDT'}:
                    data['team'] = team
                    break
        
        # Find bid time
        if 'bid_time' not in data:
            time_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,?\s+\d+:\d+\s+(AM|PM)', line)
            if time_match:
                data['bid_time'] = time_match.group(0)
    
    # Set positions
    if positions:
        data['position'] = positions[0]
        unique_pos = list(set(positions))
        if len(unique_pos) > 1:
            data['positions'] = unique_pos
    
    return data

def get_auction_data():
    # Load config
    try:
        config_data = json.load(open('config.json'))
    except Exception as e:
        print(f"Error loading config.json: {e}")
        return []
    
    print("=== Fantrax Auction Monitor ===")
    
    # Setup Chrome
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service)
    
    try:
        # Login
        driver.get("https://www.fantrax.com/home")
        time.sleep(3)
        
        print("Logging in...")
        login_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'mat-gradient')]")
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(2)
        
        wait = WebDriverWait(driver, 10)
        user_field = wait.until(EC.presence_of_element_located((By.NAME, "userOrEmail")))
        pass_field = driver.find_element(By.NAME, "password")
        
        user_field.clear()
        user_field.send_keys(config_data['username'])
        pass_field.clear()
        pass_field.send_keys(config_data['password'])
        pass_field.send_keys(Keys.RETURN)
        time.sleep(3)
        
        print("✓ Login successful")
        
        # Navigate to auctions
        print("Getting auction data...")
        driver.get("https://www.fantrax.com/fantasy/league/vqsvwdkem1uv2c8b/transactions/pending;teamId=ALL_TEAMS")
        time.sleep(5)
        
        # Find all elements with substantial text
        all_elements = driver.find_elements(By.CSS_SELECTOR, "*")
        auction_data = []
        seen_texts = set()
        auction_deadline = None  # Track the auction deadline
        
        print("Searching for auction deadline...")
        
        for element in all_elements:
            try:
                text = element.text.strip()
                
                # Check ALL text for "Free Agent Claims" deadline (separate from player filtering)
                if text and len(text) > 5:
                    # Look for multiple patterns that might contain the deadline
                    if ("Free Agent Claims" in text or 
                        "Claims" in text or 
                        "Deadline" in text or
                        "Jun 12" in text or
                        "6/12" in text):
                        
                        print(f"Found potential deadline text: {text[:100]}...")
                        parsed_deadline = parse_auction_data(text)
                        
                        if parsed_deadline.get('bid_time'):
                            print(f"  - Extracted bid_time: {parsed_deadline.get('bid_time')}")
                            if parsed_deadline.get('player_name'):
                                print(f"  - Player name: {parsed_deadline.get('player_name')}")
                            
                            # Accept any deadline date found (not just from "Free Agent Claims")
                            if not auction_deadline:  # Take the first deadline found
                                auction_deadline = parsed_deadline.get('bid_time')
                                print(f"✓ Set auction deadline: {auction_deadline}")
                
                # Original player filtering logic (unchanged)
                if (text and len(text) > 20 and text not in seen_texts and
                    any(pos in text for pos in ['SP', 'RP', 'C', '1B', '2B', '3B', 'SS', 'OF', 'DH'])):
                    
                    seen_texts.add(text)
                    parsed = parse_auction_data(text)
                    
                    if (parsed.get('player_name') and parsed.get('position') and parsed.get('team')):
                        auction_data.append(parsed)
            except:
                continue
        
        if not auction_deadline:
            print("❌ No auction deadline found")
        
        # Remove duplicates and clean
        clean_players = []
        seen_names = set()
        
        for player in auction_data:
            name = player['player_name'].lower()
            
            # Skip generic terms and position codes
            if (name in ['pending transactions', 'fantasy advice', 'roster', 'players'] or
                re.match(r'^(SP|RP|C|1B|2B|3B|SS|OF|DH)(,(SP|RP|C|1B|2B|3B|SS|OF|DH))*$', player['player_name']) or
                name in seen_names):
                continue
                
            seen_names.add(name)
            clean_players.append(player)
        
        print(f"Found {len(clean_players)} auction players:")
        
        # Display and save results
        for i, player in enumerate(clean_players, 1):
            positions = f"({'/'.join(player.get('positions', [player.get('position')]))})"
            print(f"  {i}. {player['player_name']} {positions} - {player['team']} - {player.get('bid_time', 'Unknown time')}")
        
        # Save data
        with open('auction_players.json', 'w') as f:
            json.dump(clean_players, f, indent=2)
        
        # Create email summary
        if clean_players:
            # Format deadline for subject if found
            deadline_text = ""
            if auction_deadline:
                deadline_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+', auction_deadline)
                if deadline_match:
                    deadline_text = f" - Deadline {deadline_match.group(0)}"
            
            email_text = f"Fantasy Baseball Auction Alert{deadline_text} - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            
            # Add deadline to body if found (without emoji to avoid encoding issues)
            if auction_deadline:
                email_text += f"Auction Deadline: {auction_deadline}\n\n"
            
            email_text += f"Found {len(clean_players)} player(s) up for auction:\n\n"
            
            for i, player in enumerate(clean_players, 1):
                email_text += f"{i}. {player['player_name']}\n"
                email_text += f"   Position: {player['position']}\n"
                email_text += f"   Team: {player['team']}\n"
                email_text += f"   Bid Time: {player.get('bid_time', 'Unknown')}\n\n"
            
            # Write with UTF-8 encoding to handle any special characters
            with open('email_summary.txt', 'w', encoding='utf-8') as f:
                f.write(email_text)
            
            print(f"\n✓ Saved to auction_players.json and email_summary.txt")
            if auction_deadline:
                print(f"✓ Auction deadline: {auction_deadline}")
        
        return clean_players
        
        return clean_players
        
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        driver.quit()

if __name__ == "__main__":
    print("Starting Fantrax Auction Monitor...")
    players = get_auction_data()
    
    if players:
        print("\nEmail summary:")
        print("="*50)
        with open('email_summary.txt', 'r', encoding='utf-8') as f:
            print(f.read())
    else:
        print("No auction players found.")
    
    print("Done.")