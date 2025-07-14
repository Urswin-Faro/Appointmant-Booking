# database.py
import mysql.connector
import uuid
from config import DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

def add_customer(phone_number, name):
    conn = get_db_connection()
    cursor = conn.cursor()
    customer_id = str(uuid.uuid4()) # Generate UUID for new customer
    try:
        cursor.execute(
            "INSERT INTO customers (customer_id, whatsapp_phone_number, name) VALUES (%s, %s, %s)",
            (customer_id, phone_number, name)
        )
        conn.commit()
        return customer_id
    except mysql.connector.Error as err:
        if err.errno == 1062: # Duplicate entry for unique phone number
            print(f"Customer with phone number {phone_number} already exists.")
            # Retrieve existing customer_id
            cursor.execute("SELECT customer_id FROM customers WHERE whatsapp_phone_number = %s", (phone_number,))
            customer_id = cursor.fetchone()[0]
            return customer_id
        else:
            print(f"Error: {err}")
            conn.rollback()
            return None
    finally:
        cursor.close()
        conn.close()

def get_customer_by_phone(phone_number):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True) # Return rows as dictionaries
    try:
        cursor.execute("SELECT * FROM customers WHERE whatsapp_phone_number = %s", (phone_number,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_available_services():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT service_id, name, duration_minutes, price FROM services ORDER BY name")
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

def get_service_by_id(service_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT service_id, name, duration_minutes FROM services WHERE service_id = %s", (service_id,))
        return cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

def get_available_time_slots(service_duration_minutes, date):
    # This is a simplified example. Real-world availability is complex.
    # It should check staff availability, existing appointments, working hours etc.
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Example: Find existing appointments for the given date
        # You'd then subtract these from your total available slots
        cursor.execute(
            """
            SELECT start_time, end_time FROM appointments
            WHERE DATE(start_time) = %s AND status IN ('pending', 'confirmed')
            """, (date,)
        )
        booked_slots = cursor.fetchall()

        # For a beta, let's just generate some dummy slots
        # In production, you'd have proper logic for availability based on staff, capacity, etc.
        available_slots = []
        import datetime
        start_of_day = datetime.datetime.strptime(f"{date} 09:00:00", "%Y-%m-%d %H:%M:%S")
        end_of_day = datetime.datetime.strptime(f"{date} 17:00:00", "%Y-%m-%d %H:%M:%S")
        
        current_time_slot = start_of_day
        while current_time_slot + datetime.timedelta(minutes=service_duration_minutes) <= end_of_day:
            is_booked = False
            for booked in booked_slots:
                # Simple overlap check - needs more robust logic for real app
                if not (current_time_slot >= booked['end_time'] or current_time_slot + datetime.timedelta(minutes=service_duration_minutes) <= booked['start_time']):
                    is_booked = True
                    break
            
            if not is_booked:
                available_slots.append(current_time_slot.strftime("%H:%M"))
            
            current_time_slot += datetime.timedelta(minutes=service_duration_minutes) # Move to next possible slot
            # Or
            # current_time_slot += datetime.timedelta(minutes=15) # Example: check every 15 min

        return available_slots
    finally:
        cursor.close()
        conn.close()

def book_appointment(customer_id, service_id, start_time_str, duration_minutes, whatsapp_conversation_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    appointment_id = str(uuid.uuid4())
    try:
        import datetime
        start_time = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
        end_time = start_time + datetime.timedelta(minutes=duration_minutes)

        # Basic check for overlapping appointments for the same service/staff if applicable
        # This needs to be more robust for production! (e.g., ACID transactions, proper locking)
        cursor.execute(
            """
            SELECT COUNT(*) FROM appointments
            WHERE service_id = %s
            AND (
                (start_time < %s AND end_time > %s) OR
                (start_time >= %s AND start_time < %s)
            )
            AND status IN ('pending', 'confirmed')
            """,
            (service_id, end_time, start_time, start_time, end_time)
        )
        if cursor.fetchone()[0] > 0:
            print("Slot already booked or overlaps.")
            return None # Indicate booking failed due to overlap

        cursor.execute(
            "INSERT INTO appointments (appointment_id, customer_id, service_id, start_time, end_time, status, whatsapp_conversation_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (appointment_id, customer_id, service_id, start_time, end_time, 'confirmed', whatsapp_conversation_id)
        )
        conn.commit()
        return appointment_id
    except Exception as e:
        print(f"Error booking appointment: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()

def log_message(whatsapp_message_id, direction, customer_id, timestamp, message_content, raw_json_payload):
    conn = get_db_connection()
    cursor = conn.cursor()
    message_log_id = str(uuid.uuid4())
    try:
        cursor.execute(
            """
            INSERT INTO messages_log (message_log_id, whatsapp_message_id, direction, customer_id, timestamp, message_content, raw_json_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (message_log_id, whatsapp_message_id, direction, customer_id, timestamp, message_content, raw_json_payload)
        )
        conn.commit()
    except Exception as e:
        print(f"Error logging message: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def update_appointment_confirmation_id(appointment_id, message_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE appointments SET confirmation_message_id = %s WHERE appointment_id = %s",
            (message_id, appointment_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error updating confirmation message ID: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()