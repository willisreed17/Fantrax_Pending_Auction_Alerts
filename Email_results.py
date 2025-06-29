import smtplib
import json
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def load_email_config():
    """Load email configuration from config.json file"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Check required email fields
        required_fields = ['smtp_server', 'smtp_port', 'sender_email', 'sender_password', 'email_to', 'email_subject']
        missing_fields = [field for field in required_fields if field not in config]
        
        if missing_fields:
            print(f"Missing email configuration fields in config.json: {missing_fields}")
            print("\nPlease add these email fields to your config.json:")
            print('  "smtp_server": "smtp.gmail.com",')
            print('  "smtp_port": 587,')
            print('  "sender_email": "your_email@gmail.com",')
            print('  "sender_password": "your_app_password",')
            print('  "email_to": "recipient@gmail.com",')
            print('  "email_cc": "optional_cc@gmail.com",')
            print('  "email_subject": "Current Fantrax Auctions - Will Process at "')
            return None
        
        # Debug: show what email_subject was loaded
        print(f"✓ Using email subject: '{config['email_subject']}'")
        
        return config
        
    except FileNotFoundError:
        print("config.json not found.")
        return None

def send_auction_email():
    """Send email with auction summary"""
    
    # Load email configuration
    config = load_email_config()
    if not config:
        return False
    
    # Check if auction_players.json exists and has data
    auction_data = None
    has_players = False
    
    if os.path.exists('auction_players.json'):
        try:
            # Read the file content first to check if it's empty
            with open('auction_players.json', 'r') as f:
                file_content = f.read().strip()
            
            # If file is completely empty or just whitespace
            if not file_content:
                print("✓ Found auction_players.json but it's empty (blank file)")
                has_players = False
            else:
                # Try to parse JSON
                auction_data = json.loads(file_content)
                
                # Check if there are any players in the data
                if isinstance(auction_data, list):
                    has_players = len(auction_data) > 0
                    print(f"✓ Found auction_players.json with {len(auction_data)} records")
                elif isinstance(auction_data, dict):
                    # If it's a dict, check if it has any meaningful data
                    has_players = len(auction_data) > 0 and any(auction_data.values())
                    print(f"✓ Found auction_players.json with dict data: {bool(has_players)}")
                else:
                    print(f"✓ Found auction_players.json with unexpected format: {type(auction_data)}")
                    has_players = False
            
        except json.JSONDecodeError as e:
            print(f"❌ auction_players.json contains invalid JSON: {e}")
            print("Treating as 'no players' scenario")
            has_players = False
        except Exception as e:
            print(f"❌ Error reading auction_players.json: {e}")
            return False
    else:
        print("❌ auction_players.json not found")
        return False
    
    # Determine email content based on whether there are players
    if has_players:
        # Check if email summary file exists for players
        if not os.path.exists('email_summary.txt'):
            print("❌ email_summary.txt not found. Run the auction scraper first.")
            return False
        
        # Read email content
        try:
            with open('email_summary.txt', 'r') as f:
                email_body = f.read()
            print(f"✓ Read email_summary.txt - {len(email_body)} characters")
        except Exception as e:
            print(f"❌ Error reading email_summary.txt: {e}")
            return False
        
        # Double-check that the email body actually contains player data
        if "Found 0 player(s)" in email_body or len(email_body.strip()) < 50:
            has_players = False
    
    # If no players, create a simple "no players" email
    if not has_players:
        email_body = f"""No players currently being bid on.

The Fantrax auction monitor checked for pending auctions but found no active bidding at this time.

Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

