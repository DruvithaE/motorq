from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import uuid # to generate a unique booking id


app = Flask(__name__)

conferences = {}
users = {}
bookings = {}
waitlists = {}

def validate_user(data):
    # Validate user ID
    if not isinstance(data.get("UserID"), str) or not (data["UserID"]).isalnum():
        return False, "Invalid UserID. Only alphanumeric characters are allowed."

    # Validate interested topics
    topics = data.get("Interested Topics", "").split(",")
    if len(topics) > 50 or any(not (topic.strip().replace(" ", "")).isalnum() for topic in topics):
        return False, "Invalid interested topics. Maximum 50 alphanumeric strings allowed, separated by commas."

    return True, ""

def validate_conference(data):
    required_fields = ["name", "location", "topics", "start_timestamp", "end_timestamp", "available_slots"]
    for field in required_fields:
        if field not in data:
            return False, f"Missing field: {field}"

    # Validate name
    if not isinstance(data["name"], str) or not data["name"].replace(" ", "").isalnum():
        return False, "Invalid conference name. Only alphanumeric characters and spaces are allowed."

    # Validate location
    if not isinstance(data["location"], str) or not data["location"].replace(" ", "").isalnum():
        return False, "Invalid location. Only alphanumeric characters and spaces are allowed."

    # Validate topics
    topics = data["topics"].split(",")
    if len(topics) > 10 or any(not topic.replace(" ", "").isalnum() for topic in topics):
        return False, "Invalid topics. Maximum 10 alphanumeric strings allowed, separated by commas."

    # Validate timestamps
    
    # timestamp = "2024-08-03T12:00:00Z"
    # # Replace Z with +00:00 to make it compatible with fromisoformat
    # timestamp = timestamp.replace("Z", "+00:00")
    # dt = datetime.fromisoformat(timestamp) // dt =  2024-08-03 12:00:00+00:00
    
    try:
        start_timestamp = datetime.fromisoformat(data["start_timestamp"].replace("Z", "+00:00"))
        end_timestamp = datetime.fromisoformat(data["end_timestamp"].replace("Z", "+00:00"))
    except ValueError:
        return False, "Invalid timestamps. Use ISO format."

    if start_timestamp >= end_timestamp:
        return False, "Start timestamp must be before end timestamp."
    
    if (end_timestamp - start_timestamp) > timedelta(hours=12):
        return False, "Conference duration should not exceed 12 hours."

    # Validate available slots
    if not isinstance(data["available_slots"], int) or data["available_slots"] <= 0:
        return False, "Available slots must be an integer greater than 0."

    return True, ""


@app.route('/add_user', methods=['POST'])
def add_user():
    data = request.get_json()

    # Validate input data
    is_valid, message = validate_user(data)
    if not is_valid:
        return jsonify({"error": message}), 400

    user_id = data["UserID"]
    if user_id in users:
        return jsonify({"error": "UserID already exists."}), 400

    # Add user to the system
    users[user_id] = {
        "UserID": user_id,
        "Interested Topics": data.get("Interested Topics", "")
    }

    return jsonify({"message": "User added successfully."}), 200


@app.route('/add_conference', methods=['POST'])
def add_conference():
    data = request.get_json()
    
    # Validate input data
    is_valid, message = validate_conference(data)
    if not is_valid:
        return jsonify({"error": message}), 400

    conference_name = data["name"]
    if conference_name in conferences:
        return jsonify({"error": "Conference name already exists."}), 400

    # Add conference to the system
    conferences[conference_name] = {
        "name": data["name"],
        "location": data["location"],
        "topics": data["topics"],
        "start_timestamp": data["start_timestamp"],
        "end_timestamp": data["end_timestamp"],
        "available_slots": data["available_slots"],
        "waitlist" : []
    }

    return jsonify({"message": "Conference added successfully."}), 200

@app.route('/book_conference', methods=['POST'])
def book_conference():
    data = request.get_json()
    conference_name = data.get("Name")
    user_id = data.get("UserID")
    
    if conference_name not in conferences:
        return jsonify({"error": "Conference not found.", "available_conferences": conferences}), 404
    
    if user_id not in users:
        return jsonify({"error": "UserID not found."}), 404

    conference = conferences[conference_name]
    
    
    # Check if user already has an overlapping booking
    for booking in bookings.values():
        if booking["UserID"] == user_id:
            user_conference = booking["Conference"]
            if user_conference == conference_name:
                return jsonify({"error": "User already has a booking for this conference.", "booking id": booking['booking_id']}), 400


    if conference["available_slots"] <= 0:
        waitlist_id = str(uuid.uuid4())
        waitlists[waitlist_id] = {
            "UserID": user_id,
            "Conference": conference_name,
            "timestamp": datetime.utcnow()  # Time when added to the waitlist
        }
        conference["waitlist"].append(waitlist_id)
        return jsonify({"waitlist_id": waitlist_id, "message": "Added to waitlist."}), 200

        
    # Generate a unique booking ID
    booking_id = str(uuid.uuid4())
    slot = conferences[conference_name]["available_slots"]
    
    # Create the booking entry
    bookings[booking_id] = {
        "booking_id" : booking_id,
        "UserID": user_id,
        "Conference": conference_name,
        "timestamp": datetime.utcnow()
    }
    
    # Decrement the available slots
    conferences[conference_name]["available_slots"] -= 1
    
    return jsonify({"booking_id": booking_id}), 200

