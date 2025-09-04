from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import uvicorn
import pytesseract
from PIL import Image
import io
import uuid
from transformers import pipeline
from pydantic import BaseModel, Field
import sqlite3

# --- PyTesseract Configuration ---
# You must install Tesseract OCR on your system and provide the path to its executable.
# For Windows:
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
# For macOS (with Homebrew):
# pytesseract.pytesseract.tesseract_cmd = r'/usr/local/bin/tesseract'
# For Linux:
# pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load HuggingFace medical NER model
try:
    ner_model = pipeline("ner", model="d4data/biomedical-ner-all", aggregation_strategy="simple")
except Exception as e:
    print(f"Error loading HuggingFace model: {e}")
    ner_model = None

# Dummy drug database for interaction and alternatives
drug_interactions = {
    ("aspirin", "ibuprofen"): "Increased risk of bleeding",
    ("paracetamol", "ibuprofen"): "Generally safe",
}

drug_alternatives = {
    "aspirin": ["acetaminophen", "naproxen"],
    "ibuprofen": ["acetaminophen", "naproxen"],
    "paracetamol": ["aspirin", "ibuprofen", "naproxen"],
}

# Dummy dosage recommendations by age (years)
dosage_by_age = {
    "aspirin": {"child": "50mg", "adult": "100mg"},
    "ibuprofen": {"child": "100mg", "adult": "200mg"},
    "paracetamol": {"child": "120mg", "adult": "500mg"},
    "acetaminophen": {"child": "120mg", "adult": "500mg"},
    "naproxen": {"child": "100mg", "adult": "250mg"},
}

# Hardcoded database with detailed information for a few key medicines
medicine_info_db = {
    "aspirin": {
        "name": "Aspirin",
        "description": "Aspirin is a nonsteroidal anti-inflammatory drug (NSAID) used to reduce pain, fever, and inflammation.",
        "uses": "Pain relief (headaches, muscle aches, etc.), fever reduction, and prevention of blood clots (at low doses).",
        "side_effects": "Stomach upset, heartburn, nausea, and increased risk of bleeding."
    },
    "ibuprofen": {
        "name": "Ibuprofen",
        "description": "Ibuprofen is an NSAID used to relieve pain, fever, and inflammation.",
        "uses": "Used for headaches, menstrual cramps, dental pain, and arthritis.",
        "side_effects": "Stomach pain, nausea, vomiting, dizziness, and rash."
    },
    "acetaminophen": {
        "name": "Acetaminophen",
        "description": "Acetaminophen (also known as Paracetamol) is a pain reliever and fever reducer.",
        "uses": "Treats mild to moderate pain (headaches, backaches) and reduces fever.",
        "side_effects": "Rarely causes side effects at recommended doses, but can cause liver damage in large amounts."
    },
    "paracetamol": {
        "name": "Paracetamol",
        "description": "Paracetamol (also known as Acetaminophen) is a pain reliever and fever reducer.",
        "uses": "Treats mild to moderate pain (headaches, backaches) and reduces fever.",
        "side_effects": "Rarely causes side effects at recommended doses, but can cause liver damage in large amounts."
    }
}

orders = {}

# Pydantic models for request bodies
class DrugsList(BaseModel):
    drugs: List[str]

class DrugDosageRequest(BaseModel):
    drug: str
    age: int

class DrugAlternativesRequest(BaseModel):
    drug: str

class OrderMedicinesRequest(BaseModel):
    drugs: List[str]
    patient_name: str
    location: str
    mobile_number: str = Field(..., pattern=r'^\d{10}$')

# Database functions
def get_db_connection():
    conn = sqlite3.connect('medicines.db')
    conn.row_factory = sqlite3.Row  # This allows you to access columns by name
    return conn

# Endpoints
@app.post("/extract_drugs/")
async def extract_drugs_from_prescription(file: UploadFile = File(...)):
    if not ner_model:
        return {"error": "Failed to load NER model. Please check your internet connection."}
    
    try:
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))
        
        # Check if the Tesseract path is configured correctly before using it
        try:
            text = pytesseract.image_to_string(image)
        except pytesseract.TesseractNotFoundError:
            return {"error": "Tesseract OCR engine not found. Please install it and set the path in app.py."}
            
        ner_results = ner_model(text)
        drugs = set()
        for entity in ner_results:
            if entity['entity_group'].lower() in ['drug', 'chemical']:
                drugs.add(entity['word'].lower())

        # Intersect with known drugs to filter
        known_drugs = set(dosage_by_age.keys())
        extracted_drugs = list(drugs.intersection(known_drugs))

        return {"extracted_drugs": extracted_drugs, "raw_text": text}
    except Exception as e:
        return {"error": f"Failed to extract drugs: {e}"}

def ibm_watson_drug_interaction_analysis(drugs: List[str]) -> List[dict]:
    interactions = []
    drugs = [d.lower() for d in drugs]
    for i in range(len(drugs)):
        for j in range(i + 1, len(drugs)):
            pair = (drugs[i], drugs[j])
            pair_rev = (drugs[j], drugs[i])
            if pair in drug_interactions:
                interactions.append({"drugs": pair, "interaction": drug_interactions[pair]})
            elif pair_rev in drug_interactions:
                interactions.append({"drugs": pair_rev, "interaction": drug_interactions[pair_rev]})
    return interactions

@app.post("/check_interactions/")
async def check_interactions(data: DrugsList):
    interactions = ibm_watson_drug_interaction_analysis(data.drugs)
    return {"interactions": interactions}

@app.post("/get_dosage/")
async def get_dosage(data: DrugDosageRequest):
    drug = data.drug.lower()
    if drug not in dosage_by_age:
        return {"error": "Drug not found"}
    if data.age < 18:
        dosage = dosage_by_age[drug]["child"]
    else:
        dosage = dosage_by_age[drug]["adult"]
    return {"drug": drug, "recommended_dosage": dosage}

@app.post("/get_alternatives/")
async def get_alternatives(data: DrugAlternativesRequest):
    drug = data.drug.lower()
    alternatives = drug_alternatives.get(drug, [])
    return {"drug": drug, "alternatives": alternatives}

@app.post("/order_medicines/")
async def order_medicines(data: OrderMedicinesRequest):
    order_id = str(uuid.uuid4())
    orders[order_id] = {
        "patient": data.patient_name,
        "drugs": data.drugs,
        "location": data.location,
        "mobile_number": data.mobile_number,
        "status": "Processing"
    }
    return {"order_id": order_id, "status": "Order placed"}

@app.get("/order_status/{order_id}")
async def order_status(order_id: str):
    order = orders.get(order_id)
    if not order:
        return {"error": "Order not found"}
    return {
        "order_id": order_id,
        "status": order["status"],
        "drugs": order["drugs"],
        "location": order["location"],
        "mobile_number": order["mobile_number"]
    }

@app.get("/get_medicine_info/{drug_name}")
async def get_medicine_info(drug_name: str):
    # First, check the hardcoded database for a perfect match
    if drug_name.lower() in medicine_info_db:
        return medicine_info_db[drug_name.lower()]
    
    # If not found, fall back to the SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM medicines WHERE name = ?", (drug_name.lower(),))
    medicine = cursor.fetchone()
    conn.close()
    
    if medicine:
        return dict(medicine)
    else:
        return {"error": "Medicine not found"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
