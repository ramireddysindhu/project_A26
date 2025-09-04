import streamlit as st
import requests
import json
import io

# --- Configuration ---
# Set the URL of your FastAPI backend.
# If running locally, it's typically http://127.0.0.1:8000
API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Medical Prescription Analyzer", layout="wide")

# Initialize session state to store extracted drugs
if 'extracted_drugs' not in st.session_state:
    st.session_state.extracted_drugs = []
if 'raw_text' not in st.session_state:
    st.session_state.raw_text = ""

# --- Helper Functions ---
def post_to_api(endpoint, data=None, files=None):
    """Handles API requests and returns JSON response or an error dictionary."""
    try:
        if files:
            response = requests.post(f"{API_BASE_URL}{endpoint}", files=files)
        else:
            response = requests.post(f"{API_BASE_URL}{endpoint}", json=data)
        
        # Check for HTTP errors
        response.raise_for_status()
        
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        return {"error": f"HTTP error occurred: {http_err} - {response.text}"}
    except requests.exceptions.ConnectionError:
        return {"error": "Connection failed. Is the FastAPI server running?"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}

def get_from_api(endpoint):
    """Handles GET requests and returns JSON response or an error dictionary."""
    try:
        response = requests.get(f"{API_BASE_URL}{endpoint}")
        
        # Check for HTTP errors
        response.raise_for_status()
        
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        return {"error": f"HTTP error occurred: {http_err} - {response.text}"}
    except requests.exceptions.ConnectionError:
        return {"error": "Connection failed. Is the FastAPI server running?"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {e}"}

# --- UI Layout ---
st.title("💊 Medical Prescription Analyzer")
st.markdown("---")

# Main columns for layout
col1, col2 = st.columns([1, 1])

with col1:
    st.header("1. Extract Drugs from Prescription")
    st.markdown("Upload an image of your prescription or manually select drugs below.")
    
    st.subheader("Upload Prescription")
    uploaded_file = st.file_uploader("Choose an image file...", type=["png", "jpg", "jpeg", "pdf"])

    if uploaded_file:
        st.image(uploaded_file, caption="Uploaded Prescription", use_column_width=True)
        
        if st.button("Analyze Prescription"):
            with st.spinner("Analyzing your prescription..."):
                files = {'file': uploaded_file.getvalue()}
                data = post_to_api("/extract_drugs/", files=files)
                
                if "error" in data:
                    st.error(f"Failed to extract drugs: {data['error']}")
                else:
                    st.session_state.extracted_drugs = data["extracted_drugs"]
                    st.session_state.raw_text = data["raw_text"]
                    st.success("Analysis complete!")
                    
    st.subheader("Manual Drug Entry")
    # This list should ideally be fetched from the backend API for a real application
    all_known_drugs = ["Aspirin", "Ibuprofen", "Acetaminophen", "Paracetamol", "Naproxen"]
    manual_selected_drugs = st.multiselect(
        "Or, select drugs from the list:",
        options=all_known_drugs
    )
    if manual_selected_drugs:
        st.session_state.extracted_drugs = manual_selected_drugs
        st.session_state.raw_text = "Drugs manually selected."
        st.info("Drugs have been manually selected. You can now proceed to the next section.")
    
    if st.session_state.raw_text:
        st.markdown("---")
        st.subheader("Raw Text from Prescription (for debugging)")
        st.text(st.session_state.raw_text)

with col2:
    st.header("2. Drug Information & Actions")
    
    # Check if there are drugs to analyze
    if not st.session_state.extracted_drugs:
        st.warning("Please upload a prescription or manually select drugs to proceed.")
    else:
        selected_drugs = st.session_state.extracted_drugs
        st.markdown(f"**Selected Drugs:** {', '.join(selected_drugs)}")
        
        # --- Drug Interaction Check ---
        st.subheader("Check Drug Interactions")
        interaction_drugs = st.multiselect(
            "Select drugs to check for interactions:",
            options=selected_drugs,
            default=selected_drugs
        )
        
        if st.button("Check Interactions"):
            if len(interaction_drugs) < 2:
                st.warning("Please select at least two drugs to check for interactions.")
            else:
                with st.spinner("Checking for interactions..."):
                    data = post_to_api("/check_interactions/", data={"drugs": interaction_drugs})
                    
                    if "error" in data:
                        st.error(f"Error checking interactions: {data['error']}")
                    else:
                        if data.get("interactions"):
                            st.error("Interactions Found:")
                            for interaction in data["interactions"]:
                                st.write(f"- **{interaction['drugs'][0].capitalize()}** and **{interaction['drugs'][1].capitalize()}**: {interaction['interaction']}")
                        else:
                            st.success("No major interactions found between selected drugs.")
                            
        st.markdown("---")

        # --- Drug Info and Dosage ---
        st.subheader("Get Drug Information & Dosage")
        selected_drug = st.selectbox("Select a drug:", selected_drugs)
        patient_age = st.number_input("Enter your age:", min_value=1, max_value=120, value=25)
        
        info_col, dosage_col, alt_col = st.columns(3)
        
        with info_col:
            if st.button("Get Info"):
                data = get_from_api(f"/get_medicine_info/{selected_drug.lower()}")
                if "error" in data:
                    st.error(f"Error fetching info: {data['error']}")
                else:
                    st.subheader(f"About {data.get('name', 'Drug')}")
                    st.write(f"**Description:** {data.get('description', 'N/A')}")
                    st.write(f"**Uses:** {data.get('uses', 'N/A')}")
                    st.write(f"**Side Effects:** {data.get('side_effects', 'N/A')}")
        
        with dosage_col:
            if st.button("Get Dosage"):
                data = post_to_api("/get_dosage/", data={"drug": selected_drug, "age": patient_age})
                if "error" in data:
                    st.error(f"Error getting dosage: {data['error']}")
                else:
                    st.success(f"Recommended dosage for {data['drug']}: **{data['recommended_dosage']}**")
        
        with alt_col:
            if st.button("Get Alternatives"):
                data = post_to_api("/get_alternatives/", data={"drug": selected_drug})
                if "error" in data:
                    st.error(f"Error fetching alternatives: {data['error']}")
                else:
                    if data.get("alternatives"):
                        st.success(f"Alternatives for {data['drug']}:")
                        st.write(", ".join(data['alternatives']))
                    else:
                        st.warning(f"No alternatives found for {selected_drug}.")
                        
        st.markdown("---")
        
        # --- Order Medicines ---
        st.subheader("Order Medicines")
        with st.form("order_form"):
            order_drugs = st.multiselect("Select drugs to order:", selected_drugs, default=selected_drugs)
            patient_name = st.text_input("Patient Name:")
            location = st.text_input("Delivery Location:")
            mobile_number = st.text_input("Mobile Number:")
            
            submit_button = st.form_submit_button("Place Order")
            
            if submit_button:
                if not all([order_drugs, patient_name, location, mobile_number]):
                    st.error("Please fill in all the required fields.")
                else:
                    with st.spinner("Placing your order..."):
                        data = post_to_api("/order_medicines/", data={
                            "drugs": order_drugs,
                            "patient_name": patient_name,
                            "location": location,
                            "mobile_number": mobile_number
                        })
                        
                        if "error" in data:
                            st.error(f"Order failed: {data['error']}")
                        else:
                            st.success(f"Order placed successfully! Order ID: {data['order_id']}")
