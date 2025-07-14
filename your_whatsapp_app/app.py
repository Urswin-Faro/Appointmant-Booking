# app.py
from flask import Flask, request, jsonify
import json
import os
import uuid
import datetime

from config import VERIFY_TOKEN
from database import (
    get_customer_by_phone, add_customer, get_available_services,
    get_service_by_id, get_available_time_slots, book_appointment,
    log_message, update_appointment_confirmation_id
)
from whatsapp_api import send_whatsapp_message, send_template_message

app = Flask(__name__)

# --- Webhook Verification Endpoint ---
@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print('WEBHOOK_VERIFIED')
            return challenge, 200
        else:
            return 'Verification token mismatch', 403
    return 'Missing parameters', 400

# --- Webhook for Incoming Messages ---
@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.get_json()
    print("Received Webhook Data:", json.dumps(data, indent=4))

    # Check if the webhook event is a message
    if data and data.get('object') == 'whatsapp_business_account':
        for entry in data.get('entry', []):
            for change in entry.get('changes', []):
                if change.get('field') == 'messages':
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    statuses = value.get('statuses', [])

                    # Handle incoming messages
                    for message in messages:
                        from_number = message.get('from')
                        message_type = message.get('type')
                        message_id = message.get('id')
                        timestamp = datetime.datetime.fromtimestamp(int(message.get('timestamp')))
                        
                        customer = get_customer_by_phone(from_number)
                        if not customer:
                            # Automatically add new customer if not found
                            print(f"New customer: {from_number}. Adding to DB.")
                            # You might want to ask for their name here via WhatsApp first
                            customer_id = add_customer(from_number, f"User_{from_number[-4:]}") # Generic name for now
                        else:
                            customer_id = customer['customer_id']

                        # Log the incoming message
                        log_message(message_id, 'inbound', customer_id, timestamp, json.dumps(message), data)

                        if message_type == 'text':
                            text_body = message['text']['body'].lower()
                            handle_text_message(from_number, customer_id, text_body)
                        elif message_type == 'interactive':
                            # Handle interactive replies (e.g., button clicks, list selections)
                            interactive_data = message['interactive']
                            handle_interactive_message(from_number, customer_id, interactive_data)
                        else:
                            send_whatsapp_message(from_number, "I can only process text messages and interactive selections for now. How can I help you book an appointment?")
                    
                    # Handle message status updates (e.g., delivered, read)
                    for status in statuses:
                        print(f"Message Status Update: {status.get('status')} for message ID {status.get('id')}")
                        # You can update your messages_log table here with status changes
                        # e.g., update messages_log SET status = 'delivered' WHERE whatsapp_message_id = status.get('id')
                        log_message(status.get('id'), 'outbound_status_update', None, datetime.datetime.fromtimestamp(int(status.get('timestamp'))), json.dumps(status), data)


    return 'OK', 200

# --- Message Handling Logic ---
conversation_states = {} # A simple in-memory store for conversation state for a beta

