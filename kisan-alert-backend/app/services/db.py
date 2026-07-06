import logging
import os
import firebase_admin
from firebase_admin import credentials, firestore
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Firebase Admin Client
db = None
try:
    if not firebase_admin._apps:
        cred_path = settings.FIREBASE_CREDENTIALS_PATH
        project_id = settings.FIREBASE_PROJECT_ID
        
        if cred_path and os.path.exists(cred_path):
            logger.info(f"Initializing Firebase Admin with credentials from {cred_path}")
            cred = credentials.Certificate(cred_path)
            options = {}
            if project_id:
                options["projectId"] = project_id
            firebase_admin.initialize_app(cred, options)
        else:
            logger.info("Initializing Firebase Admin with application default credentials")
            options = {}
            if project_id:
                options["projectId"] = project_id
            firebase_admin.initialize_app(options=options)
            
    db = firestore.client()
except Exception as e:
    logger.error(f"Failed to initialize Firebase Admin SDK client: {e}", exc_info=True)
    db = None


def get_farmer_by_phone(phone: str) -> dict | None:
    """
    Retrieve farmer details by their unique phone number.

    Args:
        phone: The phone number of the farmer to look up.

    Returns:
        A dictionary containing farmer details with 'id' field,
        or None if not found or if an error occurs.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return None

        farmers_ref = db.collection("farmers")
        query = farmers_ref.where("phone", "==", phone).limit(1)
        docs = query.stream()

        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            return data

        return None
    except Exception as e:
        logger.error(f"Firestore error in get_farmer_by_phone for {phone}: {e}", exc_info=True)
        return None


@firestore.transactional
def _create_farmer_transaction(transaction, farmers_ref, phone, name, village_id, language) -> dict | None:
    """
    Transactional read and write helper to check for phone uniqueness and create a farmer.
    """
    # Verify uniqueness of the phone number
    query = farmers_ref.where("phone", "==", phone).limit(1)
    docs = query.get(transaction=transaction)
    
    if len(docs) > 0:
        logger.warning(f"Validation failed: Phone number {phone} is already registered.")
        return None

    # Create document reference with auto-generated ID
    new_doc_ref = farmers_ref.document()
    data = {
        "phone": phone,
        "name": name,
        "village_id": village_id,
        "language": language or "te",
        "onboarding_stage": "new",
        "created_at": firestore.SERVER_TIMESTAMP
    }
    
    transaction.set(new_doc_ref, data)
    data["id"] = new_doc_ref.id
    return data


def create_farmer(phone: str, name: str, village_id: str, language: str = "te") -> dict | None:
    """
    Create a new farmer in the database if the phone number is unique.
    Uses a Firestore transaction to ensure uniqueness.

    Args:
        phone: Unique phone number of the farmer.
        name: Name of the farmer.
        village_id: ID of the village.
        language: Preferred language code (default "te").

    Returns:
        A dictionary containing the created farmer details including 'id',
        or None if phone number already exists or if an error occurs.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return None

        farmers_ref = db.collection("farmers")
        transaction = db.transaction()
        
        result = _create_farmer_transaction(
            transaction, 
            farmers_ref, 
            phone=phone, 
            name=name, 
            village_id=village_id, 
            language=language
        )
        return result
    except Exception as e:
        logger.error(f"Firestore error in create_farmer for phone {phone}: {e}", exc_info=True)
        return None


def update_farmer_onboarding(farmer_id: str, stage: str, village_id: str = None) -> bool:
    """
    Update a farmer's onboarding stage and optionally their village identifier.

    Args:
        farmer_id: The document ID of the farmer to update.
        stage: The new onboarding stage value.
        village_id: Optional village ID to update.

    Returns:
        True if the update was successful, False otherwise.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return False

        doc_ref = db.collection("farmers").document(farmer_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            logger.warning(f"Update failed: Farmer with ID {farmer_id} does not exist.")
            return False

        update_data = {
            "onboarding_stage": stage
        }
        if village_id is not None:
            update_data["village_id"] = village_id

        doc_ref.update(update_data)
        return True
    except Exception as e:
        logger.error(f"Firestore error in update_farmer_onboarding for {farmer_id}: {e}", exc_info=True)
        return False


def get_plot_for_farmer(farmer_id: str) -> list[dict]:
    """
    Retrieve all plots associated with a given farmer ID.

    Args:
        farmer_id: The document ID or reference ID of the farmer.

    Returns:
        A list of plot dictionaries including the 'id' field,
        or an empty list if none are found or if an error occurs.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return []

        plots_ref = db.collection("plots")
        query = plots_ref.where("farmer_id", "==", farmer_id)
        docs = query.stream()

        plots = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            plots.append(data)

        return plots
    except Exception as e:
        logger.error(f"Firestore error in get_plot_for_farmer for {farmer_id}: {e}", exc_info=True)
        return []


