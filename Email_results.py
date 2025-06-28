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
            with open('auction_players.json', 'r') as f:
                auction_data = json.load(f)
            
            # Check if there are any players in the data
            if isinstance(auction_data, list):
                has_players = len(auction_data) > 0
            elif isinstance(auction_data, dict):
                # If it's a dict, check if it has any meaningful data
                has_players = len(auction_data) > 0 and any(auction_data.values())
            
            print(f"✓ Found auction_players.json with {len(auction_data) if isinstance(auction_data, list) else 'some'} records")
            
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