def handle_text_message(from_number, customer_id, text_body):
    current_state = conversation_states.get(from_number, {'step': 'start'})

    if "hello" in text_body or "hi" in text_body or "start" in text_body:
        send_whatsapp_message(from_number, "Hello! Welcome to our appointment booking service. How can I help you?")
        # Offer options like "Book Appointment", "View My Appointments", "Services"
        # Using interactive buttons is much better here
        send_interactive_main_menu(from_number)
        conversation_states[from_number] = {'step': 'main_menu'}
    elif current_state['step'] == 'select_service_text_input':
        # User is typing service name (less ideal than interactive lists)
        services = get_available_services()
        matched_service = next((s for s in services if s['name'].lower() == text_body), None)
        if matched_service:
            conversation_states[from_number] = {
                'step': 'select_date',
                'service_id': matched_service['service_id'],
                'service_name': matched_service['name'],
                'duration': matched_service['duration_minutes']
            }
            send_whatsapp_message(from_number, f"Great! You selected {matched_service['name']}. Please provide the date you'd like to book (YYYY-MM-DD):")
        else:
            send_whatsapp_message(from_number, "Sorry, I couldn't find that service. Please try again or type 'services' to see the list.")
    elif current_state['step'] == 'select_date':
        try:
            selected_date = datetime.datetime.strptime(text_body, "%Y-%m-%d").date()
            if selected_date < datetime.date.today():
                send_whatsapp_message(from_number, "You cannot book an appointment in the past. Please provide a future date (YYYY-MM-DD):")
                return
            
            # Fetch and display available time slots
            service_duration = current_state['duration']
            available_slots = get_available_time_slots(service_duration, selected_date.strftime("%Y-%m-%d"))

            if available_slots:
                send_whatsapp_message(from_number, f"Available slots for {current_state['service_name']} on {selected_date.strftime('%Y-%m-%d')}:")
                # Send as a list or buttons
                slot_options = [{"id": f"book_slot_{selected_date.strftime('%Y-%m-%d')} {slot}", "title": slot} for slot in available_slots]
                send_interactive_list_message(from_number, "Choose a time slot:", "Available Times", slot_options)
                
                conversation_states[from_number]['step'] = 'select_time'
                conversation_states[from_number]['selected_date'] = selected_date.strftime("%Y-%m-%d")
            else:
                send_whatsapp_message(from_number, "No slots available for that date. Please try another date or type 'cancel' to start over.")
        except ValueError:
            send_whatsapp_message(from_number, "Invalid date format. Please use YYYY-MM-DD.")
    elif "cancel" in text_body:
        send_whatsapp_message(from_number, "Okay, booking cancelled. How else can I help you?")
        conversation_states.pop(from_number, None) # Clear state
        send_interactive_main_menu(from_number) # Go back to main menu
    else:
        send_whatsapp_message(from_number, "I'm not sure how to respond to that. Please type 'hi' to start over or 'cancel' to stop.")
        send_interactive_main_menu(from_number)
        conversation_states.pop(from_number, None) # Clear state if unknown input


def handle_interactive_message(from_number, customer_id, interactive_data):
    current_state = conversation_states.get(from_number, {'step': 'start'})
    message_type = interactive_data.get('type')

    if message_type == 'button':
        button_id = interactive_data['button_reply']['id']
        handle_button_click(from_number, customer_id, button_id, current_state)
    elif message_type == 'list':
        list_id = interactive_data['list_reply']['id']
        handle_list_selection(from_number, customer_id, list_id, current_state)

def handle_button_click(from_number, customer_id, button_id, current_state):
    if button_id == 'book_appointment':
        services = get_available_services()
        if services:
            # Prepare interactive list message for services
            service_options = [{"id": s['service_id'], "title": s['name']} for s in services]
            send_interactive_list_message(from_number, "Please select a service:", "Our Services", service_options)
            conversation_states[from_number] = {'step': 'select_service'}
        else:
            send_whatsapp_message(from_number, "Sorry, no services are currently available.")
    elif button_id == 'view_appointments':
        send_whatsapp_message(from_number, "This feature is coming soon! For now, please contact us directly to view your appointments.")
        send_interactive_main_menu(from_number)
        conversation_states.pop(from_number, None)
    elif button_id == 'get_help':
        send_whatsapp_message(from_number, "Please type your question or call us at [Your Phone Number].")
        send_interactive_main_menu(from_number)
        conversation_states.pop(from_number, None)


