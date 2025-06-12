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

def parse_auction_data(raw_text):
    """Parse auction text into structured data"""
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    data = {}
    
    # Find all player names first
    all_player_names = []
    for i, line in enumerate(lines):
        if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', line):
            # Skip position combinations like "SP,RP" or "1B,3B,OF"
            if not re.match(r'^(SP|RP|C|1B|2B|3B|SS|OF|DH|P)(,(SP|RP|C|1B|2B|3B|SS|OF|DH|P))*$', line):
                all_player_names.append((i, line.strip()))
    
    if not all_player_names:
        return data  # No valid player name found
    
    # First player is the one being claimed
    data['player_name'] = all_player_names[0][1]
    # Only look at next 8 lines to avoid other players' data
    relevant_lines = lines[all_player_names[0][0]:all_player_names[0][0]+8]
    
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
    
    # Set positions - combine all unique positions into single field
    if positions:
        unique_pos = list(set(positions))
        if len(unique_pos) > 1:
            data['position'] = '/'.join(unique_pos)
        else:
            data['position'] = positions[0]
    
    # If there are multiple players, need to determine which is claim vs drop
    if len(all_player_names) > 1:
        # Simple approach: look at the position of players in the transaction text
        # In Fantrax, the pattern is usually: Claimed Player ... transaction info ... Dropped Player
        
        # Check if this looks like a claim/drop transaction by looking for bid keywords
        has_transaction_keywords = any(keyword in raw_text for keyword in ['BID', 'SUBMITTED', 'PTY'])
        
        if has_transaction_keywords:
            # First player mentioned is usually the claim, last player is the drop
            claimed_player = all_player_names[0][1]
            dropped_player = all_player_names[-1][1]
            
            # Make sure they're different players
            if claimed_player != dropped_player:
                data['player_name'] = claimed_player
                data['drop_player'] = dropped_player
                
                # Use the first player's details for the main transaction
                # (the relevant_lines are already set for the first player above)
            else:
                # Same player mentioned twice, treat as single claim
                data['player_name'] = claimed_player
        else:
            # No clear transaction keywords, treat first player as claim
            data['player_name'] = all_player_names[0][1]
    
    return data

def get_auction_data():
    # Load config from environment variables (GitHub Actions) or config file (local)
    username = os.getenv('FANTRAX_USERNAME')
    password = os.getenv('FANTRAX_PASSWORD')
    
    if not username or not password:
        # Fallback to config.json for local development
        try:
            config_data = json.load(open('config.json'))
            username = config_data['username']
            password = config_data['password']
            print("Using config.json for credentials")
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return []
    else:
        print("Using environment variables for credentials")
    
    print("=== Fantrax Auction Monitor ===")
    
    # Setup Chrome with options for both local and headless (GitHub Actions)
    service = Service(ChromeDriverManager().install())
    chrome_options = webdriver.ChromeOptions()
    
    # Add headless options for GitHub Actions
    if os.getenv('GITHUB_ACTIONS'):
        print("Running in GitHub Actions - using headless mode")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
    
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
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
        user_field.send_keys(username)
        pass_field.clear()
        pass_field.send_keys(password)
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
                    # Look for "Free Agent Claims" followed by deadline
                    if "Free Agent Claims" in text:
                        print(f"Found potential deadline text: {text[:100]}...")
                        
                        # Look for deadline time in format "Day Month DD, H:MM AM/PM CDT" (the actual deadline)
                        deadline_match = re.search(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,?\s+\d+:\d+\s+(AM|PM)', text)
                        if deadline_match and not auction_deadline:
                            auction_deadline = deadline_match.group(0)
                            print(f"✓ Set auction deadline from day-format: {auction_deadline}")
                            continue
                        
                        # Fallback: look for any time pattern but only if it's NOT associated with a player bid
                        if not auction_deadline:
                            parsed_deadline = parse_auction_data(text)
                            if parsed_deadline.get('bid_time') and not parsed_deadline.get('player_name'):
                                # Only use as deadline if no player name (meaning it's not a bid time)
                                auction_deadline = parsed_deadline.get('bid_time')
                                print(f"✓ Set auction deadline from time-only: {auction_deadline}")
                
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
        
        # First, collect all players being dropped
        dropped_players = set()
        for player in auction_data:
            if player.get('drop_player'):
                dropped_players.add(player['drop_player'].lower())
        
        for player in auction_data:
            name = player['player_name'].lower()
            
            # Skip generic terms, position codes, and players being dropped
            if (name in ['pending transactions', 'fantasy advice', 'roster', 'players'] or
                re.match(r'^(SP|RP|C|1B|2B|3B|SS|OF|DH)(,(SP|RP|C|1B|2B|3B|SS|OF|DH))*$', player['player_name']) or
                name in seen_names or
                name in dropped_players):
                continue
                
            seen_names.add(name)
            clean_players.append(player)
        
        print(f"Found {len(clean_players)} auction players:")
        
        # Display and save results
        for i, player in enumerate(clean_players, 1):
            drop_info = f" (dropping {player['drop_player']})" if player.get('drop_player') else ""
            print(f"  {i}. {player['player_name']} ({player.get('position')}) - {player['team']} - {player.get('bid_time', 'Unknown time')}{drop_info}")
        
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
                email_text += f"   Position: {player.get('position', 'Unknown')}\n"
                email_text += f"   Team: {player.get('team', 'Unknown')}\n"
                if player.get('drop_player'):
                    email_text += f"   Dropping: {player['drop_player']}\n"
                email_text += "\n"
            
            # Write with UTF-8 encoding to handle any special characters
            with open('email_summary.txt', 'w', encoding='utf-8') as f:
                f.write(email_text)
            
            print(f"\n✓ Saved to auction_players.json and email_summary.txt")
            if auction_deadline:
                print(f"✓ Auction deadline: {auction_deadline}")
        
        return clean_players
        
    except Exception as e:
        print(f"Error: {e}")
        return []
    finally:
        driver.quit()

if __name__ == "__main__":
    try:
        print("Starting Fantrax Auction Monitor...")
        print(f"Python working directory: {os.getcwd()}")
        print(f"Files in directory: {os.listdir('.')}")
        
        players = get_auction_data()
        
        if players:
            print("\nEmail summary:")
            print("="*50)
            try:
                with open('email_summary.txt', 'r', encoding='utf-8') as f:
                    print(f.read())
            except FileNotFoundError:
                print("email_summary.txt not found")
        else:
            print("No auction players found.")
        
        print("Done.")
        
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
