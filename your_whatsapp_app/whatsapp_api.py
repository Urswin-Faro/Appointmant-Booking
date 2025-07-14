# whatsapp_api.py
import requests
import json
from config import WHATSAPP_API_URL, PHONE_NUMBER_ID, ACCESS_TOKEN

def send_whatsapp_message(to_number, message_body, message_type="text"):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": message_type,
    }

    if message_type == "text":
        payload["text"] = {"body": message_body}
    elif message_type == "interactive":
        # Example for interactive message (buttons/lists)
        # This will be more complex and depend on the specific interactive type
        # For a simple text input, use 'text' type above.
        # For buttons, you'd define the button object:
        # payload["interactive"] = {
        #     "type": "button",
        #     "body": {"text": message_body},
        #     "action": {"buttons": [{"type": "reply", "reply": {"id": "unique_id", "title": "Button Text"}}]}
        # }
        payload["interactive"] = message_body # message_body would be a dict for interactive

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        response_data = response.json()
        print(f"WhatsApp API Response: {json.dumps(response_data, indent=4)}")
        return response_data.get('messages', [])[0].get('id') if response_data.get('messages') else None
    except requests.exceptions.RequestException as e:
        print(f"Error sending WhatsApp message: {e}")
        print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
        return None

def send_template_message(to_number, template_name, components=None, language_code="en_US"):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{WHATSAPP_API_URL}/{PHONE_NUMBER_ID}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components if components else []
        }
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        response_data = response.json()
        print(f"Template Message Response: {json.dumps(response_data, indent=4)}")
        return response_data.get('messages', [])[0].get('id') if response_data.get('messages') else None
    except requests.exceptions.RequestException as e:
        print(f"Error sending template message: {e}")
        print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
        return None