def handle_list_selection(from_number, customer_id, list_id, current_state):
    if current_state['step'] == 'select_service':
        service_id = list_id
        service = get_service_by_id(service_id)
        if service:
            conversation_states[from_number] = {
                'step': 'select_date',
                'service_id': service['service_id'],
                'service_name': service['name'],
                'duration': service['duration_minutes']
            }
            send_whatsapp_message(from_number, f"You've selected {service['name']}. Now, please enter the desired date for your appointment in YYYY-MM-DD format (e.g., 2025-07-20).")
        else:
            send_whatsapp_message(from_number, "Invalid service selected. Please try again.")
            send_interactive_main_menu(from_number) # Reset
            conversation_states.pop(from_number, None)

    elif current_state['step'] == 'select_time':
        # list_id will contain something like "book_slot_2025-07-20 09:00"
        try:
            full_datetime_str = list_id.replace("book_slot_", "")
            
            # Ensure the service details are in the state
            if 'service_id' not in current_state or 'duration' not in current_state:
                send_whatsapp_message(from_number, "Oops, something went wrong with the service selection. Please start over.")
                send_interactive_main_menu(from_number)
                conversation_states.pop(from_number, None)
                return

            appointment_id = book_appointment(
                customer_id,
                current_state['service_id'],
                full_datetime_str,
                current_state['duration'],
                from_number # Using from_number as conversation_id for simplicity here
            )

            if appointment_id:
                confirmation_msg = f"Your {current_state['service_name']} appointment is confirmed for {full_datetime_str} (SAST). We look forward to seeing you!"
                sent_msg_id = send_whatsapp_message(from_number, confirmation_msg)
                if sent_msg_id:
                    update_appointment_confirmation_id(appointment_id, sent_msg_id)
                send_whatsapp_message(from_number, "Is there anything else I can assist you with?")
                send_interactive_main_menu(from_number) # Go back to main menu
                conversation_states.pop(from_number, None) # Clear state
            else:
                send_whatsapp_message(from_number, "Sorry, that time slot is no longer available or there was an issue booking. Please try another time or date.")
                # Re-offer slots or main menu
                send_interactive_main_menu(from_number)
                conversation_states.pop(from_number, None)

        except Exception as e:
            print(f"Error processing time slot selection: {e}")
            send_whatsapp_message(from_number, "There was an error processing your request. Please try again or type 'cancel'.")
            send_interactive_main_menu(from_number)
            conversation_states.pop(from_number, None)

# --- Helper functions for sending interactive messages ---
def send_interactive_main_menu(to_number):
    buttons = [
        {"type": "reply", "reply": {"id": "book_appointment", "title": "Book Appointment"}},
        {"type": "reply", "reply": {"id": "view_appointments", "title": "View My Appointments"}},
        {"type": "reply", "reply": {"id": "get_help", "title": "Get Help"}}
    ]
    interactive_body = {
        "type": "button",
        "body": {"text": "How can I help you today?"},
        "action": {"buttons": buttons}
    }
    send_whatsapp_message(to_number, interactive_body, message_type="interactive")

def send_interactive_list_message(to_number, header_text, button_text, sections_data):
    # sections_data is a list of {"id": "...", "title": "..."} for list items
    list_sections = [
        {
            "rows": sections_data
        }
    ]
    interactive_body = {
        "type": "list",
        "header": {"type": "text", "text": header_text},
        "body": {"text": "Please choose from the following:"},
        "action": {
            "button": button_text,
            "sections": list_sections
        }
    }
    send_whatsapp_message(to_number, interactive_body, message_type="interactive")


if __name__ == '__main__':
    # Load environment variables for local testing
    from dotenv import load_dotenv
    load_dotenv()
    
    # You'll need to set these in your .env file:
    # WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
    # WHATSAPP_ACCESS_TOKEN=your_permanent_access_token
    # WHATSAPP_VERIFY_TOKEN=your_custom_verify_token
    # DB_HOST=localhost
    # DB_USER=your_mysql_user
    # DB_PASSWORD=your_mysql_password
    # DB_NAME=whatsapp_booking

    # For local development, Flask runs on HTTP.
    # For production, you MUST use HTTPS (e.g., via Nginx, Apache, or a cloud service).
    app.run(host='0.0.0.0', port=5000, debug=True)