def get_all_plots() -> list[dict]:
    """
    Retrieve all plots currently registered in the database.

    Returns:
        A list of all plot dictionaries with 'id' fields,
        or an empty list if an error occurs.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return []

        plots_ref = db.collection("plots")
        docs = plots_ref.stream()

        plots = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            plots.append(data)

        return plots
    except Exception as e:
        logger.error(f"Firestore error in get_all_plots: {e}", exc_info=True)
        return []


def get_village_defaults(village_id: str) -> dict | None:
    """
    Retrieve default soil and nutrient values for a specific village.

    Args:
        village_id: The document ID (village code/identifier) to query.

    Returns:
        A dictionary containing default values and 'village_id',
        or None if not found or if an error occurs.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return None

        doc_ref = db.collection("village_defaults").document(village_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            data["village_id"] = doc.id
            return data

        return None
    except Exception as e:
        logger.error(f"Firestore error in get_village_defaults for {village_id}: {e}", exc_info=True)
        return None


def create_escalation(plot_id: str, photo_url: str, ai_diagnosis: str) -> dict | None:
    """
    Log a new crop disease or hazard escalation for review by agricultural officers.

    Args:
        plot_id: Reference or string ID of the affected plot.
        photo_url: Public access URL of the crop photo.
        ai_diagnosis: Crop disease diagnosis returned by the AI agent.

    Returns:
        A dictionary containing the created escalation details with its ID,
        or None if an error occurs.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return None

        escalations_ref = db.collection("escalations")
        new_doc_ref = escalations_ref.document()

        data = {
            "plot_id": plot_id,
            "photo_url": photo_url,
            "ai_diagnosis": ai_diagnosis,
            "status": "pending",
            "officer_note": "",
            "final_message": "",
            "created_at": firestore.SERVER_TIMESTAMP,
            "resolved_at": None
        }

        new_doc_ref.set(data)
        data["id"] = new_doc_ref.id
        return data
    except Exception as e:
        logger.error(f"Firestore error in create_escalation for plot {plot_id}: {e}", exc_info=True)
        return None


def list_pending_escalations() -> list[dict]:
    """
    List all escalations that are in 'pending' status waiting for officer review.

    Returns:
        A list of pending escalation dictionaries with 'id' fields,
        or an empty list if an error occurs.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return []

        escalations_ref = db.collection("escalations")
        query = escalations_ref.where("status", "==", "pending")
        docs = query.stream()

        pending = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            pending.append(data)

        return pending
    except Exception as e:
        logger.error(f"Firestore error in list_pending_escalations: {e}", exc_info=True)
        return []


def resolve_escalation(id: str, status: str, officer_note: str, final_message: str) -> bool:
    """
    Resolve a pending crop disease escalation with review results.

    Args:
        id: The document ID of the escalation.
        status: The resolution status (must be one of: 'approved', 'modified', 'rejected').
        officer_note: Remarks or annotations written by the officer.
        final_message: The final message payload to send to the farmer.

    Returns:
        True if the escalation was resolved successfully, False otherwise.
    """
    try:
        if db is None:
            logger.error("Firestore db client is not initialized.")
            return False

        allowed_statuses = {"approved", "modified", "rejected"}
        if status not in allowed_statuses:
            logger.error(f"Invalid escalation resolution status: {status}. Must be one of {allowed_statuses}")
            return False

        doc_ref = db.collection("escalations").document(id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Resolution failed: Escalation with ID {id} does not exist.")
            return False

        doc_ref.update({
            "status": status,
            "officer_note": officer_note,
            "final_message": final_message,
            "resolved_at": firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        logger.error(f"Firestore error in resolve_escalation for {id}: {e}", exc_info=True)
        return False