@app.route('/confirm_waitlist_booking', methods=['POST'])
def confirm_waitlist_booking():
    data = request.get_json()
    waitlist_id = data.get("booking_id")
    
    if waitlist_id not in waitlists:
        return jsonify({"error": "Waitlist entry not found."}), 404
    
    waitlist_entry = waitlists[waitlist_id]
    conference_name = waitlist_entry["Conference"]
    conference = conferences.get(conference_name)

    if not conference:
        return jsonify({"error": "Conference not found."}), 404

    # Check if the slot is still available
    if conference["available_slots"] <= 0:
        return jsonify({"error": "No slots available."}), 400

    # Check if the waitlist entry is still valid (within 1 hour)
    if datetime.utcnow() - waitlist_entry["timestamp"] > timedelta(hours=1):
        # Move user to end of the waitlist
        conference["waitlist"].remove(waitlist_id)
        conference["waitlist"].append(waitlist_id)
        return jsonify({"error": "Confirmation window expired. Moved to end of waitlist."}), 400

    # Confirm booking
    booking_id = str(uuid.uuid4())
    bookings[booking_id] = {
        "booking_id" : booking_id,
        "UserID": waitlist_entry["UserID"],
        "Conference": conference_name,
        "timestamp": datetime.utcnow()
    }
    conference["available_slots"] -= 1

    # Remove from waitlist
    waitlists.pop(waitlist_id)

    return jsonify({"booking_id": booking_id, "message": "Booking confirmed from waitlist."}), 200



def process_waitlist(conference_name):
    conference = conferences.get(conference_name)
    if not conference:
        return

    now = datetime.utcnow()

    # Check if there are available slots and users in the waitlist
    if conference["available_slots"] > 0 and conference["waitlist"]:
        while conference["available_slots"] > 0 and conference["waitlist"]:
            waitlist_id = conference["waitlist"].pop(0)
            waitlist_entry = waitlists.get(waitlist_id)

            # Check if the waitlist entry exists and is within the 1-hour confirmation window
            if waitlist_entry and waitlist_entry.get("timestamp") and \
                now - waitlist_entry["timestamp"] > timedelta(hours=1):
                
                user_id = waitlist_entry["UserID"]

                # Create a booking for the user
                booking_id = str(uuid.uuid4())
                bookings[booking_id] = {
                    "booking_id": booking_id,
                    "UserID": user_id,
                    "Conference": conference_name,
                    "timestamp": now
                }
                conference["available_slots"] -= 1

                # Notify the user about their confirmed booking (e.g., via email)
                print(f"User {user_id} has been moved from waitlist to confirmed booking. Booking ID: {booking_id}")

                # Remove the waitlist entry
                del waitlists[waitlist_id]
            else:
                # If the waitlist entry is not within the confirmation window, put it back in the waitlist
                conference["waitlist"].append(waitlist_id)
                break  # Exit the loop to avoid infinite loop on non-eligible entries


@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    data = request.get_json()
    booking_id = data.get("booking_id")
    
    booking = bookings.get(booking_id)
    if booking:
        # if booking["status"] == "Canceled":
        #     return jsonify({"error": "Booking is already canceled."}), 400
        
        # Update the conference slots
        conference = conferences.get(booking["Conference"])
        # if booking["status"] == "Confirmed" and conference:
        conference["available_slots"] += 1
        
        if conference["waitlist"]:
            process_waitlist(conference)

        # Remove the booking
        del bookings[booking_id]
        return jsonify({"message": "Booking canceled successfully."}), 200

    # Check if the booking ID is in the waitlists dictionary
    waitlist_entry = waitlists.get(booking_id)
    if waitlist_entry:
        # Remove the waitlist entry
        del waitlists[booking_id]
        return jsonify({"message": "Removed from waitlist successfully."}), 200






@app.route('/booking_status/<booking_id>', methods=['GET'])
def booking_status(booking_id):
    # Check bookings first
    booking = bookings.get(booking_id)
    if booking:
        return jsonify({
            "status": "Confirmed",
            "conference_name": booking["Conference"],
            "user_id": booking["UserID"]
        }), 200

    # Check waitlists if not found in bookings
    waitlist_entry = waitlists.get(booking_id)
    if waitlist_entry:
        return jsonify({
            "status": " In Waitlist",
            "conference_name": waitlist_entry["Conference"],
            "user_id": waitlist_entry["UserID"],
        }), 200

    # Return an error if not found in either
    return jsonify({"error": "Booking ID not found."}), 404
 
if __name__ == '__main__':
    app.run(debug=True)