You will receive another alert when new auctions become available.
"""
        print("✓ No players found - sending 'no players' notification")
    
    # Extract auction deadline from email body and create custom subject
    auction_deadline = None
    deadline_match = re.search(r'Auction Deadline: (.+)', email_body)
    if deadline_match:
        auction_deadline = deadline_match.group(1).strip()
    
    # Use the custom subject from config
    base_subject = config['email_subject']
    
    # Modify subject for no-players case
    if not has_players:
        email_subject = "Fantrax Auctions - No Active Bidding"
    elif auction_deadline:
        # Convert "Jun 12, 2:00 AM" to "2am on June 12th"
        try:
            # Parse the deadline
            deadline_parts = auction_deadline.replace(',', '').split()
            if len(deadline_parts) >= 3:
                month = deadline_parts[0]  # "Jun"
                day = deadline_parts[1]    # "12"
                time_part = deadline_parts[2]  # "2:00"
                am_pm = deadline_parts[3] if len(deadline_parts) > 3 else "AM"  # "AM"
                
                # Convert month abbreviation to full name
                month_map = {
                    'Jan': 'January', 'Feb': 'February', 'Mar': 'March', 'Apr': 'April',
                    'May': 'May', 'Jun': 'June', 'Jul': 'July', 'Aug': 'August',
                    'Sep': 'September', 'Oct': 'October', 'Nov': 'November', 'Dec': 'December'
                }
                full_month = month_map.get(month, month)
                
                # Convert time to simplified format (e.g., "2:00 AM" to "2am")
                hour = time_part.split(':')[0]
                simplified_time = f"{hour}{am_pm.lower()}"
                
                # Add ordinal suffix to day
                day_int = int(day)
                if day_int in [11, 12, 13]:
                    ordinal = "th"
                elif day_int % 10 == 1:
                    ordinal = "st"
                elif day_int % 10 == 2:
                    ordinal = "nd"
                elif day_int % 10 == 3:
                    ordinal = "rd"
                else:
                    ordinal = "th"
                
                formatted_deadline = f"{simplified_time} on {full_month} {day}{ordinal}"
                email_subject = f"{base_subject}{formatted_deadline}"
            else:
                # If parsing fails, just append the raw deadline
                email_subject = f"{base_subject}{auction_deadline}"
        except:
            # If any parsing fails, just append the raw deadline
            email_subject = f"{base_subject}{auction_deadline}"
    else:
        # No deadline found, just use the base subject
        email_subject = base_subject.rstrip()
    
    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = config['sender_email']
        # Use email addresses exactly as specified in config
        msg['To'] = config['email_to']
        
        # For SMTP sending, we need individual email addresses in a list
        # Split semicolon-separated addresses for the actual sending
        to_recipients = [email.strip() for email in config['email_to'].split(';')]
        recipients = to_recipients.copy()
        
        # Add CC if specified
        if 'email_cc' in config and config['email_cc']:
            msg['Cc'] = config['email_cc']
            cc_recipients = [email.strip() for email in config['email_cc'].split(';')]
            recipients.extend(cc_recipients)
        
        msg['Subject'] = email_subject
        
        # Add body to email (NO ATTACHMENTS)
        msg.attach(MIMEText(email_body, 'plain'))
        
        # Connect to server and send email
        print(f"Connecting to {config['smtp_server']}...")
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()  # Enable encryption
        
        print("Logging in...")
        server.login(config['sender_email'], config['sender_password'])
        
        print(f"Sending email...")
        print(f"To: {config['email_to']}")
        if 'email_cc' in config and config['email_cc']:
            print(f"CC: {config['email_cc']}")
        print(f"Subject: {email_subject}")
        
        text = msg.as_string()
        server.sendmail(config['sender_email'], recipients, text)
        server.quit()
        
        print("✅ Email sent successfully!")
        
        # Log the sent email
        log_entry = f"{datetime.now().isoformat()}: Email sent to {', '.join(recipients)}"
        log_entry += f" - Subject: {email_subject}\n"
        
        with open('email_log.txt', 'a') as f:
            f.write(log_entry)
        
        return True
        
    except smtplib.SMTPAuthenticationError:
        print("❌ Email authentication failed!")
        print("For Gmail:")
        print("1. Make sure 2-factor authentication is enabled")
        print("2. Use an 'App Password' (not your regular password)")
        print("3. Check that the sender_email and sender_password in config.json are correct")
        return False
        
    except smtplib.SMTPConnectError:
        print("❌ Could not connect to email server!")
        print("Check your internet connection and SMTP server settings.")
        return False
        
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

def test_email_config():
    """Test email configuration without sending auction data"""
    config = load_email_config()
    if not config:
        return False
    
    try:
        # Create test message
        msg = MIMEMultipart()
        msg['From'] = config['sender_email']
        msg['To'] = config['email_to']
        
        # Add CC if specified
        if 'email_cc' in config and config['email_cc']:
            msg['Cc'] = config['email_cc']
            recipients = [config['email_to'], config['email_cc']]
        else:
            recipients = [config['email_to']]
        
        msg['Subject'] = "Fantrax Auction Monitor - Test Email"
        
        test_body = f"""This is a test email from your Fantrax Auction Monitor.

If you receive this email, your configuration is working correctly!

Test sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

You should receive auction alerts at this email address when players are found.
"""
        
        msg.attach(MIMEText(test_body, 'plain'))
        
        # Send test email
        print(f"Sending test email to {config['email_to']}")
        if 'email_cc' in config and config['email_cc']:
            print(f"CC: {config['email_cc']}")
            
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        server.login(config['sender_email'], config['sender_password'])
        
        text = msg.as_string()
        server.sendmail(config['sender_email'], recipients, text)
        server.quit()
        
        print("✅ Test email sent successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test email failed: {e}")
        return False

if __name__ == "__main__":
    print("Fantrax Auction Email Sender")
    print("=" * 40)
    
    # Check if this is a test run
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("Running email test...")
        test_email_config()
    else:
        print("Sending auction alert email...")
        success = send_auction_email()
        
        if success:
            print("Email sending completed successfully.")
        else:
            print("Email sending failed. Check the error messages above.")
