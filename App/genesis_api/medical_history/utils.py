from genesis_api.models import User,  DoctorPatientAssociation, UserImage,  MedicalHistory, Prescription
from genesis_api.tools.handlers import *
from genesis_api.tools.utils import *

from sqlalchemy.orm import Session,joinedload, contains_eager
from sqlalchemy.exc import SQLAlchemyError

import logging




def create_medical_history_report(user_id: int, **kwargs: dict[str,type]) -> dict[str,str]:
    """
    Create a new medical history report for a patient.

    Args:
        user_id (int): The ID of the doctor creating the report.
        **kwargs (dict): Keyword arguments containing the following:
            patient_id (int): The ID of the patient for whom the report is being created.
            observation (str): The doctor's observation of the patient's medical history.
            next_appointment (str): The date of the patient's next appointment in the format 'YYYY-MM-DD'.
            diagnostic (str): The doctor's diagnosis of the patient's condition.
            symptoms (str): The patient's symptoms.
            private_notes (str): Any private notes the doctor wishes to include.
            follow_up_required (bool): Whether a follow-up appointment is required.
            user_image (int): The ID of the user image associated with the report.

    Returns:
        dict: A dictionary containing the medical history report.
    """

    try:
        # Get the patient and the doctor-patient association id
        patient_id = User.get_data(kwargs['patient_id']).id
        if not patient_id:
            raise ElementNotFoundError('Patient not found')
        
        association = db.session.query(DoctorPatientAssociation).filter_by(doctor_id=user_id, patient_id=patient_id).first()
        if not association:
            raise ElementNotFoundError('Doctor-Patient association not found')
        elif db.session.query(MedicalHistory).filter(MedicalHistory.association_id == association.id, MedicalHistory.next_appointment_date==kwargs['next_appointment']).first():
            raise DuplicateEntryError('Medical history report already exists for this patient')
        
        # Create the medical history report
        medical_history = MedicalHistory(
            association_id=association.id,
            observation=kwargs['observation'],
            next_appointment_date=kwargs['next_appointment'], # AAAA-MM-DD
            diagnostic=kwargs['diagnostic'],
            symptoms=kwargs['symptoms'],
            private_notes=kwargs['private_notes'],
            follow_up_required=kwargs['follow_up_required'],
        )
        medical_history.user_images.append(UserImage.get_data(kwargs['user_image']))

        # Create the prescription

        if kwargs['prescription']:
            for prescription_obj in kwargs['prescription']:
                medical_history.prescriptions.append(create_prescription(**prescription_obj))


        db.session.add(medical_history)
        db.session.commit()
    except Exception as e:
        logging.exception("An error occurred while creating a medical history report: %s", e)
        raise InternalServerError(e)
    except SQLAlchemyError as e:
        logging.exception("An error occurred while creating a medical history report: %s", e)
        raise InternalServerError(e)
        
    # Return the medical history report as a dictionary
    return medical_history.to_dict()




from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

def create_prescription(**kwargs: dict[str, type]) -> dict[str, str]:
    """
    Create a new prescription object if it doesn't already exist.

    :param kwargs: A dictionary containing the prescription details.
    :return: A dictionary representation of the Prescription object.
    """

    try:

        # Check if a similar prescription already exists
        existing_prescription = Prescription.query.filter(
            Prescription.treatment == kwargs['treatment'],
            Prescription.dosage == kwargs['dosage'],
            Prescription.frequency_value == kwargs['frequency_value'],
            Prescription.frequency_unit == kwargs['frequency_unit'],
            Prescription.start_date == kwargs['start_date']
        ).one_or_none()

        if existing_prescription:
            logging.info("Prescription already exists.")
            return existing_prescription

        # Create new prescription
        new_prescription = Prescription(**kwargs)
        db.session.add(new_prescription)
        db.session.commit()
        return new_prescription

    except SQLAlchemyError as e:
        logging.exception("Database error occurred while creating a prescription.", exc_info=e)
        db.session.rollback()
        raise  # Re-raise the exception so the error can be handled further up the call stack

    except Exception as e:
        logging.exception("An unexpected error occurred while creating a prescription.", exc_info=e)
        raise  # Re-raise the exception so the error can be handled further up the call stack



def get_medical_history_by_patient(current_user: User, patient_id: int) -> dict:
    """
    Retrieve a patient's medical history from the database.

    :param current_user: The current user (doctor) making the request.
    :param patient_id: The ID of the patient whose medical history is being retrieved.
    :return: A list of dictionaries containing the medical history data, or None if no record was found.
    """
    try:
        # Combine queries to retrieve medical history records directly through the association
        medical_history_records = db.session.query(MedicalHistory)\
            .join(DoctorPatientAssociation, DoctorPatientAssociation.id == MedicalHistory.association_id)\
            .filter(
                DoctorPatientAssociation.doctor_id == current_user.id,
                DoctorPatientAssociation.patient_id == patient_id
            )\
            .options(
                contains_eager(MedicalHistory.association).joinedload(DoctorPatientAssociation.patient),
                joinedload(MedicalHistory.user_images),  # Eager load user images
                joinedload(MedicalHistory.prescriptions),  # Eager load prescriptions
            )\
            .all()

        if medical_history_records:
            medical_history_data = []
            for record in medical_history_records:
                record_dict = record.to_dict()
                if record.user_images:  # Only add if there are user images
                    record_dict['user_images'] = [image.to_dict() for image in record.user_images]
                if record.prescriptions:  # Only add if there are prescriptions
                    record_dict['prescriptions'] = [prescription.to_dict() for prescription in record.prescriptions]
                medical_history_data.append(record_dict)

            return medical_history_data
        else:
            return None

    except Exception as e:
        logging.exception("An error occurred while retrieving medical history: %s", e)
        return None


